import base64
import csv
from io import BytesIO

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import analytics
from .models import Table, MenuItem, Order, OrderItem, StaffProfile, RestaurantSettings
from .sms import send_sms_async

LATE_THRESHOLD_SECONDS = 10 * 60  # 10 minutes

ROLE_HOME = {
    StaffProfile.ROLE_WAITER: "waiter_tables",
    StaffProfile.ROLE_CHEF: "kitchen_panel",
    StaffProfile.ROLE_ADMIN: "admin_summary",
}


@require_GET
def health_check(request):
    """Unauthenticated liveness probe for uptime monitors."""
    return HttpResponse("ok", content_type="text/plain")


def _staff_role(request):
    if not request.user.is_authenticated:
        return None
    profile = getattr(request.user, "staff", None)
    return profile.role if profile else None


def _require_role(request, role):
    return _staff_role(request) == role


def _staff_name(request):
    profile = getattr(request.user, "staff", None)
    if profile:
        return profile.display_name
    return request.user.get_username() if request.user.is_authenticated else ""


def _user_display_name(user):
    if user is None:
        return "another waiter"
    try:
        return user.staff.display_name
    except StaffProfile.DoesNotExist:
        return user.get_username()


def _upi_payee():
    """RestaurantSettings first, then settings.py fallbacks."""
    try:
        rs = RestaurantSettings.objects.filter(pk=1).first()
        if rs and rs.upi_id:
            return rs.upi_id, (rs.payee_name or settings.TANDEM_PAYEE_NAME)
    except Exception:
        pass
    return settings.TANDEM_UPI_ID, settings.TANDEM_PAYEE_NAME


def _order_owned_by(order, user):
    """True if this waiter may add items / edit customer on the order."""
    if order.waiter_id is None:
        return True
    return order.waiter_id == user.id


def csrf_failure(request, reason=""):
    """Stale multi-tab login forms → send back to login instead of a 403 page."""
    messages.warning(request, "Session expired — please sign in again.")
    role = "waiter"
    path = (request.path or "").strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "login" and parts[1] in settings.STAFF_ROLES:
        role = parts[1]
    return redirect("role_login", role=role)


# ---------- username / password login ----------

@ensure_csrf_cookie
def role_login(request, role):
    if role not in settings.STAFF_ROLES:
        return redirect("role_login", role="waiter")

    # Already logged in as this role → go straight to panel
    if _require_role(request, role):
        return redirect(ROLE_HOME[role])

    # Same browser, different role open in another tab — clear so CSRF/session stay in sync
    if request.method == "GET" and request.user.is_authenticated:
        logout(request)
        return redirect("role_login", role=role)

    if request.method == "POST":
        # Switching accounts: drop previous session before authenticating
        if request.user.is_authenticated:
            logout(request)
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, "Wrong username or password.")
        else:
            profile = getattr(user, "staff", None)
            if profile is None or profile.role != role:
                messages.error(request, f"This account is not a {role} login.")
            else:
                login(request, user)
                return redirect(ROLE_HOME[role])

    return render(request, "orders/login.html", {"role": role})


@require_POST
def role_logout(request):
    role = _staff_role(request) or "waiter"
    logout(request)
    return redirect("role_login", role=role)


# ---------- waiter flow ----------

def waiter_tables(request):
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    tables = list(Table.objects.all())
    open_orders = (
        Order.objects.filter(status=Order.STATUS_OPEN)
        .select_related("waiter", "waiter__staff")
    )
    locks = {o.table_id: o for o in open_orders}
    for table in tables:
        order = locks.get(table.id)
        if order is None:
            table.lock_state = "free"
            table.lock_waiter_name = ""
        elif order.waiter_id is None or order.waiter_id == request.user.id:
            table.lock_state = "mine"
            table.lock_waiter_name = _user_display_name(order.waiter) if order.waiter_id else _staff_name(request)
        else:
            table.lock_state = "theirs"
            table.lock_waiter_name = _user_display_name(order.waiter)

    return render(request, "orders/waiter_tables.html", {
        "tables": tables,
        "staff_name": _staff_name(request),
    })


