from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from insights.build_analytics_db import CATEGORY_LABELS
from orders.menu_data import HELD, MENU, RENAMES
from orders.menu_update import apply_plan, build_plan
from orders.models import MenuItem, Order, OrderItem, StaffProfile, Table
from orders.tests import TEST_SETTINGS

User = get_user_model()


def run(*args):
    out = StringIO()
    call_command("update_menu", *args, stdout=out)
    return out.getvalue()


class MenuDataTests(TestCase):
    def test_names_are_unique_and_prices_sensible(self):
        names = [name for _, name, _ in MENU]
        self.assertEqual(len(names), len(set(names)), "a dish appears twice in menu_data.MENU")
        for _, name, price in MENU:
            self.assertGreater(price, 0, name)
            self.assertLessEqual(len(name), 100, name)

    def test_every_category_exists_and_every_section_is_used(self):
        valid = dict(MenuItem.CATEGORY_CHOICES)
        used = {category for category, _, _ in MENU}
        self.assertTrue(used <= set(valid), used - set(valid))
        # ice creams are not on the printed menu: the only sections allowed to be empty
        self.assertEqual(set(valid) - used, {"ice_signature", "ice_classic"})

    def test_held_items_are_not_in_the_menu_and_renames_point_at_menu_items(self):
        names = {name for _, name, _ in MENU}
        self.assertFalse([h for h, _ in HELD if h in names])
        for new in RENAMES.values():
            self.assertIn(new, names)

    def test_titles_have_no_known_misspellings(self):
        text = " ".join(name for _, name, _ in MENU).lower()
        self.assertNotIn("lawabdar", text)
        self.assertIn("lababdar", text)

    def test_analytics_labels_match_the_app(self):
        self.assertEqual(CATEGORY_LABELS, dict(MenuItem.CATEGORY_CHOICES))


