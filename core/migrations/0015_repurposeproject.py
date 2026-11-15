from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0014_contentstrategy_gap_research")]

    operations = [
        migrations.CreateModel(
            name="RepurposeProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("repurpose", "Repurpose existing content"), ("fresh", "Start from a rough idea")], max_length=20)),
                ("source_title", models.CharField(blank=True, default="", max_length=255)),
                ("source_content", models.TextField()),
                ("platforms", models.JSONField(default=list)),
                ("objective", models.CharField(max_length=30)),
                ("desired_action", models.CharField(blank=True, default="", max_length=255)),
                ("source_analysis", models.JSONField(blank=True, default=dict)),
                ("hook_options", models.JSONField(blank=True, default=list)),
                ("outputs", models.JSONField(blank=True, default=list)),
                ("quality_report", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("brand", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="repurpose_projects", to="core.brandprofile")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
