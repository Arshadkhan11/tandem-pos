"""
Tests for table locking, billing/UPI, CSV exports, and admin dashboard ranges.
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import MenuItem, Order, OrderItem, RestaurantSettings, StaffProfile, Table

User = get_user_model()

TEST_SETTINGS = dict(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    TANDEM_UPI_ID="fallback@upi",
    TANDEM_PAYEE_NAME="Fallback Payee",
)


def _make_waiter(username, display_name=None):
    user = User.objects.create_user(username=username, password="testpass123")
    StaffProfile.objects.create(
        user=user,
        role=StaffProfile.ROLE_WAITER,
        display_name=display_name or username.title(),
    )
    return user


def _make_admin(username="admin_user"):
    user = User.objects.create_user(username=username, password="testpass123")
    user.is_staff = True
    user.is_superuser = True
    user.save()
    StaffProfile.objects.create(
        user=user,
        role=StaffProfile.ROLE_ADMIN,
        display_name="Admin",
    )
    return user


def _login_waiter(client, user):
    client.force_login(user)


@override_settings(**TEST_SETTINGS)
class TableLockingTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=1)
        self.w1 = _make_waiter("waiter_a", "Waiter A")
        self.w2 = _make_waiter("waiter_b", "Waiter B")
        self.item = MenuItem.objects.create(
            name="Paneer, Butter Masala",
            category="tea_coffee",
            price=Decimal("280.00"),
        )

    def test_unique_constraint_blocks_second_open_order(self):
        Order.objects.create(table=self.table, status=Order.STATUS_OPEN, waiter=self.w1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(table=self.table, status=Order.STATUS_OPEN, waiter=self.w2)

    def test_waiter_order_creates_owned_open_order(self):
        c = Client()
        _login_waiter(c, self.w1)
        r = c.get(reverse("waiter_order", args=[self.table.id]))
        self.assertEqual(r.status_code, 200)
        orders = Order.objects.filter(table=self.table, status=Order.STATUS_OPEN)
        self.assertEqual(orders.count(), 1)
        self.assertEqual(orders.get().waiter_id, self.w1.id)

    def test_second_waiter_cannot_add_item_while_locked(self):
        order = Order.objects.create(table=self.table, status=Order.STATUS_OPEN, waiter=self.w1)
        c2 = Client()
        _login_waiter(c2, self.w2)

        r = c2.get(reverse("waiter_order", args=[self.table.id]), follow=True)
        self.assertContains(r, "being served by Waiter A")

        r = c2.post(reverse("add_item", args=[order.id, self.item.id]), follow=True)
        self.assertContains(r, "being served by Waiter A")
        self.assertEqual(order.items.count(), 0)

    def test_second_waiter_can_order_after_close(self):
        order = Order.objects.create(table=self.table, status=Order.STATUS_OPEN, waiter=self.w1)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=1)
        order.status = Order.STATUS_CLOSED
        order.closed_at = timezone.now()
        order.save()

        c2 = Client()
        _login_waiter(c2, self.w2)
        r = c2.get(reverse("waiter_order", args=[self.table.id]))
        self.assertEqual(r.status_code, 200)
        open_orders = Order.objects.filter(table=self.table, status=Order.STATUS_OPEN)
        self.assertEqual(open_orders.count(), 1)
        self.assertEqual(open_orders.get().waiter_id, self.w2.id)

        r = c2.post(reverse("add_item", args=[open_orders.get().id, self.item.id]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(open_orders.get().items.count(), 1)


@override_settings(**TEST_SETTINGS)
class TableLockRaceTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=42)
        self.w1 = _make_waiter("race_w1", "Race One")
        self.w2 = _make_waiter("race_w2", "Race Two")

    def test_integrity_error_on_create_recovers_to_single_open_order(self):
        """
        Simulate the race: filter().first() saw no open order, but create()
        loses to another writer → IntegrityError → reload the winning open order.
        """
        from unittest.mock import patch

        original_create = Order.objects.create

        def racing_create(**kwargs):
            original_create(
                table=kwargs["table"],
                status=Order.STATUS_OPEN,
                waiter=self.w2,
            )
            raise IntegrityError("UNIQUE constraint failed: one_open_order_per_table")

        c = Client()
        c.force_login(self.w1)
        with patch.object(Order.objects, "create", side_effect=racing_create):
            r = c.get(reverse("waiter_order", args=[self.table.id]), follow=True)

        open_orders = Order.objects.filter(table=self.table, status=Order.STATUS_OPEN)
        self.assertEqual(open_orders.count(), 1)
        self.assertEqual(open_orders.get().waiter_id, self.w2.id)
        self.assertContains(r, "being served by Race Two")


@override_settings(**TEST_SETTINGS)
class BillingUpiTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=2)
        self.waiter = _make_waiter("bill_waiter")
        self.item = MenuItem.objects.create(
            name="Tea", category="tea_coffee", price=Decimal("40.00")
        )
        self.order = Order.objects.create(
            table=self.table, status=Order.STATUS_OPEN, waiter=self.waiter
        )
        OrderItem.objects.create(order=self.order, menu_item=self.item, quantity=3)

    def test_billing_total_and_qr_with_empty_restaurant_settings(self):
        RestaurantSettings.objects.all().delete()
        c = Client()
        c.force_login(self.waiter)
        r = c.get(reverse("billing_detail", args=[self.order.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["total"], Decimal("120.00"))
        self.assertTrue(r.context["qr_base64"])
        # Fallback VPA used in generated URI path — image exists even without RestaurantSettings
        self.assertIn("data:image/png;base64,", r.content.decode())

    def test_billing_uses_restaurant_settings_when_present(self):
        rs = RestaurantSettings.load()
        rs.upi_id = "tandem@okicici"
        rs.payee_name = "Tandem Cafe"
        rs.save()
        from orders.views import _upi_payee

        pa, pn = _upi_payee()
        self.assertEqual(pa, "tandem@okicici")
        self.assertEqual(pn, "Tandem Cafe")

    def test_double_close_is_safe(self):
        c = Client()
        c.force_login(self.waiter)
        r1 = c.post(
            reverse("close_order", args=[self.order.id]),
            {"payment_method": "upi"},
        )
        self.assertEqual(r1.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CLOSED)
        self.assertEqual(self.order.payment_method, Order.PAYMENT_UPI)

        r2 = c.post(
            reverse("close_order", args=[self.order.id]),
            {"payment_method": "cash"},
            follow=True,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            Order.objects.filter(table=self.table, status=Order.STATUS_CLOSED).count(),
            1,
        )

    def test_cash_close_counts_on_dashboard(self):
        c = Client()
        c.force_login(self.waiter)
        r = c.post(
            reverse("close_order", args=[self.order.id]),
            {"payment_method": "cash"},
        )
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_method, Order.PAYMENT_CASH)

        admin = _make_admin("cash_dash_admin")
        c.force_login(admin)
        dash = c.get(reverse("admin_summary") + "?range=today")
        self.assertEqual(dash.status_code, 200)
        self.assertEqual(dash.context["range_cash_revenue"], Decimal("120.00"))
        self.assertEqual(dash.context["range_upi_revenue"], Decimal("0"))
        self.assertEqual(dash.context["range_revenue"], Decimal("120.00"))
        self.assertEqual(dash.context["range_order_count"], 1)

    def test_close_without_payment_method_rejected(self):
        c = Client()
        c.force_login(self.waiter)
        r = c.post(reverse("close_order", args=[self.order.id]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("billing_detail", args=[self.order.id]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_OPEN)

    def test_zero_bill_close_deletes_order_not_counted(self):
        empty = Order.objects.create(
            table=Table.objects.create(number=22),
            status=Order.STATUS_OPEN,
            waiter=self.waiter,
        )
        c = Client()
        c.force_login(self.waiter)
        r = c.post(reverse("close_order", args=[empty.id]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Order.objects.filter(pk=empty.id).exists())
        self.assertEqual(
            Order.objects.filter(status=Order.STATUS_CLOSED).count(),
            0,
        )

    def test_remove_last_item_frees_table(self):
        line = self.order.items.get()
        # qty 3 → remove down to delete
        c = Client()
        c.force_login(self.waiter)
        c.post(reverse("remove_item", args=[self.order.id, line.id]))
        c.post(reverse("remove_item", args=[self.order.id, line.id]))
        r = c.post(reverse("remove_item", args=[self.order.id, line.id]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("waiter_tables"))
        self.assertFalse(Order.objects.filter(pk=self.order.id).exists())
        self.assertFalse(
            Order.objects.filter(table=self.table, status=Order.STATUS_OPEN).exists()
        )


@override_settings(**TEST_SETTINGS)
class ItemNoteTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=9)
        self.waiter = _make_waiter("note_waiter", "Note Waiter")
        self.chef = User.objects.create_user(username="note_chef", password="x")
        StaffProfile.objects.create(
            user=self.chef, role=StaffProfile.ROLE_CHEF, display_name="Note Chef"
        )
        self.item = MenuItem.objects.create(
            name="Chilli Chicken", category="starters_nonveg", price=Decimal("249.00")
        )
        self.order = Order.objects.create(
            table=self.table, status=Order.STATUS_OPEN, waiter=self.waiter
        )

    def test_different_notes_create_separate_lines(self):
        c = Client()
        c.force_login(self.waiter)
        c.post(
            reverse("add_item", args=[self.order.id, self.item.id]),
            {"note": "spicy"},
        )
        c.post(
            reverse("add_item", args=[self.order.id, self.item.id]),
            {"note": "gravy"},
        )
        c.post(
            reverse("add_item", args=[self.order.id, self.item.id]),
            {"note": "spicy"},
        )
        lines = list(self.order.items.order_by("note"))
        self.assertEqual(len(lines), 2)
        by_note = {ln.note: ln.quantity for ln in lines}
        self.assertEqual(by_note["gravy"], 1)
        self.assertEqual(by_note["spicy"], 2)

    def test_set_item_note_on_cart_line(self):
        line = OrderItem.objects.create(
            order=self.order, menu_item=self.item, quantity=1
        )
        c = Client()
        c.force_login(self.waiter)
        r = c.post(
            reverse("set_item_note", args=[self.order.id, line.id]),
            {"note": "sugar less"},
        )
        self.assertEqual(r.status_code, 302)
        line.refresh_from_db()
        self.assertEqual(line.note, "sugar less")

    def test_kitchen_shows_note_and_waiter(self):
        OrderItem.objects.create(
            order=self.order,
            menu_item=self.item,
            quantity=1,
            note="less oil, gravy",
        )
        c = Client()
        c.force_login(self.chef)
        r = c.get(reverse("kitchen_panel"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "less oil, gravy")
        self.assertContains(r, "Chilli Chicken")
        self.assertContains(r, "Note Waiter")  # display_name from _make_waiter default


@override_settings(**TEST_SETTINGS)
class CsvExportTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.waiter = _make_waiter("csv_waiter", "Csv Waiter")
        self.table = Table.objects.create(number=3)
        self.item = MenuItem.objects.create(
            name="Soup, Tomato",
            category="breakfast",
            price=Decimal("150.00"),
        )
        self.order = Order.objects.create(
            table=self.table,
            status=Order.STATUS_CLOSED,
            waiter=self.waiter,
            closed_at=timezone.now(),
            customer_name='Patel, "Arjun"',
            customer_phone="9876543210",
        )
        OrderItem.objects.create(order=self.order, menu_item=self.item, quantity=2)

    def _parse_csv(self, content: bytes):
        text = content.decode("utf-8")
        return list(csv.reader(io.StringIO(text)))

    def test_item_sales_csv_escapes_commas_and_quotes(self):
        c = Client()
        c.force_login(self.admin)
        r = c.get(reverse("admin_export_csv") + "?range=all")
        self.assertEqual(r.status_code, 200)
        rows = self._parse_csv(r.content)
        header = rows[0]
        self.assertIn("waiter", header)
        self.assertIn("customer_name", header)
        data = rows[1]
        # csv.reader unescapes — values must round-trip with commas/quotes intact
        self.assertIn("Soup, Tomato", data)
        self.assertIn('Patel, "Arjun"', data)
        self.assertIn("Csv Waiter", data)
        self.assertIn("note", header)

    def test_customers_csv_escapes_and_includes_total(self):
        c = Client()
        c.force_login(self.admin)
        r = c.get(reverse("admin_export_customers_csv") + "?range=all")
        self.assertEqual(r.status_code, 200)
        rows = self._parse_csv(r.content)
        header = rows[0]
        self.assertEqual(header[0], "order_id")
        data = rows[1]
        self.assertIn('Patel, "Arjun"', data)
        self.assertIn("2x Soup, Tomato", data)
        self.assertIn("300.00", data)
        self.assertIn("Csv Waiter", data)


@override_settings(**TEST_SETTINGS)
class AdminDashboardRangeTests(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.table = Table.objects.create(number=4)
        self.waiter = _make_waiter("dash_waiter")
        item = MenuItem.objects.create(
            name="Naan", category="tea_coffee", price=Decimal("50.00")
        )
        now = timezone.now()

        def closed_order(days_ago, qty):
            o = Order.objects.create(
                table=self.table,
                status=Order.STATUS_CLOSED,
                waiter=self.waiter,
                closed_at=now - timedelta(days=days_ago),
                created_at=now - timedelta(days=days_ago),
            )
            # Allow multiple closed orders on same table (constraint only on open)
            OrderItem.objects.create(order=o, menu_item=item, quantity=qty)
            return o

        self.today = closed_order(0, 2)       # ₹100
        self.week = closed_order(3, 4)        # ₹200
        self.month = closed_order(20, 6)      # ₹300
        self.old = closed_order(60, 10)       # ₹500

    def _kpis(self, query):
        c = Client()
        c.force_login(self.admin)
        r = c.get(reverse("admin_summary") + query)
        self.assertEqual(r.status_code, 200)
        return r.context["range_revenue"], r.context["range_order_count"]

    def test_today_range(self):
        rev, count = self._kpis("?range=today")
        self.assertEqual(rev, Decimal("100.00"))
        self.assertEqual(count, 1)

    def test_empty_closed_orders_excluded_from_kpis(self):
        Order.objects.create(
            table=self.table,
            status=Order.STATUS_CLOSED,
            waiter=self.waiter,
            closed_at=timezone.now(),
        )
        rev, count = self._kpis("?range=today")
        self.assertEqual(rev, Decimal("100.00"))
        self.assertEqual(count, 1)  # empty shell ignored

    def test_7d_range(self):
        rev, count = self._kpis("?range=7d")
        self.assertEqual(rev, Decimal("300.00"))  # today + week
        self.assertEqual(count, 2)

    def test_30d_range(self):
        rev, count = self._kpis("?range=30d")
        self.assertEqual(rev, Decimal("600.00"))  # today+week+month
        self.assertEqual(count, 3)

    def test_all_range(self):
        rev, count = self._kpis("?range=all")
        self.assertEqual(rev, Decimal("1100.00"))
        self.assertEqual(count, 4)

    def test_custom_range(self):
        start = (timezone.localdate() - timedelta(days=25)).isoformat()
        end = (timezone.localdate() - timedelta(days=15)).isoformat()
        rev, count = self._kpis(f"?range=custom&from={start}&to={end}")
        self.assertEqual(rev, Decimal("300.00"))
        self.assertEqual(count, 1)


@override_settings(**TEST_SETTINGS)
class SqliteWalAndSessionTests(TestCase):
    def test_sqlite_pragmas_applied(self):
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout;")
            timeout = cursor.fetchone()[0]
            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0].lower()
        self.assertGreaterEqual(timeout, 5000)
        # File DBs use WAL; Django's in-memory test DB reports "memory"
        self.assertIn(mode, ("wal", "memory"))

    def test_busy_timeout_reapplied_on_new_connection(self):
        """connection_created must set busy_timeout on every new SQLite handle."""
        connection.close()
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout;")
            timeout = cursor.fetchone()[0]
        self.assertGreaterEqual(timeout, 5000)

    def test_session_cookie_age_is_full_shift_friendly(self):
        from django.conf import settings

        # Django default two weeks; must not be shortened below an 8–12h shift
        self.assertGreaterEqual(settings.SESSION_COOKIE_AGE, 60 * 60 * 12)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 60 * 60 * 24 * 7 * 2)


@override_settings(**TEST_SETTINGS)
class SeedMenuAndCategoryGroupingTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(number=10)
        self.waiter = _make_waiter("seed_waiter")

    def test_seed_menu_loads_77_items_across_all_categories(self):
        from django.core.management import call_command
        from orders.management.commands.seed_menu import ITEMS

        self.assertEqual(len(ITEMS), 77)
        call_command("seed_menu")

        active = MenuItem.objects.filter(is_active=True)
        self.assertEqual(active.count(), 77)
        keys = set(active.values_list("category", flat=True))
        expected_keys = {c for c, _ in MenuItem.CATEGORY_CHOICES}
        self.assertEqual(keys, expected_keys)
        # No legacy placeholder slugs
        legacy = {
            "indian", "continental", "chinese", "bbq_grill", "seafood", "dessert",
            "beverage", "rice_noodles_pasta", "ice_cream",
        }
        self.assertFalse(keys & legacy)
        self.assertTrue(
            active.filter(name="Water Bottle (Small)", price=10, category="beverages").exists()
        )
        self.assertTrue(
            active.filter(name="Water Bottle (Large)", price=20, category="beverages").exists()
        )

    def test_waiter_order_groups_all_display_categories(self):
        from django.core.management import call_command

        call_command("seed_menu")
        c = Client()
        c.force_login(self.waiter)
        r = c.get(reverse("waiter_order", args=[self.table.id]))
        self.assertEqual(r.status_code, 200)
        by_cat = r.context["items_by_category"]
        expected_labels = [label for _, label in MenuItem.CATEGORY_CHOICES]
        self.assertEqual(list(by_cat.keys()), expected_labels)
        self.assertEqual(len(by_cat), 12)
        self.assertEqual(sum(len(v) for v in by_cat.values()), 77)
        # No empty / orphaned groups
        self.assertTrue(all(len(items) > 0 for items in by_cat.values()))
        self.assertContains(r, 'id="menu-search"')


@override_settings(**TEST_SETTINGS)
class RestaurantSettingsQrUploadTests(TestCase):
    def _png_bytes(self, img):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def test_valid_upi_qr_decodes_into_settings(self):
        import qrcode
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from orders.admin import RestaurantSettingsAdmin

        uri = "upi://pay?pa=tandem@okicici&pn=Tandem%20Retreat"
        img = qrcode.make(uri)
        upload = SimpleUploadedFile(
            "upi.png", self._png_bytes(img).read(), content_type="image/png"
        )

        rs = RestaurantSettings.load()
        rs.upi_id = "old@upi"
        rs.payee_name = "Old Name"
        rs.save()

        from orders.upi_qr import decode_upi_from_image

        decoded = decode_upi_from_image(upload)
        self.assertIsNotNone(decoded, "pyzbar must decode the generated UPI QR")
        self.assertEqual(decoded["pa"], "tandem@okicici")
        self.assertEqual(decoded["pn"], "Tandem Retreat")

        # Exercise admin save_model path
        factory = RequestFactory()
        request = factory.post("/django-admin/")
        request.user = _make_admin("qr_admin")
        setattr(request, "session", "session")
        setattr(request, "_messages", FallbackStorage(request))

        admin_obj = RestaurantSettingsAdmin(RestaurantSettings, AdminSite())

        class FakeForm:
            changed_data = ["qr_image"]
            cleaned_data = {"qr_image": upload}

        rs.upi_id = "old@upi"
        rs.payee_name = "Old Name"
        admin_obj.save_model(request, rs, FakeForm(), change=True)
        rs.refresh_from_db()
        self.assertEqual(rs.upi_id, "tandem@okicici")
        self.assertEqual(rs.payee_name, "Tandem Retreat")

    def test_non_qr_image_leaves_values_intact_with_warning(self):
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib import messages as dj_messages
        from django.test import RequestFactory
        from orders.admin import RestaurantSettingsAdmin

        blank = Image.new("RGB", (64, 64), color=(200, 180, 160))
        upload = SimpleUploadedFile(
            "blank.png", self._png_bytes(blank).read(), content_type="image/png"
        )

        rs = RestaurantSettings.load()
        rs.upi_id = "keep@upi"
        rs.payee_name = "Keep Name"
        rs.save()

        factory = RequestFactory()
        request = factory.post("/django-admin/")
        request.user = _make_admin("qr_admin2")
        setattr(request, "session", "session")
        setattr(request, "_messages", FallbackStorage(request))

        admin_obj = RestaurantSettingsAdmin(RestaurantSettings, AdminSite())

        class FakeForm:
            changed_data = ["qr_image"]
            cleaned_data = {"qr_image": upload}

        admin_obj.save_model(request, rs, FakeForm(), change=True)
        rs.refresh_from_db()
        self.assertEqual(rs.upi_id, "keep@upi")
        self.assertEqual(rs.payee_name, "Keep Name")
        stored = list(dj_messages.get_messages(request))
        self.assertTrue(any(m.level == dj_messages.WARNING for m in stored))


@override_settings(**TEST_SETTINGS)
class StaffAdminSyncAndLoginTests(TestCase):
    def test_waiter_role_clears_django_admin_flags(self):
        from orders.admin import StaffUserAdmin

        user = User.objects.create_user(username="new_waiter", password="pass12345")
        user.is_staff = True
        user.is_superuser = True
        user.save()
        StaffProfile.objects.create(
            user=user, role=StaffProfile.ROLE_WAITER, display_name="New Waiter"
        )
        StaffUserAdmin._sync_django_admin_flags(user)
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_admin_role_sets_django_admin_flags(self):
        from orders.admin import StaffUserAdmin

        user = User.objects.create_user(username="new_admin", password="pass12345")
        StaffProfile.objects.create(
            user=user, role=StaffProfile.ROLE_ADMIN, display_name="New Admin"
        )
        StaffUserAdmin._sync_django_admin_flags(user)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_create_user_form_sets_role_in_one_step(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from orders.admin import StaffUserAdmin, StaffUserCreationForm

        form = StaffUserCreationForm(
            data={
                "username": "floor_waiter",
                "password1": "pass12345!",
                "password2": "pass12345!",
                "role": StaffProfile.ROLE_WAITER,
                "display_name": "Floor Waiter",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        request = RequestFactory().post("/django-admin/auth/user/add/")
        request.user = _make_admin("hire_admin")
        StaffUserAdmin(User, AdminSite()).save_model(request, user, form, change=False)

        user.refresh_from_db()
        self.assertEqual(user.staff.role, StaffProfile.ROLE_WAITER)
        self.assertEqual(user.staff.display_name, "Floor Waiter")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_admin_form_grants_django_admin(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from orders.admin import StaffUserAdmin, StaffUserCreationForm

        form = StaffUserCreationForm(
            data={
                "username": "floor_admin",
                "password1": "pass12345!",
                "password2": "pass12345!",
                "role": StaffProfile.ROLE_ADMIN,
                "display_name": "Floor Admin",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        request = RequestFactory().post("/django-admin/auth/user/add/")
        request.user = _make_admin("hire_admin2")
        StaffUserAdmin(User, AdminSite()).save_model(request, user, form, change=False)

        user.refresh_from_db()
        self.assertEqual(user.staff.role, StaffProfile.ROLE_ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_new_staff_can_login_via_role_login_immediately(self):
        from orders.admin import StaffUserAdmin

        user = User.objects.create_user(username="hire_chef", password="chefpass99")
        StaffProfile.objects.create(
            user=user, role=StaffProfile.ROLE_CHEF, display_name="Hire Chef"
        )
        StaffUserAdmin._sync_django_admin_flags(user)

        c = Client()
        r = c.post(
            reverse("role_login", args=["chef"]),
            {"username": "hire_chef", "password": "chefpass99"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("kitchen_panel"))


@override_settings(**TEST_SETTINGS)
class CategoryRevenueChartTests(TestCase):
    def setUp(self):
        self.admin = _make_admin("chart_admin")
        self.waiter = _make_waiter("chart_waiter")
        self.table = Table.objects.create(number=11)
        # One closed sale in each of the 10 new categories
        now = timezone.now()
        for i, (slug, _label) in enumerate(MenuItem.CATEGORY_CHOICES):
            item = MenuItem.objects.create(
                name=f"Item {slug}",
                category=slug,
                price=Decimal("10.00") * (i + 1),
            )
            order = Order.objects.create(
                table=self.table,
                status=Order.STATUS_CLOSED,
                waiter=self.waiter,
                closed_at=now,
                created_at=now,
            )
            OrderItem.objects.create(order=order, menu_item=item, quantity=1)

    def test_dashboard_category_chart_uses_all_ten_new_labels(self):
        c = Client()
        c.force_login(self.admin)
        r = c.get(reverse("admin_summary") + "?range=all")
        self.assertEqual(r.status_code, 200)
        labels = r.context["chart_payload"]["categories"]["labels"]
        expected = [label for _, label in MenuItem.CATEGORY_CHOICES]
        self.assertEqual(set(labels), set(expected))
        self.assertEqual(len(labels), 12)
        legacy_labels = {
            "Indian", "Continental", "Chinese", "BBQ & Grill",
            "Seafood", "Desserts", "Beverages", "Rice, Noodles & Pasta", "Ice Creams",
        }
        self.assertFalse(set(labels) & legacy_labels)
        self.assertEqual(len(r.context["chart_payload"]["categories"]["values"]), 12)


@override_settings(**TEST_SETTINGS)
class FooterBrandingTests(TestCase):
    FOOTER_MARKERS = (
        "Gather. Dine. Celebrate.",
        "More than a meal. A destination.",
        "Version 1.0",
        "Crafted by Arshad",
    )

    def setUp(self):
        self.table = Table.objects.create(number=12)
        self.waiter = _make_waiter("foot_waiter")
        self.chef = User.objects.create_user(username="foot_chef", password="x")
        StaffProfile.objects.create(
            user=self.chef, role=StaffProfile.ROLE_CHEF, display_name="Foot Chef"
        )
        self.admin = _make_admin("foot_admin")
        self.item = MenuItem.objects.create(
            name="Footer Tea", category="tea_coffee", price=Decimal("30.00")
        )
        self.order = Order.objects.create(
            table=self.table, status=Order.STATUS_OPEN, waiter=self.waiter
        )

    def _assert_footer(self, response):
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in self.FOOTER_MARKERS:
            self.assertIn(marker, html)

    def test_footer_on_all_key_pages(self):
        c = Client()
        for role in ("waiter", "chef", "admin"):
            self._assert_footer(c.get(reverse("role_login", args=[role])))

        c.force_login(self.waiter)
        self._assert_footer(c.get(reverse("waiter_tables")))
        self._assert_footer(c.get(reverse("waiter_order", args=[self.table.id])))
        self._assert_footer(c.get(reverse("billing_tables")))
        self._assert_footer(c.get(reverse("billing_detail", args=[self.order.id])))

        c.force_login(self.chef)
        self._assert_footer(c.get(reverse("kitchen_panel")))

        c.force_login(self.admin)
        self._assert_footer(c.get(reverse("admin_summary")))

    def test_kitchen_footer_stays_compact_for_mobile(self):
        """Footer band should stay slim (py-1.5 / ~2–3 lines) — not a multi-section block."""
        c = Client()
        c.force_login(self.chef)
        r = c.get(reverse("kitchen_panel"))
        html = r.content.decode()
        self.assertEqual(html.count("<footer"), 1)
        self.assertIn("py-1.5", html)
        self.assertIn("flex flex-col", html)
        self.assertIn("flex-1", html)
        # No generous multi-row footer padding
        self.assertNotRegex(html, r"<footer[^>]*class=\"[^\"]*py-[6-9]")
        self.assertNotRegex(html, r"<footer[^>]*class=\"[^\"]*py-1[0-9]")
