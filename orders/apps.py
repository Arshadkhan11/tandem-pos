from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _enable_sqlite_wal(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")


class OrdersConfig(AppConfig):
    name = "orders"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        connection_created.connect(_enable_sqlite_wal)
