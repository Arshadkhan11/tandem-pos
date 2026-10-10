"""Work out (and optionally make) the changes needed to bring the live menu in line
with `menu_data.MENU`. Deliberately cautious: it never deletes or deactivates anything,
never overwrites a price unless told to, and never touches is_active on existing items."""
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from .menu_data import HELD, MENU, RENAMES
from .models import MenuItem


@dataclass
class Plan:
    renames: list = field(default_factory=list)  # (old, new)
    rename_conflicts: list = field(default_factory=list)  # (old, new, why)
    creates: list = field(default_factory=list)  # (category, name, price)
    moves: list = field(default_factory=list)  # (name, from_label, to_label)
    price_differences: list = field(default_factory=list)  # (name, current, menu)
    unchanged: int = 0
    duplicates: list = field(default_factory=list)  # names found more than once in the DB
    left_alone: list = field(default_factory=list)  # active items not on the printed menu
    held: list = field(default_factory=lambda: list(HELD))

    @property
    def has_changes(self):
        return bool(self.renames or self.creates or self.moves)


def _labels():
    return dict(MenuItem.CATEGORY_CHOICES)


def build_plan():
    labels = _labels()
    existing = {}
    for item in MenuItem.objects.all().order_by("id"):
        existing.setdefault(item.name, []).append(item)

    plan = Plan()
    renamed_from = set()
    for old, new in RENAMES.items():
        if old not in existing:
            continue
        if new in existing:
            plan.rename_conflicts.append((old, new, f"“{new}” already exists too — merge them by hand"))
        elif len(existing[old]) > 1:
            plan.rename_conflicts.append((old, new, f"“{old}” exists more than once"))
        else:
            plan.renames.append((old, new))
            existing[new] = existing.pop(old)
            renamed_from.add(old)

    menu_names = set()
    for category, name, price in MENU:
        if category not in labels:
            raise ValueError(f"Unknown category “{category}” for {name}")
        menu_names.add(name)
        rows = existing.get(name, [])
        if not rows:
            plan.creates.append((category, name, Decimal(price)))
            continue
        if len(rows) > 1:
            plan.duplicates.append(name)
            continue
        item = rows[0]
        changed = False
        if item.category != category:
            plan.moves.append((name, labels.get(item.category, item.category), labels[category]))
            changed = True
        if item.price != Decimal(price):
            plan.price_differences.append((name, item.price, Decimal(price)))
        if not changed:
            plan.unchanged += 1

    # `existing` is keyed by the name each dish WILL have, so a dish about to be
    # renamed is matched against the printed menu under its new name.
    plan.left_alone = sorted(
        name
        for name, rows in existing.items()
        if name not in menu_names and any(i.is_active for i in rows)
    )
    return plan


@transaction.atomic
def apply_plan(plan, update_prices=False):
    """Make the changes in `plan`. Returns a small summary dict."""
    done = {"renamed": 0, "created": 0, "moved": 0, "prices_updated": 0}
    for old, new in plan.renames:
        MenuItem.objects.filter(name=old).update(name=new)
        done["renamed"] += 1
    wanted = {name: (category, Decimal(price)) for category, name, price in MENU}
    for category, name, price in plan.creates:
        MenuItem.objects.create(name=name, category=category, price=price, is_active=True)
        done["created"] += 1
    for name, _from, _to in plan.moves:
        MenuItem.objects.filter(name=name).update(category=wanted[name][0])
        done["moved"] += 1
    if update_prices:
        for name, _current, menu_price in plan.price_differences:
            MenuItem.objects.filter(name=name).update(price=menu_price)
            done["prices_updated"] += 1
    return done