def waiter_order(request, table_id):
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    table = get_object_or_404(Table, pk=table_id)

    order = (
        Order.objects.filter(table=table, status=Order.STATUS_OPEN)
        .select_related("waiter", "waiter__staff")
        .first()
    )
    if order is None:
        try:
            order = Order.objects.create(
                table=table,
                status=Order.STATUS_OPEN,
                waiter=request.user,
            )
        except IntegrityError:
            order = (
                Order.objects.filter(table=table, status=Order.STATUS_OPEN)
                .select_related("waiter", "waiter__staff")
                .get()
            )

    # Claim legacy open orders that have no waiter yet
    if order.waiter_id is None:
        order.waiter = request.user
        order.save(update_fields=["waiter"])
    elif order.waiter_id != request.user.id:
        messages.error(
            request,
            f"{table} is currently being served by {_user_display_name(order.waiter)}.",
        )
        return redirect("waiter_tables")

    items_by_category = {}
    for label in dict(MenuItem.CATEGORY_CHOICES).values():
        items_by_category[label] = []
    for item in MenuItem.objects.filter(is_active=True):
        items_by_category.setdefault(item.get_category_display(), []).append(item)
    items_by_category = {
        label: items for label, items in items_by_category.items() if items
    }

    return render(request, "orders/waiter_order.html", {
        "table": table,
        "order": order,
        "items_by_category": items_by_category,
        "staff_name": _staff_name(request),
    })


@require_POST
def add_item(request, order_id, item_id):
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    order = get_object_or_404(
        Order.objects.select_related("waiter", "waiter__staff", "table"),
        pk=order_id,
        status=Order.STATUS_OPEN,
    )
    if not _order_owned_by(order, request.user):
        messages.error(
            request,
            f"{order.table} is currently being served by {_user_display_name(order.waiter)}.",
        )
        return redirect("waiter_tables")
    if order.waiter_id is None:
        order.waiter = request.user
        order.save(update_fields=["waiter"])

    menu_item = get_object_or_404(MenuItem, pk=item_id)
    note = (request.POST.get("note") or "").strip()[:120]
    existing = order.items.filter(
        menu_item=menu_item,
        status=OrderItem.STATUS_PENDING,
        note=note,
    ).first()
    if existing:
        existing.quantity += 1
        existing.save(update_fields=["quantity"])
    else:
        OrderItem.objects.create(
            order=order, menu_item=menu_item, quantity=1, note=note
        )
    return redirect("waiter_order", table_id=order.table_id)


@require_POST
def remove_item(request, order_id, item_id):
    """Decrease qty by 1; delete the line when qty hits 0."""
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    order = get_object_or_404(
        Order.objects.select_related("waiter", "waiter__staff", "table"),
        pk=order_id,
        status=Order.STATUS_OPEN,
    )
    if not _order_owned_by(order, request.user):
        messages.error(
            request,
            f"{order.table} is currently being served by {_user_display_name(order.waiter)}.",
        )
        return redirect("waiter_tables")

    line = get_object_or_404(OrderItem, pk=item_id, order=order)
    if line.quantity > 1:
        line.quantity -= 1
        line.save(update_fields=["quantity"])
    else:
        line.delete()

    # Empty cart → free the table (no ₹0 "sale" left hanging)
    if not order.items.exists():
        table = order.table
        order.delete()
        messages.info(request, f"{table} freed — cart was empty.")
        return redirect("waiter_tables")

    return redirect("waiter_order", table_id=order.table_id)


@require_POST
def set_customer(request, order_id):
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    order = get_object_or_404(
        Order.objects.select_related("waiter", "waiter__staff", "table"),
        pk=order_id,
        status=Order.STATUS_OPEN,
    )
    if not _order_owned_by(order, request.user):
        messages.error(
            request,
            f"{order.table} is currently being served by {_user_display_name(order.waiter)}.",
        )
        return redirect("waiter_tables")

    name = request.POST.get("customer_name", "").strip()[:100]
    phone = "".join(c for c in request.POST.get("customer_phone", "") if c.isdigit())[:15]
    opt_in = request.POST.get("marketing_opt_in") == "on"
    order.customer_name = name
    order.customer_phone = phone
    order.marketing_opt_in = opt_in
    order.save(update_fields=["customer_name", "customer_phone", "marketing_opt_in"])
    messages.success(request, "Customer details saved.")
    return redirect("waiter_order", table_id=order.table_id)


@require_POST
def set_item_note(request, order_id, item_id):
    """Optional kitchen note on a cart line (spicy, sugar less, etc.)."""
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    order = get_object_or_404(
        Order.objects.select_related("waiter", "waiter__staff", "table"),
        pk=order_id,
        status=Order.STATUS_OPEN,
    )
    if not _order_owned_by(order, request.user):
        messages.error(
            request,
            f"{order.table} is currently being served by {_user_display_name(order.waiter)}.",
        )
        return redirect("waiter_tables")

    line = get_object_or_404(OrderItem, pk=item_id, order=order)
    note = (request.POST.get("note") or "").strip()[:120]
    if line.note != note:
        line.note = note
        line.save(update_fields=["note"])
        if note:
            messages.success(request, f"Note saved for {line.menu_item.name}.")
        else:
            messages.info(request, f"Note cleared for {line.menu_item.name}.")
    return redirect("waiter_order", table_id=order.table_id)


