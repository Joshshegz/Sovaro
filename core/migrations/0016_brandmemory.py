from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0015_repurposeproject")]

    operations = [
        migrations.CreateModel(
            name="BrandMemory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("brand_fact", "Brand fact"), ("offer", "Offer or product"), ("audience_insight", "Audience insight"), ("customer_language", "Customer language"), ("performance_lesson", "Performance lesson"), ("guardrail", "Claim or topic to avoid")], max_length=40)),
                ("statement", models.TextField()),
                ("evidence", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("confirmed", "Confirmed"), ("hypothesis", "Working hypothesis"), ("needs_confirmation", "Needs confirmation")], default="needs_confirmation", max_length=30)),
                ("source", models.CharField(blank=True, default="user", max_length=30)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("brand", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memories", to="core.brandprofile")),
            ],
            options={"ordering": ["category", "-updated_at"]},
        ),
    ]
