"""The Tandem menu as printed (Nandi Hills · Full Menu), kept as data so a script can
bring the app's menu in line with it. Edit this file when the printed menu changes,
then run `manage.py update_menu` (it shows what it would do first)."""

# (category key, item name, price in ₹). Section order follows the printed menu.
MENU = [
    # Soups
    ("soups", "Veg Manchow Soup", 99),
    ("soups", "Lemon Coriander Soup", 110),
    ("soups", "Sweet Corn Soup", 110),
    ("soups", "Manchow Soup", 110),
    ("soups", "Chicken Soup", 160),
    # Veg starters
    ("starters_veg", "Gobi Manchurian", 199),
    ("starters_veg", "Pepper Mushroom", 179),
    ("starters_veg", "Chilli Mushroom", 199),
    ("starters_veg", "Chilli Paneer", 220),
    ("starters_veg", "Peri Peri Paneer", 220),
    ("starters_veg", "Paneer Manchurian", 220),
    # Non-veg starters
    ("starters_nonveg", "Chicken Lollipop (6pc)", 275),
    ("starters_nonveg", "Wings of Fire (6pc)", 275),
    ("starters_nonveg", "Crispy Chicken Strips", 275),
    ("starters_nonveg", "Chicken Nuggets", 149),
    # Wok-tossed chicken
    ("wok_chicken", "Dragon Chicken", 249),
    ("wok_chicken", "Chilli Chicken", 249),
    ("wok_chicken", "Piri Piri Chicken", 249),
    ("wok_chicken", "Pepper Chicken", 249),
    ("wok_chicken", "Lemon Chicken", 249),
    ("wok_chicken", "Chicken Manchurian", 249),
    # Fries & potato wedges
    ("fries", "Classic French Fries", 125),
    ("fries", "Peri Peri Fries", 149),
    ("fries", "Cheese Salted Fries", 175),
    ("fries", "Crispy Potato Wedges", 125),
    ("fries", "Peri Peri Potato Wedges", 149),
    ("fries", "Cheese Potato Wedges", 175),
    # Sandwiches
    ("breakfast", "Garden Veg Sandwich", 150),
    ("breakfast", "Cheese Veg Sandwich", 149),
    ("breakfast", "Mushroom Sandwich", 149),
    ("breakfast", "Chicken Sandwich", 199),
    # Maggi & quick bites
    ("maggi", "Veg Maggi", 99),
    ("maggi", "Egg Maggi", 125),
    ("maggi", "Egg Cheese Maggi", 149),
    ("maggi", "Bread Omelette", 99),
    # Veg curries (half / full are separate items, like Single / Double ice cream)
    ("curries_veg", "Veg Curry", 199),
    ("curries_veg", "Mix Veg Curry", 220),
    ("curries_veg", "Veg Kolhapuri", 220),
    ("curries_veg", "Paneer Butter Masala (Half)", 260),
    ("curries_veg", "Paneer Butter Masala (Full)", 500),
    ("curries_veg", "Paneer Do Pyaza", 240),
    ("curries_veg", "Mushroom Masala", 220),
    ("curries_veg", "Mushroom Do Pyaza", 220),
    ("curries_veg", "Paneer Lababdar", 280),
    ("curries_veg", "Matar Paneer", 220),
    ("curries_veg", "Shahi Paneer", 240),
    ("curries_veg", "Kadai Paneer", 260),
    ("curries_veg", "Paneer Pasanda", 240),
    ("curries_veg", "Kadai Mushroom", 220),
    ("curries_veg", "Dal Fry", 200),
    ("curries_veg", "Yellow Dal Tadka", 220),
    # Non-veg curries
    ("curries_nonveg", "Butter Chicken Bone-in (Half)", 280),
    ("curries_nonveg", "Butter Chicken Bone-in (Full)", 540),
    ("curries_nonveg", "Butter Chicken Boneless (Half)", 299),
    ("curries_nonveg", "Butter Chicken Boneless (Full)", 580),
    ("curries_nonveg", "Ra Ra Murga", 299),
    ("curries_nonveg", "Egg Curry (2pc)", 170),
    ("curries_nonveg", "Chicken Curry", 240),
    # Roti & paratha
    ("roti_paratha", "Plain Roti (Tawa)", 30),
    ("roti_paratha", "Butter Roti", 40),
    ("roti_paratha", "Lachha Paratha", 70),
    ("roti_paratha", "Aloo Paratha", 120),
    ("roti_paratha", "Paneer Paratha", 150),
    ("roti_paratha", "Onion Paratha", 100),
    ("roti_paratha", "Aloo Onion Paratha", 120),
    # Rice & comfort meals
    ("rice_comfort", "Steamed Rice", 90),
    ("rice_comfort", "Jeera Rice", 149),
    ("rice_comfort", "Ghee Rice", 199),
    ("rice_comfort", "Curd Rice", 160),
    ("rice_comfort", "Dal Khichdi", 220),
    # Rice, noodles & pasta
    ("rice_veg", "Veg Fried Rice", 149),
    ("rice_veg", "Schezwan Fried Rice", 175),
    ("rice_veg", "Schezwan Noodles", 175),
    ("rice_veg", "White Sauce Pasta", 225),
    ("rice_veg", "Pink Sauce Pasta", 225),
    ("rice_nonveg", "Egg Fried Rice", 175),
    ("rice_nonveg", "Chicken Fried Rice", 199),
    ("rice_nonveg", "Schezwan Chicken Fried Rice", 225),
    ("rice_nonveg", "Chicken Hakka Noodles", 199),
    ("rice_nonveg", "Schezwan Chicken Noodles", 225),
    ("rice_nonveg", "White Sauce Pasta (Chicken)", 249),
    ("rice_nonveg", "Pink Sauce Pasta (Chicken)", 249),
    # Tea & coffee
    ("tea_coffee", "Tea", 30),
    ("tea_coffee", "Masala Tea", 35),
    ("tea_coffee", "Black Tea", 30),
    ("tea_coffee", "Coffee", 30),
    ("tea_coffee", "Black Coffee", 30),
    ("tea_coffee", "Cold Coffee", 149),
    # Soft drinks
    ("beverages", "Thums Up", 30),
    ("beverages", "7UP", 30),
    # Milkshakes
    ("milkshakes", "Vanilla Milkshake", 99),
    ("milkshakes", "Strawberry Milkshake", 99),
    ("milkshakes", "Chocolate Milkshake", 119),
    ("milkshakes", "Butterscotch Milkshake", 119),
    ("milkshakes", "Mango Milkshake", 119),
    ("milkshakes", "Dry Fruit Milkshake", 149),
]

# An item that already exists under an old name is renamed (not duplicated), so its
# order history and any recipe stay attached.
RENAMES = {
    "Nuggets": "Chicken Nuggets",
}

# On the printed menu but marked "?" (unsure name or price). NOT added until confirmed.
HELD = [
    ("Egg Coag (2pc) — name unclear", 100),
    ("Chicken Lababdar / Andhera Chicken (Bone-in) — Half / Full", "280 / 540"),
    ("Chicken Lababdar / Andhera Chicken (Boneless) — Half / Full", "299 / 580"),
    ("Kadai Chicken — first entry", 270),
    ("Kadai Chicken — second entry", 260),
]
