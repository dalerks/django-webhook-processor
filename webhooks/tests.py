import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import WebhookEvent

PAYLOAD = {"id": "order_123", "financial_status": "paid"}
SECRET = "test-secret"


def _sig(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@override_settings(WEBHOOK_SECRET=SECRET)
class WebhookIngestTests(TestCase):
    def _post(self, payload=PAYLOAD, sig=None, topic="orders/create", source="shopify"):
        body = json.dumps(payload).encode()
        return self.client.post(
            f"/api/webhooks/{source}/",
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_TOPIC=topic,
            HTTP_X_WEBHOOK_SIGNATURE=sig or _sig(body),
        )

    @patch("webhooks.views.process_webhook_event.delay")
    def test_valid_webhook_stores_event_and_enqueues_task(self, mock_delay):
        res = self._post()
        self.assertEqual(res.status_code, 202)
        event = WebhookEvent.objects.get()
        self.assertEqual(event.topic, "orders/create")
        self.assertEqual(event.external_id, "order_123")
        self.assertEqual(event.status, WebhookEvent.Status.PENDING)
        mock_delay.assert_called_once_with(str(event.id))

    def test_invalid_signature_returns_401(self):
        res = self._post(sig="bad-sig")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    @patch("webhooks.views.process_webhook_event.delay")
    def test_duplicate_webhook_returns_200_without_duplicate(self, mock_delay):
        self._post()
        res = self._post()  # same id
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["duplicate"])
        self.assertEqual(WebhookEvent.objects.count(), 1)
        mock_delay.assert_called_once()  # only once, not twice

    def test_missing_id_returns_400(self):
        res = self._post(payload={"no_id": True})
        self.assertEqual(res.status_code, 400)


class EventListTests(TestCase):
    def setUp(self):
        WebhookEvent.objects.create(
            topic="orders/create", external_id="1", source="shopify", payload={}
        )
        WebhookEvent.objects.create(
            topic="products/update", external_id="2", source="stripe", payload={},
            status=WebhookEvent.Status.DONE,
        )

    def test_list_all_events(self):
        res = self.client.get("/api/events/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 2)

    def test_filter_by_status(self):
        res = self.client.get("/api/events/?status=done")
        self.assertEqual(len(res.json()), 1)
        self.assertEqual(res.json()[0]["external_id"], "2")

    def test_filter_by_source(self):
        res = self.client.get("/api/events/?source=shopify")
        self.assertEqual(len(res.json()), 1)
