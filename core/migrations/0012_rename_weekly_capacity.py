from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0011_monthlyreport_competitor_snapshot_and_more")]

    operations = [
        migrations.RenameField(
            model_name="brandprofile",
            old_name="weekly_hours_capacity",
            new_name="weekly_posts_capacity",
        ),
        migrations.AlterField(
            model_name="brandprofile",
            name="weekly_posts_capacity",
            field=models.PositiveIntegerField(
                default=3,
                help_text="Realistic number of social posts the brand can publish each week",
            ),
        ),
    ]
