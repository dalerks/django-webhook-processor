# django-webhook-processor

> Async webhook ingestion pipeline — Django REST Framework, Celery, Redis, PostgreSQL. Accepts events from any platform, verifies HMAC signatures, stores idempotently, and processes in background workers with automatic retry.

## Business Problem Solved

Every production integration that receives webhooks faces the same three failure modes: **duplicate deliveries** (platform retries on timeout), **slow processing blocking the receiver** (causing more timeouts), and **silent failures with no retry**. This service solves all three: store-first with a unique constraint prevents duplicates, Celery offloads processing so the receiver always responds in <50ms, and exponential backoff retries handle transient downstream errors.

## What It Does

| Feature | Detail |
|---|---|
| Webhook ingest | `POST /api/webhooks/<source>/` — accepts events from any platform |
| HMAC verification | SHA-256 signature check before any processing |
| Idempotent storage | Unique constraint on `(topic, external_id)` — duplicate deliveries silently ignored |
| Async processing | Celery task enqueued immediately after store; receiver returns 202 in <50ms |
| Auto retry | Failed tasks retry up to 3× with 30s backoff |
| Event query API | `GET /api/events/?status=pending&source=shopify` |
| Topic routing | Dispatcher maps `orders/create`, `products/update`, etc. to typed handlers |

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | Django 5 + Django REST Framework |
| Language | Python 3.12 |
| Task queue | Celery 5 |
| Broker / cache | Redis 7 |
| Database | PostgreSQL 16 |
| Deploy | Docker Compose (local) / any container platform |

## Architecture

```
External Platform (Shopify, Stripe, etc.)
            │
            │  POST /api/webhooks/shopify/
            │  X-Webhook-Signature: <hmac>
            │  X-Webhook-Topic: orders/create
            ▼
┌───────────────────────────┐
│   WebhookIngestView       │
│                           │
│  1. Verify HMAC sig       │  → 401 if invalid
│  2. INSERT webhook_event  │  → 200 if duplicate (unique constraint)
│  3. Enqueue Celery task   │
│  4. Return 202 <50ms      │
└───────────┬───────────────┘
            │
            │  process_webhook_event.delay(event_id)
            ▼
┌───────────────────────────┐
│   Celery Worker(s)        │
│                           │
│  1. Load event from DB    │
│  2. Mark PROCESSING       │
│  3. Dispatch to handler   │──▶ orders/create → fulfillment
│  4. Mark DONE             │──▶ products/update → inventory sync
│  5. Retry on failure      │──▶ orders/updated → status notify
└───────────────────────────┘
```

## Project Structure

```
config/
├── settings.py        # Django config, Celery config
├── celery.py          # Celery app definition
└── urls.py

webhooks/
├── models.py          # WebhookEvent model (UUID PK, status, payload)
├── views.py           # WebhookIngestView, EventListView
├── tasks.py           # process_webhook_event + topic dispatcher
├── urls.py
└── tests.py           # 7 tests covering ingest, auth, dedup, filtering
```

## Setup

### Local (Docker Compose)

```bash
git clone https://github.com/dalerks/django-webhook-processor
cd django-webhook-processor
cp .env.example .env
docker compose up --build
```

This starts: PostgreSQL, Redis, the Django web server on `:8000`, and a Celery worker with 4 concurrent processes.

```bash
# Run migrations
docker compose exec web python manage.py migrate

# Run tests
docker compose exec web python manage.py test
```

### Local (without Docker)

```bash
pip install -r requirements.txt
cp .env.example .env
# Update DATABASE_URL and REDIS_URL in .env
python manage.py migrate
python manage.py runserver

# In a second terminal:
celery -A config worker --loglevel=info
```

## Usage

### Send a webhook event

```bash
# Compute HMAC
SECRET="your_webhook_secret"
BODY='{"id":"order_456","financial_status":"paid"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST http://localhost:8000/api/webhooks/shopify/ \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Topic: orders/create" \
  -H "X-Webhook-Signature: $SIG" \
  -d "$BODY"
# {"ok": true, "event_id": "...uuid..."}
```

### Query stored events

```bash
curl "http://localhost:8000/api/events/?status=pending&source=shopify"
```

### Add a new platform / topic handler

1. Register webhook in your platform dashboard pointing to `/api/webhooks/<your-source>/`
2. Add a handler in `webhooks/tasks.py`:
```python
def _handle_invoice_paid(payload: dict) -> None:
    # your logic here
    ...
```
3. Add it to the `handlers` dict in `_dispatch()`

## Tests

```bash
python manage.py test webhooks
```

7 tests covering: valid ingest, HMAC rejection, duplicate dedup, missing ID, event list, status filter, source filter.
