"""Shared aggregation helpers for the /admin-summary/ dashboard and CSV export."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import MenuItem, Order, OrderItem

LATE_THRESHOLD = 10 * 60  # seconds — keep in sync with views.LATE_THRESHOLD_SECONDS


def _biz_tz():
    """Restaurant calendar day timezone (India)."""
    try:
        return ZoneInfo(getattr(settings, "TIME_ZONE", "Asia/Kolkata"))
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _day_start(d):
    """Inclusive start of calendar day `d` in business timezone, as aware UTC datetime."""
    return timezone.make_aware(datetime.combine(d, time.min), _biz_tz())


def _day_end_exclusive(d):
    """Exclusive end of calendar day `d` (start of next day)."""
    return _day_start(d + timedelta(days=1))


def _filter_closed_at(qs, start_date=None, end_date=None, field="closed_at"):
    """Filter by business-local calendar dates (not UTC __date)."""
    if start_date is not None:
        qs = qs.filter(**{f"{field}__gte": _day_start(start_date)})
    if end_date is not None:
        qs = qs.filter(**{f"{field}__lt": _day_end_exclusive(end_date)})
    return qs


def parse_dashboard_range(get):
    """
    Parse ?range=today|7d|30d|all|custom&from=&to=
    Returns (start_date|None, end_date|None, range_key, from_str, to_str).
    None,None means all time.
    """
    today = timezone.localdate()
    range_key = (get.get("range") or "today").strip().lower()
    from_str = (get.get("from") or "").strip()
    to_str = (get.get("to") or "").strip()

    def _parse(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None

    if range_key == "7d":
        return today - timedelta(days=6), today, "7d", from_str, to_str
    if range_key == "30d":
        return today - timedelta(days=29), today, "30d", from_str, to_str
    if range_key == "all":
        return None, None, "all", from_str, to_str
    if range_key == "custom":
        start = _parse(from_str) or today
        end = _parse(to_str) or today
        if start > end:
            start, end = end, start
        return start, end, "custom", start.isoformat(), end.isoformat()
    return today, today, "today", from_str, to_str


def closed_orders_qs(start_date=None, end_date=None):
    """Closed bills with at least one line item (excludes empty ₹0 practice closes)."""
    qs = (
        Order.objects.filter(status=Order.STATUS_CLOSED)
        .annotate(_line_count=Count("items"))
        .filter(_line_count__gt=0)
    )
    return _filter_closed_at(qs, start_date, end_date, field="closed_at")


def item_sales_breakdown(start_date=None, end_date=None, limit=None):
    """Item-wise qty + revenue for closed orders in range. Shared by dashboard + CSV."""
    qs = OrderItem.objects.filter(order__status=Order.STATUS_CLOSED)
    qs = _filter_closed_at(qs, start_date, end_date, field="order__closed_at")
    rows = (
        qs.values("menu_item__name")
        .annotate(qty=Sum("quantity"), revenue=Sum(F("quantity") * F("menu_item__price")))
        .order_by("-revenue")
    )
    if limit is not None:
        rows = list(rows[:limit])
    return rows


def category_revenue(start_date=None, end_date=None):
    qs = OrderItem.objects.filter(order__status=Order.STATUS_CLOSED)
    qs = _filter_closed_at(qs, start_date, end_date, field="order__closed_at")
    rows = (
        qs.values("menu_item__category")
        .annotate(revenue=Sum(F("quantity") * F("menu_item__price")))
        .order_by("-revenue")
    )
    cat_labels = dict(MenuItem.CATEGORY_CHOICES)
    return [
        {
            "category": cat_labels.get(r["menu_item__category"], r["menu_item__category"]),
            "revenue": float(r["revenue"] or 0),
        }
        for r in rows
    ]


def daily_revenue_last_n_days(n=14):
    today = timezone.localdate()
    start = today - timedelta(days=n - 1)
    item_rows = (
        _filter_closed_at(
            OrderItem.objects.filter(order__status=Order.STATUS_CLOSED),
            start,
            today,
            field="order__closed_at",
        )
        .annotate(day=TruncDate("order__closed_at", tzinfo=_biz_tz()))
        .values("day")
        .annotate(revenue=Sum(F("quantity") * F("menu_item__price")))
        .order_by("day")
    )
    by_day = {r["day"]: float(r["revenue"] or 0) for r in item_rows}
    labels = []
    values = []
    for i in range(n):
        d = start + timedelta(days=i)
        labels.append(d.isoformat())
        values.append(by_day.get(d, 0.0))
    return {"labels": labels, "values": values}


def kitchen_speed_stats(start_date=None, end_date=None):
    qs = OrderItem.objects.filter(
        status=OrderItem.STATUS_READY,
        ready_at__isnull=False,
    )
    qs = _filter_closed_at(qs, start_date, end_date, field="ready_at")

    total = qs.count()
    if total == 0:
        return {
            "avg_seconds": None,
            "avg_minutes": None,
            "late_pct": None,
            "sample_size": 0,
        }

    late = 0
    total_secs = 0.0
    for item in qs.only("added_at", "ready_at"):
        secs = (item.ready_at - item.added_at).total_seconds()
        total_secs += secs
        if secs >= LATE_THRESHOLD:
            late += 1
    avg = total_secs / total
    return {
        "avg_seconds": round(avg, 1),
        "avg_minutes": round(avg / 60, 1),
        "late_pct": round(100.0 * late / total, 1),
        "sample_size": total,
    }


def range_kpis(start_date=None, end_date=None):
    orders = list(closed_orders_qs(start_date, end_date))
    revenue = sum((o.total_amount() for o in orders), Decimal("0"))
    cash = sum(
        (o.total_amount() for o in orders if o.payment_method == Order.PAYMENT_CASH),
        Decimal("0"),
    )
    upi = sum(
        (o.total_amount() for o in orders if o.payment_method == Order.PAYMENT_UPI),
        Decimal("0"),
    )
    count = len(orders)
    aov = (revenue / count) if count else Decimal("0")
    return {
        "revenue": revenue,
        "cash_revenue": cash,
        "upi_revenue": upi,
        "order_count": count,
        "aov": aov.quantize(Decimal("0.01")) if count else Decimal("0"),
    }


def all_time_revenue():
    orders = closed_orders_qs()
    return sum((o.total_amount() for o in orders), Decimal("0"))
