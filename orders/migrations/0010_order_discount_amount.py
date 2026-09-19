from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_order_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="discount_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="₹ discount applied at checkout before payment.",
                max_digits=10,
            ),
        ),
    ]
