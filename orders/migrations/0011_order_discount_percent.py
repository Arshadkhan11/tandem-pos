from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0010_order_discount_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="discount_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Checkout discount % (0–100) applied before payment.",
                max_digits=5,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="discount_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="₹ off computed from discount % at apply/close (for reports).",
                max_digits=10,
            ),
        ),
    ]
