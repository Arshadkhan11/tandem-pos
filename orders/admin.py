from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User
from django.utils.translation import gettext_lazy as _

from .models import StaffProfile, Table, MenuItem, Order, OrderItem, RestaurantSettings
from .upi_qr import decode_upi_from_image


class StaffUserCreationForm(UserCreationForm):
    """One-step hire: username, password, Tandem role, and display name."""

    role = forms.ChoiceField(
        choices=StaffProfile.ROLE_CHOICES,
        initial=StaffProfile.ROLE_WAITER,
        label="Tandem role",
        help_text=(
            "Waiter / Chef → app login only. "
            "Admin → app login + Django admin (/django-admin/)."
        ),
    )
    display_name = forms.CharField(
        max_length=50,
        label="Display name",
        help_text="Shown on the floor (tickets, locks, kitchen).",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    max_num = 1
    extra = 0
    verbose_name_plural = "Tandem role"
    fields = ("role", "display_name")


class StaffUserAdmin(DjangoUserAdmin):
    """Manage waiters/chefs/admins in one place. Role lives on StaffProfile."""

    add_form = StaffUserCreationForm
    inlines = [StaffProfileInline]
    list_display = ["username", "get_role", "get_display_name", "is_active", "is_staff"]
    list_filter = ["staff__role", "is_active"]
    search_fields = ["username", "staff__display_name"]
    # Derived from Tandem role — not manually toggled (that looked like “not saving”).
    readonly_fields = ("is_staff", "is_superuser", "last_login", "date_joined")

    # Drop Groups — Tandem uses StaffProfile.role, not auth groups.
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (
            _("Tandem access"),
            {
                "fields": ("is_active", "is_staff", "is_superuser"),
                "description": (
                    "Uncheck Active to offboard (blocks login; keeps history). "
                    "Staff status / superuser are set automatically from Tandem role: "
                    "only Admin gets /django-admin/ access. "
                    "Waiters and chefs log in at /login/waiter/ and /login/chef/ — "
                    "they do not need Staff status."
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "password1",
                    "password2",
                    "role",
                    "display_name",
                ),
                "description": (
                    "Create the account and Tandem role in one step. "
                    "Choose Admin only if they should manage users/settings "
                    "in Django admin."
                ),
            },
        ),
    )

    def get_inline_instances(self, request, obj=None):
        # Role is on the add form; inline is for edits only.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    @admin.display(description="Role", ordering="staff__role")
    def get_role(self, obj):
        try:
            return obj.staff.get_role_display()
        except StaffProfile.DoesNotExist:
            return "—"

    @admin.display(description="Display name")
    def get_display_name(self, obj):
        try:
            return obj.staff.display_name
        except StaffProfile.DoesNotExist:
            return "—"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and isinstance(form, StaffUserCreationForm):
            role = form.cleaned_data["role"]
            display_name = form.cleaned_data["display_name"].strip()
            StaffProfile.objects.update_or_create(
                user=obj,
                defaults={"role": role, "display_name": display_name},
            )
            self._sync_django_admin_flags(obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        self._sync_django_admin_flags(form.instance)

    @staticmethod
    def _sync_django_admin_flags(user):
        """Only Tandem Admin role may use /django-admin/."""
        try:
            profile = user.staff
        except StaffProfile.DoesNotExist:
            return
        is_admin = profile.role == StaffProfile.ROLE_ADMIN
        if user.is_staff != is_admin or user.is_superuser != is_admin:
            user.is_staff = is_admin
            user.is_superuser = is_admin
            user.save(update_fields=["is_staff", "is_superuser"])


# Replace the default User admin so role + display name are set where
# the account and password are managed — no seed_staff edits for day-to-day hires.
admin.site.unregister(User)
admin.site.register(User, StaffUserAdmin)
admin.site.unregister(Group)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ["display_name", "role", "user"]
    list_filter = ["role"]
    search_fields = ["display_name", "user__username"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        StaffUserAdmin._sync_django_admin_flags(obj.user)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["number", "name"]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "price", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "table", "waiter", "status", "created_at", "closed_at"]
    list_filter = ["status"]
    list_editable = ["waiter"]
    raw_id_fields = ["waiter"]
    inlines = [OrderItemInline]


@admin.register(RestaurantSettings)
class RestaurantSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "UPI payee",
            {
                "fields": ("upi_id", "payee_name", "qr_image"),
                "description": (
                    "Upload a UPI QR photo to auto-fill VPA and payee name, "
                    "or type them manually if scanning fails."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return not RestaurantSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        qr_changed = "qr_image" in form.changed_data and form.cleaned_data.get("qr_image")
        if qr_changed:
            decoded = decode_upi_from_image(form.cleaned_data["qr_image"])
            if decoded:
                obj.upi_id = decoded["pa"]
                if decoded.get("pn"):
                    obj.payee_name = decoded["pn"]
                self.message_user(
                    request,
                    f"QR scanned — UPI set to {obj.upi_id}"
                    + (f" ({obj.payee_name})" if obj.payee_name else "")
                    + ".",
                    level=messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    "Could not read a UPI QR from that image "
                    "(blurry photo, wrong format, or no QR found). "
                    "upi_id / payee_name were left unchanged — enter the VPA manually.",
                    level=messages.WARNING,
                )
        super().save_model(request, obj, form, change)
