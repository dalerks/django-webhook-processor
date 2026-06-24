import hashlib
import hmac
import logging

from django.conf import settings
from django.db import IntegrityError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WebhookEvent
from .tasks import process_webhook_event

logger = logging.getLogger(__name__)


class WebhookIngestView(APIView):
    """
    Receives webhook POST from any platform, verifies HMAC, stores the event,
    and enqueues a Celery task for async processing.

    POST /api/webhooks/<source>/
    Headers: X-Webhook-Signature (base64 HMAC-SHA256 of raw body)
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request: Request, source: str) -> Response:
        raw_body = request.body
        signature = request.headers.get("X-Webhook-Signature", "")

        if not self._verify_signature(raw_body, signature):
            logger.warning("Invalid signature from source=%s", source)
            return Response({"detail": "Invalid signature"}, status=401)

        topic = request.headers.get("X-Webhook-Topic", "unknown")
        external_id = str(request.data.get("id", ""))

        if not external_id:
            return Response({"detail": "Missing payload id"}, status=400)

        try:
            event = WebhookEvent.objects.create(
                topic=topic,
                external_id=external_id,
                source=source,
                payload=request.data,
            )
        except IntegrityError:
            # Duplicate delivery — already stored, return 200 to silence retries
            logger.debug("Duplicate webhook %s/%s — skipping", topic, external_id)
            return Response({"ok": True, "duplicate": True})

        process_webhook_event.delay(str(event.id))
        return Response({"ok": True, "event_id": str(event.id)}, status=202)

    @staticmethod
    def _verify_signature(body: bytes, provided: str) -> bool:
        secret = settings.WEBHOOK_SECRET
        if not secret:
            return True  # verification disabled in dev
        expected = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, provided)


class EventListView(APIView):
    """GET /api/events/?status=pending&source=shopify"""

    def get(self, request: Request) -> Response:
        qs = WebhookEvent.objects.order_by("-received_at")
        if status := request.query_params.get("status"):
            qs = qs.filter(status=status)
        if source := request.query_params.get("source"):
            qs = qs.filter(source=source)
        data = list(
            qs.values(
                "id", "topic", "external_id", "source", "status", "received_at", "processed_at"
            )[:50]
        )
        return Response(data)
