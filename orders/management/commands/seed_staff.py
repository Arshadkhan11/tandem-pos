from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from orders.models import StaffProfile

User = get_user_model()

# Change passwords before going live. Usernames stay stable for bookmarks/logins.
STAFF = [
    # 3 waiters — take orders / billing
    {"username": "waiter1", "password": "waiter111", "role": StaffProfile.ROLE_WAITER, "display_name": "Waiter 1"},
    {"username": "waiter2", "password": "waiter222", "role": StaffProfile.ROLE_WAITER, "display_name": "Waiter 2"},
    {"username": "waiter3", "password": "waiter333", "role": StaffProfile.ROLE_WAITER, "display_name": "Waiter 3"},
    # 2 chefs — kitchen queue
    {"username": "chef1", "password": "chef1111", "role": StaffProfile.ROLE_CHEF, "display_name": "Chef 1"},
    {"username": "chef2", "password": "chef2222", "role": StaffProfile.ROLE_CHEF, "display_name": "Chef 2"},
    # 1 generic admin — sales summary
    {"username": "admin", "password": "admin123", "role": StaffProfile.ROLE_ADMIN, "display_name": "Admin"},
]


class Command(BaseCommand):
    help = "Create/update staff logins (3 waiters, 2 chefs, 1 admin)"

    def handle(self, *args, **options):
        for entry in STAFF:
            user, created = User.objects.get_or_create(username=entry["username"])
            user.set_password(entry["password"])
            is_admin = entry["role"] == StaffProfile.ROLE_ADMIN
            user.is_staff = is_admin
            # Full permissions for the admin role so they can manage staff
            # (add/edit/disable waiters & chefs) from /django-admin/ without
            # needing individual model permissions assigned.
            user.is_superuser = is_admin
            user.is_active = True
            user.save()

            StaffProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": entry["role"],
                    "display_name": entry["display_name"],
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"{action}: {entry['username']} ({entry['role']}) — {entry['display_name']}")

        self.stdout.write(self.style.SUCCESS("Staff accounts ready."))
