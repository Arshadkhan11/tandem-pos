from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0008_orderitem_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[("cash", "Cash"), ("upi", "UPI")],
                default="",
                help_text="Set when the bill is closed (cash or UPI).",
                max_length=10,
            ),
        ),
    ]
