from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0012_rename_weekly_capacity")]

    operations = [
        migrations.AddField(
            model_name="brandprofile",
            name="brand_image",
            field=models.ImageField(
                blank=True,
                help_text="Brand logo or profile image",
                null=True,
                upload_to="brand_images/%Y/%m/",
            ),
        ),
    ]
