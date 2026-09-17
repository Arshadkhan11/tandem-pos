"""
Django settings for tandem project.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _env(key, default=None):
    return os.environ.get(key, default)


def _env_bool(key, default=False):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Quick-start development settings — override via environment / .env on the VPS.
# Local runserver without a .env file: set DEBUG=True in the shell, e.g.
#   DEBUG=True python manage.py runserver
SECRET_KEY = _env(
    "SECRET_KEY",
    "django-insecure-%ecpzxd3l8kqx+6x0y^r_d75pxsx$z^$x8$@seafw9jvvv0k4=",
)

# Default False — only True when explicitly set in the environment.
DEBUG = _env_bool("DEBUG", False)

ALLOWED_HOSTS = [
    h.strip()
    for h in _env("ALLOWED_HOSTS", "app.tandemretreat.com").split(",")
    if h.strip()
]
# So local runserver still accepts requests when DEBUG=True without editing ALLOWED_HOSTS.
if DEBUG:
    for host in ("127.0.0.1", "localhost"):
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "orders.apps.OrdersConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tandem.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "orders.context_processors.app_branding",
            ],
        },
    },
]

WSGI_APPLICATION = "tandem.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # Timeout waiting for locks (WAL + busy_timeout also set on connect)
            "timeout": 20,
        },
    }
}

# Full-shift sessions (Django default = 2 weeks). Explicit so deploys don't shrink it.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2  # 14 days


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# HTTPS / proxy (Caddy terminates TLS → gunicorn over HTTP)
# When DEBUG=True (local), redirect/secure-cookies are off so runserver works on http://
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in _env(
        "CSRF_TRUSTED_ORIGINS",
        "https://app.tandemretreat.com,http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]
CSRF_FAILURE_VIEW = "orders.views.csrf_failure"


# Branding / product meta (footer + future white-label bumps)
APP_VERSION = "1.0"
APP_CREDIT = "Crafted by Arshad"

# Valid staff roles for /login/<role>/ pages.
STAFF_ROLES = ("waiter", "chef", "admin")

LOGIN_URL = "/login/waiter/"

# Fill in Tandem's real UPI ID before this goes live (e.g. "tandem@okicici")
TANDEM_UPI_ID = _env("TANDEM_UPI_ID", "tandem@upi")
TANDEM_PAYEE_NAME = _env("TANDEM_PAYEE_NAME", "Tandem")

# Customer SMS (optional). Leave SMS_API_KEY empty to log-only / skip network.
SMS_ENABLED = _env_bool("SMS_ENABLED", True)
SMS_API_KEY = _env("SMS_API_KEY", "")
SMS_THANKYOU = _env(
    "SMS_THANKYOU",
    "Thanks for visiting Tandem! We hope to see you again.",
)

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}