def _queue_items():
    return (
        OrderItem.objects.filter(status=OrderItem.STATUS_PENDING, order__status=Order.STATUS_OPEN)
        .select_related("order", "order__table", "order__waiter", "order__waiter__staff", "menu_item")
        .order_by("added_at")
    )


def _annotate_age(items):
    now = timezone.now()
    for item in items:
        age = (now - item.added_at).total_seconds()
        item.age_minutes = int(age // 60)
        item.is_late = age >= LATE_THRESHOLD_SECONDS
        item.waiter_name = (
            _user_display_name(item.order.waiter) if item.order.waiter_id else ""
        )
    return items


@ensure_csrf_cookie
def kitchen_panel(request):
    if not _require_role(request, "chef"):
        return redirect("role_login", role="chef")
    items = _annotate_age(list(_queue_items()))
    return render(request, "orders/kitchen_panel.html", {
        "items": items,
        "staff_name": _staff_name(request),
    })


def kitchen_panel_partial(request):
    # Polled every few seconds by HTMX — returns just the ticket list markup.
    if not _require_role(request, "chef"):
        return redirect("role_login", role="chef")
    items = _annotate_age(list(_queue_items()))
    return render(request, "orders/_kitchen_queue.html", {"items": items})


@require_POST
def mark_ready(request, item_id):
    if not _require_role(request, "chef"):
        return redirect("role_login", role="chef")
    item = get_object_or_404(OrderItem, pk=item_id)
    item.status = OrderItem.STATUS_READY
    item.ready_at = timezone.now()
    item.save(update_fields=["status", "ready_at"])
    # HTMX request -> return the updated partial instead of a full redirect
    if request.headers.get("HX-Request"):
        items = _annotate_age(list(_queue_items()))
        return render(request, "orders/_kitchen_queue.html", {"items": items})
    return redirect("kitchen_panel")


# ---------- billing ----------

def billing_tables(request):
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    open_orders = Order.objects.filter(status=Order.STATUS_OPEN).select_related("table")
    return render(request, "orders/billing_tables.html", {
        "open_orders": open_orders,
        "staff_name": _staff_name(request),
    })


def billing_detail(request, order_id):
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    order = get_object_or_404(Order, pk=order_id, status=Order.STATUS_OPEN)
    total = order.total_amount()
    upi_id, payee_name = _upi_payee()

    upi_uri = (
        f"upi://pay?pa={upi_id}&pn={payee_name}"
        f"&am={total}&cu=INR&tn=Order{order.id}"
    )
    qr_img = qrcode.make(upi_uri)
    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode()

    return render(request, "orders/billing_detail.html", {
        "order": order,
        "total": total,
        "qr_base64": qr_base64,
        "staff_name": _staff_name(request),
        "whatsapp_url": order.whatsapp_url(
            f"Thanks for visiting Tandem! Your bill for {order.table} was ₹{total}."
        ),
    })


@require_POST
def close_order(request, order_id):
    if not _require_role(request, "waiter"):
        return redirect("role_login", role="waiter")
    order = (
        Order.objects.filter(pk=order_id, status=Order.STATUS_OPEN)
        .select_related("table")
        .first()
    )
    if order is None:
        # Idempotent: double-tap / slow retry after already closed
        messages.info(request, "That table was already closed.")
        return redirect("waiter_tables")

    total = order.total_amount()
    # ₹0 bill = practice / emptied cart — free table, do not count as a sale
    if total == 0:
        table = order.table
        order.delete()
        messages.info(request, f"{table} freed — no charge (empty bill not counted).")
        return redirect("waiter_tables")

    method = (request.POST.get("payment_method") or "").strip().lower()
    if method not in (Order.PAYMENT_CASH, Order.PAYMENT_UPI):
        messages.error(request, "Choose Cash or UPI to close the bill.")
        return redirect("billing_detail", order_id=order.id)

    order.status = Order.STATUS_CLOSED
    order.closed_at = timezone.now()
    order.payment_method = method
    order.save(update_fields=["status", "closed_at", "payment_method"])

    # Best-effort thank-you SMS — only when phone present + marketing opt-in
    if order.customer_phone and order.marketing_opt_in:
        send_sms_async(order.customer_phone, settings.SMS_THANKYOU)

    label = order.get_payment_method_display()
    messages.success(
        request, f"{order.table} closed ({label}). Total was ₹{total}."
    )
    return redirect("waiter_tables")


# ---------- admin summary (app theme dashboard — not django-admin) ----------

def admin_summary(request):
    if not _require_role(request, "admin"):
        return redirect("role_login", role="admin")

    start, end, range_key, from_str, to_str = analytics.parse_dashboard_range(request.GET)
    kpis = analytics.range_kpis(start, end)
    all_time = analytics.all_time_revenue()
    kitchen = analytics.kitchen_speed_stats(start, end)
    top_items = list(analytics.item_sales_breakdown(start, end, limit=10))
    categories = analytics.category_revenue(start, end)
    trend = analytics.daily_revenue_last_n_days(14)
    item_sales = analytics.item_sales_breakdown(start, end)
    recent_customers = (
        analytics.closed_orders_qs(start, end)
        .exclude(customer_phone="")
        .order_by("-closed_at")[:20]
    )

    chart_payload = {
        "trend": trend,
        "topItems": {
            "labels": [r["menu_item__name"] for r in top_items],
            "revenue": [float(r["revenue"] or 0) for r in top_items],
            "qty": [int(r["qty"] or 0) for r in top_items],
        },
        "categories": {
            "labels": [c["category"] for c in categories],
            "values": [c["revenue"] for c in categories],
        },
    }

    return render(request, "orders/admin_summary.html", {
        "staff_name": _staff_name(request),
        "range_key": range_key,
        "from_str": from_str,
        "to_str": to_str,
        "range_revenue": kpis["revenue"],
        "range_cash_revenue": kpis["cash_revenue"],
        "range_upi_revenue": kpis["upi_revenue"],
        "range_order_count": kpis["order_count"],
        "range_aov": kpis["aov"],
        "all_time_revenue": all_time,
        "kitchen": kitchen,
        "item_sales": item_sales,
        "recent_customers": recent_customers,
        "chart_payload": chart_payload,
        "export_query": request.GET.urlencode(),
    })


def admin_export_csv(request):
    """Item-wise sales CSV for the selected range (includes customer + waiter)."""
    if not _require_role(request, "admin"):
        return redirect("role_login", role="admin")

    start, end, range_key, _, _ = analytics.parse_dashboard_range(request.GET)
    items = OrderItem.objects.filter(order__status=Order.STATUS_CLOSED)
    if start is not None:
        items = items.filter(order__closed_at__date__gte=start)
    if end is not None:
        items = items.filter(order__closed_at__date__lte=end)
    items = items.select_related(
        "order", "order__table", "order__waiter", "order__waiter__staff", "menu_item",
    ).order_by("order_id", "id")

    stamp = range_key if range_key != "custom" else f"{start}_{end}"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="tandem-sales-{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "order_id", "table", "waiter", "customer_name", "customer_phone",
        "item_name", "note", "qty", "line_total", "order_total_paid",
        "payment_method", "closed_at", "marketing_opt_in",
    ])
    # Cache order totals to avoid N+1 sum loops
    order_totals = {}
    for item in items:
        order = item.order
        if order.id not in order_totals:
            order_totals[order.id] = order.total_amount()
        closed_at = order.closed_at
        writer.writerow([
            order.id,
            str(order.table),
            _user_display_name(order.waiter) if order.waiter_id else "",
            order.customer_name,
            order.customer_phone,
            item.menu_item.name,
            item.note,
            item.quantity,
            item.line_total(),
            order_totals[order.id],
            order.payment_method or "",
            timezone.localtime(closed_at).isoformat(timespec="seconds") if closed_at else "",
            "yes" if order.marketing_opt_in else "no",
        ])
    return response


