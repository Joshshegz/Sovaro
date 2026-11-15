from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0013_brandprofile_brand_image")]

    operations = [
        migrations.AddField(
            model_name="contentstrategy",
            name="content_gap_research",
            field=models.JSONField(blank=True, default=dict, help_text="Grounded competitor coverage, whitespace findings, sources and research queries"),
        ),
        migrations.AddField(
            model_name="contentstrategy",
            name="content_gap_researched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
