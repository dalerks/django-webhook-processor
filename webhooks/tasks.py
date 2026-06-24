import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_webhook_event(self, event_id: str) -> None:
    from .models import WebhookEvent

    try:
        event = WebhookEvent.objects.get(pk=event_id)
    except WebhookEvent.DoesNotExist:
        logger.warning("WebhookEvent %s not found", event_id)
        return

    event.status = WebhookEvent.Status.PROCESSING
    event.save(update_fields=["status"])

    try:
        _dispatch(event)
        event.status = WebhookEvent.Status.DONE
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "processed_at"])
        logger.info("Processed %s", event)
    except Exception as exc:
        event.error = str(exc)
        event.save(update_fields=["error"])
        logger.exception("Failed to process %s", event)
        raise self.retry(exc=exc)


def _dispatch(event) -> None:
    """Route event to the correct handler by topic."""
    handlers = {
        "orders/create": _handle_order_create,
        "orders/updated": _handle_order_updated,
        "products/update": _handle_product_update,
    }
    handler = handlers.get(event.topic)
    if handler:
        handler(event.payload)
    else:
        logger.debug("No handler for topic %s — stored only", event.topic)


def _handle_order_create(payload: dict) -> None:
    order_id = payload.get("id")
    logger.info("New order %s — triggering fulfillment check", order_id)
    # Fulfillment logic, ERP push, notification, etc.


def _handle_order_updated(payload: dict) -> None:
    order_id = payload.get("id")
    status = payload.get("financial_status")
    logger.info("Order %s updated — status: %s", order_id, status)


def _handle_product_update(payload: dict) -> None:
    product_id = payload.get("id")
    logger.info("Product %s updated — syncing inventory", product_id)
