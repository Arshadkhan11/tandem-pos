from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class StaffProfile(models.Model):
    ROLE_WAITER = "waiter"
    ROLE_CHEF = "chef"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_WAITER, "Waiter"),
        (ROLE_CHEF, "Chef"),
        (ROLE_ADMIN, "Admin"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    display_name = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.display_name} ({self.role})"


class Table(models.Model):
    number = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=50, blank=True)  # optional, e.g. "Patio 1"

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return self.name or f"Table {self.number}"


class MenuItem(models.Model):
    CATEGORY_CHOICES = [
        ("tea_coffee", "Tea & Coffee"),
        ("maggi", "Maggi"),
        ("breakfast", "Sandwiches & Breakfast"),
        ("starters_veg", "Starters — Veg"),
        ("starters_nonveg", "Starters — Non-Veg"),
        ("fries", "Fries & Wedges"),
        ("rice_veg", "Rice, Noodles & Pasta — Veg"),
        ("rice_nonveg", "Rice, Noodles & Pasta — Non-Veg"),
        ("beverages", "Refreshers & Soft Drinks"),
        ("ice_signature", "Ice Creams — Signature"),
        ("ice_classic", "Ice Creams — Classic"),
        ("milkshakes", "Milkshakes"),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)  # toggle off instead of deleting

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_CLOSED, "Closed")]

    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name="orders")
    waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_taken",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    # Optional — asked once at order open; never required during rush
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    marketing_opt_in = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["table"],
                condition=Q(status="open"),
                name="one_open_order_per_table",
            ),
        ]

    def total_amount(self):
        return sum(item.line_total() for item in self.items.all())

    def phone_digits(self):
        return "".join(c for c in self.customer_phone if c.isdigit())

    def whatsapp_url(self, message="Thanks for visiting Tandem!"):
        digits = self.phone_digits()
        if len(digits) == 10:
            digits = "91" + digits
        elif digits.startswith("0") and len(digits) == 11:
            digits = "91" + digits[1:]
        if len(digits) < 12:
            return ""
        from urllib.parse import quote
        return f"https://wa.me/{digits}?text={quote(message)}"

    def __str__(self):
        return f"Order #{self.pk} — {self.table}"


class OrderItem(models.Model):
    STATUS_PENDING = "pending"
    STATUS_READY = "ready"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_READY, "Ready")]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    added_at = models.DateTimeField(default=timezone.now)
    ready_at = models.DateTimeField(null=True, blank=True)

    def line_total(self):
        return self.menu_item.price * self.quantity

    def age_seconds(self):
        return (timezone.now() - self.added_at).total_seconds()

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name}"


class RestaurantSettings(models.Model):
    """Singleton — UPI payee config edited in /django-admin/ only."""

    upi_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="UPI VPA, e.g. tandem@okicici",
    )
    payee_name = models.CharField(max_length=100, blank=True, default="Tandem")
    qr_image = models.ImageField(
        upload_to="upi_qr/",
        blank=True,
        null=True,
        help_text="Optional: upload a UPI QR photo to auto-fill VPA and payee name.",
    )

    class Meta:
        verbose_name = "Restaurant settings"
        verbose_name_plural = "Restaurant settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # singleton — never delete

    def __str__(self):
        return "Restaurant settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "upi_id": getattr(settings, "TANDEM_UPI_ID", ""),
                "payee_name": getattr(settings, "TANDEM_PAYEE_NAME", "Tandem"),
            },
        )
        return obj
