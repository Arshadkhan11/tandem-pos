from django.conf import settings


def app_branding(request):
    """Expose APP_VERSION / APP_CREDIT to every template."""
    return {
        "app_version": getattr(settings, "APP_VERSION", "1.0"),
        "app_credit": getattr(settings, "APP_CREDIT", "Crafted by Arshad"),
    }
