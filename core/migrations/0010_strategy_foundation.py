from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0009_brandprofile_social_assessment_and_more")]

    operations = [
        migrations.AddField(
            model_name="brandprofile", name="strategy_inputs",
            field=models.JSONField(default=dict, blank=True),
        ),
        migrations.AddField(
            model_name="contentstrategy", name="strategy_foundation",
            field=models.JSONField(default=dict, blank=True),
        ),
    ]
