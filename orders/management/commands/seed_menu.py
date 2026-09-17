from django.core.management.base import BaseCommand

from orders.models import MenuItem, OrderItem, Table

# Real Tandem menu — Single/Double sizes are separate named items.
ITEMS = [
    # tea_coffee
    ("tea_coffee", "Tea", 30),
    ("tea_coffee", "Masala Tea", 35),
    ("tea_coffee", "Black Tea", 30),
    ("tea_coffee", "Coffee", 30),
    ("tea_coffee", "Black Coffee", 30),
    ("tea_coffee", "Cold Coffee", 149),
    # maggi
    ("maggi", "Veg Maggi", 99),
    ("maggi", "Egg Maggi", 125),
    ("maggi", "Egg Cheese Maggi", 149),
    # breakfast
    ("breakfast", "Garden Veg Sandwich", 150),
    ("breakfast", "Cheese Veg Sandwich", 149),
    ("breakfast", "Mushroom Sandwich", 149),
    ("breakfast", "Chicken Sandwich", 199),
    ("breakfast", "Bread Omelette", 99),
    # starters_veg
    ("starters_veg", "Gobi Manchurian", 199),
    ("starters_veg", "Pepper Mushroom", 179),
    ("starters_veg", "Chilli Mushroom", 199),
    ("starters_veg", "Chilli Paneer", 220),
    ("starters_veg", "Peri Peri Paneer", 220),
    ("starters_veg", "Paneer Manchurian", 220),
    # starters_nonveg
    ("starters_nonveg", "Chicken Lollipop (6pc)", 275),
    ("starters_nonveg", "Wings of Fire (6pc)", 275),
    ("starters_nonveg", "Crispy Chicken Strips", 275),
    ("starters_nonveg", "Nuggets", 149),
    ("starters_nonveg", "Dragon Chicken", 249),
    ("starters_nonveg", "Chilli Chicken", 249),
    ("starters_nonveg", "Piri Piri Chicken", 249),
    ("starters_nonveg", "Pepper Chicken", 249),
    ("starters_nonveg", "Lemon Chicken", 249),
    ("starters_nonveg", "Chicken Manchurian", 249),
    # fries
    ("fries", "Classic French Fries", 125),
    ("fries", "Peri Peri Fries", 149),
    ("fries", "Cheese Salted Fries", 175),
    ("fries", "Crispy Potato Wedges", 125),
    ("fries", "Peri Peri Potato Wedges", 149),
    ("fries", "Cheese Potato Wedges", 175),
    # rice_veg
    ("rice_veg", "Veg Fried Rice", 149),
    ("rice_veg", "Schezwan Fried Rice", 175),
    ("rice_veg", "Schezwan Noodles", 175),
    ("rice_veg", "White Sauce Pasta", 225),
    ("rice_veg", "Pink Sauce Pasta", 225),
    # rice_nonveg
    ("rice_nonveg", "Egg Fried Rice", 175),
    ("rice_nonveg", "Chicken Fried Rice", 199),
    ("rice_nonveg", "Chicken Hakka Noodles", 199),
    ("rice_nonveg", "Schezwan Chicken Noodles", 225),
    ("rice_nonveg", "Schezwan Chicken Fried Rice", 225),
    ("rice_nonveg", "White Sauce Pasta (Chicken)", 249),
    ("rice_nonveg", "Pink Sauce Pasta (Chicken)", 249),
    # beverages
    ("beverages", "Salt Lime Soda", 69),
    ("beverages", "Sweet & Salt Lime Soda", 79),
    ("beverages", "Thums Up", 30),
    ("beverages", "7UP", 30),
    ("beverages", "Red Bull", 199),
    # ice_signature
    ("ice_signature", "Tandem 7th Heaven (Single)", 80),
    ("ice_signature", "Tandem 7th Heaven (Double)", 150),
    ("ice_signature", "Tandem Arabian Nights (Single)", 80),
    ("ice_signature", "Tandem Arabian Nights (Double)", 150),
    # ice_classic
    ("ice_classic", "Vanilla (Single)", 60),
    ("ice_classic", "Vanilla (Double)", 110),
    ("ice_classic", "Strawberry (Single)", 60),
    ("ice_classic", "Strawberry (Double)", 110),
    ("ice_classic", "Chocolate (Single)", 60),
    ("ice_classic", "Chocolate (Double)", 110),
    ("ice_classic", "Butterscotch (Single)", 60),
    ("ice_classic", "Butterscotch (Double)", 110),
    ("ice_classic", "Mango (Single)", 60),
    ("ice_classic", "Mango (Double)", 110),
    ("ice_classic", "Coffee (Single)", 60),
    ("ice_classic", "Coffee (Double)", 110),
    # milkshakes
    ("milkshakes", "Vanilla Milkshake", 99),
    ("milkshakes", "Strawberry Milkshake", 99),
    ("milkshakes", "Chocolate Milkshake", 119),
    ("milkshakes", "Butterscotch Milkshake", 119),
    ("milkshakes", "Mango Milkshake", 119),
    ("milkshakes", "Dry Fruit Milkshake", 149),
]

DEFAULT_TABLES = 12

VALID_CATEGORIES = {c for c, _ in MenuItem.CATEGORY_CHOICES}


class Command(BaseCommand):
    help = "Seed Tandem menu items and tables"

    def handle(self, *args, **options):
        assert len(ITEMS) == 75, f"Expected 75 menu items, got {len(ITEMS)}"
        assert all(c in VALID_CATEGORIES for c, _, _ in ITEMS)

        # Clear placeholder / stale rows when nothing depends on them yet.
        if OrderItem.objects.exists():
            MenuItem.objects.exclude(name__in=[n for _, n, _ in ITEMS]).update(is_active=False)
            self.stdout.write(self.style.WARNING(
                "Order history present — deactivated unknown items instead of deleting."
            ))
        else:
            deleted, _ = MenuItem.objects.all().delete()
            self.stdout.write(f"Cleared {deleted} existing menu item(s).")

        created = 0
        updated = 0
        for category, name, price in ITEMS:
            obj, was_created = MenuItem.objects.update_or_create(
                name=name,
                defaults={"category": category, "price": price, "is_active": True},
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(self.style.SUCCESS(
            f"Menu items: {created} created, {updated} updated "
            f"({MenuItem.objects.filter(is_active=True).count()} active / {len(ITEMS)} expected)"
        ))

        tables_created = 0
        for n in range(1, DEFAULT_TABLES + 1):
            _, was_created = Table.objects.get_or_create(number=n)
            tables_created += int(was_created)
        self.stdout.write(self.style.SUCCESS(
            f"Tables created: {tables_created} (of {DEFAULT_TABLES})"
        ))
