from django.core.management.base import BaseCommand

from orders.menu_update import apply_plan, build_plan
from orders.models import MenuItem


class Command(BaseCommand):
    help = (
        "Bring the menu in line with orders/menu_data.py (the printed menu). "
        "By default it only SHOWS what it would do. Add --apply to make the changes. "
        "It never deletes or deactivates anything and never changes a price unless you pass --update-prices."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually make the changes (default: preview only).")
        parser.add_argument(
            "--update-prices",
            action="store_true",
            help="Also overwrite existing prices with the ones in menu_data.py (off by default).",
        )

    def handle(self, *args, **options):
        plan = build_plan()
        w = self.stdout.write

        def section(title, rows, fmt):
            if rows:
                w(self.style.MIGRATE_HEADING(f"\n{title} ({len(rows)})"))
                for row in rows:
                    w("  " + fmt(row))

        section("Will be RENAMED (history and recipes stay attached)", plan.renames, lambda r: f"{r[0]}  →  {r[1]}")
        section("Will be ADDED", plan.creates, lambda r: f"{r[1]}  ₹{r[2]:.0f}  [{dict(MenuItem.CATEGORY_CHOICES)[r[0]]}]")
        section("Will be MOVED to another section", plan.moves, lambda r: f"{r[0]}:  {r[1]}  →  {r[2]}")
        section(
            "Price differs from the printed menu (NOT changed unless you pass --update-prices)",
            plan.price_differences,
            lambda r: f"{r[0]}: app ₹{r[1]:.0f}, printed menu ₹{r[2]:.0f}",
        )
        section("CAN'T be renamed", plan.rename_conflicts, lambda r: f"{r[0]} → {r[1]}: {r[2]}")
        section("Found MORE THAN ONCE in the app (skipped, fix by hand)", plan.duplicates, lambda r: r)
        section(
            "Active in the app but NOT on the printed menu (left exactly as they are)",
            plan.left_alone,
            lambda r: r,
        )
        section("NOT added: marked ‘?’ on the printed menu until you confirm", plan.held, lambda r: f"{r[0]}  ({r[1]})")
        w(f"\nAlready correct: {plan.unchanged}")

        if not options["apply"]:
            w(self.style.WARNING("\nPREVIEW ONLY — nothing was changed. Run again with --apply to make these changes."))
            return
        if not plan.has_changes and not (options["update_prices"] and plan.price_differences):
            w(self.style.SUCCESS("\nNothing to do — the app already matches the menu."))
            return
        done = apply_plan(plan, update_prices=options["update_prices"])
        active = MenuItem.objects.filter(is_active=True).count()
        w(
            self.style.SUCCESS(
                f"\nDone. Renamed {done['renamed']}, added {done['created']}, moved {done['moved']}, "
                f"prices updated {done['prices_updated']}. Active dishes now: {active}."
            )
        )
