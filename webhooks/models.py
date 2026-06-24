import uuid
from django.db import models


class WebhookEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        DONE = "done"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=120)
    external_id = models.CharField(max_length=255)
    source = models.CharField(max_length=80, default="unknown")
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("topic", "external_id")]
        indexes = [
            models.Index(fields=["status", "received_at"]),
            models.Index(fields=["source", "topic"]),
        ]

    def __str__(self):
        return f"{self.source}/{self.topic}/{self.external_id} [{self.status}]"