class UpdateMenuOnTheCurrentMenuTests(TestCase):
    """Run against what is live today: the 77 items that seed_menu installs."""

    def setUp(self):
        call_command("seed_menu", stdout=StringIO())
        self.live_before = MenuItem.objects.filter(is_active=True).count()

    def test_preview_changes_nothing_and_says_so(self):
        before = list(MenuItem.objects.values_list("id", "name", "category", "price", "is_active"))
        text = run()
        self.assertEqual(before, list(MenuItem.objects.values_list("id", "name", "category", "price", "is_active")))
        self.assertIn("PREVIEW ONLY", text)
        self.assertIn("Nuggets  →  Chicken Nuggets", text)

    def test_plan_matches_what_we_expect_from_the_printed_menu(self):
        plan = build_plan()
        self.assertEqual(plan.renames, [("Nuggets", "Chicken Nuggets")])
        created = {name for _, name, _ in plan.creates}
        self.assertTrue({"Veg Manchow Soup", "Paneer Lababdar", "Aloo Paratha", "Dal Khichdi",
                         "Butter Chicken Bone-in (Full)", "Paneer Butter Masala (Half)"} <= created)
        self.assertEqual({n for n, _, _ in plan.moves},
                         {"Bread Omelette", "Dragon Chicken", "Chilli Chicken", "Piri Piri Chicken",
                          "Pepper Chicken", "Lemon Chicken", "Chicken Manchurian"})
        self.assertEqual(plan.price_differences, [])
        # on the app today but not on the printed menu: all ice creams, Red Bull, lime sodas, water
        self.assertEqual(len(plan.left_alone), 21)
        self.assertIn("Vanilla (Single)", plan.left_alone)
        self.assertIn("Red Bull", plan.left_alone)
        self.assertNotIn("Nuggets", plan.left_alone)  # it is about to be renamed, not left behind

    def test_apply_adds_renames_moves_and_keeps_everything_else(self):
        expected_new = len(build_plan().creates)
        nuggets = MenuItem.objects.get(name="Nuggets")
        order = Order.objects.create(table=Table.objects.create(number=99))
        OrderItem.objects.create(order=order, menu_item=nuggets, quantity=2)
        text = run("--apply")
        self.assertIn("Done.", text)
        nuggets.refresh_from_db()
        self.assertEqual(nuggets.name, "Chicken Nuggets")  # same row: history kept
        self.assertEqual(OrderItem.objects.get().menu_item_id, nuggets.pk)
        self.assertEqual(MenuItem.objects.get(name="Bread Omelette").category, "maggi")
        self.assertEqual(MenuItem.objects.get(name="Dragon Chicken").category, "wok_chicken")
        self.assertEqual(MenuItem.objects.get(name="Butter Chicken Bone-in (Full)").price, Decimal("540"))
        self.assertTrue(MenuItem.objects.filter(name="Vanilla (Single)", is_active=True).exists())  # untouched
        self.assertEqual(MenuItem.objects.filter(is_active=True).count(), self.live_before + expected_new)
        for _, name, _ in MENU:
            self.assertTrue(MenuItem.objects.filter(name=name).exists(), name)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        run("--apply")
        count = MenuItem.objects.count()
        self.assertFalse(build_plan().has_changes)
        self.assertIn("Nothing to do", run("--apply"))
        self.assertEqual(MenuItem.objects.count(), count)

    def test_a_raised_price_is_reported_but_not_overwritten_by_default(self):
        MenuItem.objects.filter(name="Chilli Paneer").update(price=260)  # owner raised it in admin
        plan = build_plan()
        self.assertEqual(plan.price_differences, [("Chilli Paneer", Decimal("260.00"), Decimal("220"))])
        text = run("--apply")
        self.assertIn("app ₹260, printed menu ₹220", text)
        self.assertEqual(MenuItem.objects.get(name="Chilli Paneer").price, Decimal("260.00"))

    def test_update_prices_flag_overwrites_prices(self):
        MenuItem.objects.filter(name="Chilli Paneer").update(price=260)
        run("--apply", "--update-prices")
        self.assertEqual(MenuItem.objects.get(name="Chilli Paneer").price, Decimal("220.00"))

    def test_it_never_reactivates_or_deactivates(self):
        MenuItem.objects.filter(name="Tea").update(is_active=False)
        run("--apply")
        self.assertFalse(MenuItem.objects.get(name="Tea").is_active)
        self.assertTrue(MenuItem.objects.get(name="Red Bull").is_active)

    def test_a_dish_that_exists_twice_is_skipped_and_reported(self):
        MenuItem.objects.create(name="Tea", category="tea_coffee", price=30)
        text = run("--apply")
        self.assertIn("MORE THAN ONCE", text)
        self.assertEqual(MenuItem.objects.filter(name="Tea").count(), 2)

    def test_rename_is_skipped_when_both_names_already_exist(self):
        MenuItem.objects.create(name="Chicken Nuggets", category="starters_nonveg", price=149)
        plan = build_plan()
        self.assertEqual(plan.renames, [])
        self.assertEqual(plan.rename_conflicts[0][:2], ("Nuggets", "Chicken Nuggets"))
        run("--apply")
        self.assertTrue(MenuItem.objects.filter(name="Nuggets").exists())

    def test_held_items_are_never_created(self):
        run("--apply")
        self.assertFalse(MenuItem.objects.filter(name__icontains="Coag").exists())
        self.assertFalse(MenuItem.objects.filter(name__icontains="Andhera").exists())
        self.assertFalse(MenuItem.objects.filter(name="Kadai Chicken").exists())
        self.assertIn("NOT added", run())


class UpdateMenuOnAnEmptyDatabaseTests(TestCase):
    def test_a_fresh_install_gets_the_whole_menu(self):
        run("--apply")
        self.assertEqual(MenuItem.objects.count(), len(MENU))


@override_settings(**TEST_SETTINGS)
class WaiterScreenAfterUpdateTests(TestCase):
    def test_sections_appear_in_printed_menu_order_and_new_items_are_orderable(self):
        run("--apply")
        waiter = User.objects.create_user("w1", password="pw-for-tests-123")
        StaffProfile.objects.create(user=waiter, role="waiter", display_name="W")
        table = Table.objects.create(number=1)
        self.client.force_login(waiter)
        resp = self.client.get(reverse("waiter_order", args=[table.pk]))
        sections = list(resp.context["items_by_category"])
        self.assertEqual(sections[:4], ["Soups", "Veg Starters", "Non-Veg Starters", "Wok-Tossed Chicken"])
        self.assertLess(sections.index("Veg Curries"), sections.index("Roti & Paratha"))
        self.assertIn("Aloo Paratha", [i.name for i in resp.context["items_by_category"]["Roti & Paratha"]])
        order = Order.objects.get(table=table)
        item = MenuItem.objects.get(name="Paneer Lababdar")
        self.client.post(reverse("add_item", args=[order.pk, item.pk]))
        self.assertEqual(order.items.get().menu_item, item)
