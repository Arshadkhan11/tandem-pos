from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0007_menu_split_rice_ice"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="note",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Kitchen note, e.g. spicy, gravy, less oil",
                max_length=120,
            ),
        ),
    ]
