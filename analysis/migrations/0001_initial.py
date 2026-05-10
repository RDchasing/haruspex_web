# Generated manually for the initial haruspex web app.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AnalysisJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("original_name", models.CharField(max_length=255)),
                ("stored_name", models.CharField(blank=True, max_length=128)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "排队中"),
                            ("running", "解析中"),
                            ("success", "已完成"),
                            ("failed", "失败"),
                            ("cleaned", "已清理"),
                        ],
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("progress", models.PositiveSmallIntegerField(default=0)),
                ("message", models.CharField(blank=True, max_length=500)),
                ("error", models.TextField(blank=True)),
                ("archive_path", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("downloaded_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