def admin_export_customers_csv(request):
    """One row per closed order: customer, items, amount paid, waiter."""
    if not _require_role(request, "admin"):
        return redirect("role_login", role="admin")

    start, end, range_key, _, _ = analytics.parse_dashboard_range(request.GET)
    orders = (
        analytics.closed_orders_qs(start, end)
        .select_related("table", "waiter", "waiter__staff")
        .prefetch_related("items__menu_item")
        .order_by("-closed_at")
    )

    stamp = range_key if range_key != "custom" else f"{start}_{end}"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="tandem-customers-{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "order_id",
        "closed_at",
        "table",
        "customer_name",
        "customer_phone",
        "marketing_opt_in",
        "waiter",
        "items",
        "total_paid",
        "payment_method",
    ])
    for order in orders:
        items_summary = "; ".join(
            (
                f"{line.quantity}x {line.menu_item.name}"
                + (f" ({line.note})" if line.note else "")
            )
            for line in order.items.all()
        )
        closed_at = order.closed_at
        writer.writerow([
            order.id,
            timezone.localtime(closed_at).isoformat(timespec="seconds") if closed_at else "",
            str(order.table),
            order.customer_name,
            order.customer_phone,
            "yes" if order.marketing_opt_in else "no",
            _user_display_name(order.waiter) if order.waiter_id else "",
            items_summary,
            order.total_amount(),
            order.payment_method or "",
        ])
    return response
