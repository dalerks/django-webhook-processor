import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="WebhookEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ("topic", models.CharField(max_length=120)),
                ("external_id", models.CharField(max_length=255)),
                ("source", models.CharField(default="unknown", max_length=80)),
                ("payload", models.JSONField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("done", "Done"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"indexes": [
                models.Index(fields=["status", "received_at"], name="webhooks_status_idx"),
                models.Index(fields=["source", "topic"], name="webhooks_source_topic_idx"),
            ]},
        ),
        migrations.AlterUniqueTogether(
            name="webhookevent",
            unique_together={("topic", "external_id")},
        ),
    ]
