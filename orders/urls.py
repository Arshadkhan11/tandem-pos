from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check, name="health_check"),

    path("login/<str:role>/", views.role_login, name="role_login"),
    path("logout/", views.role_logout, name="role_logout"),

    path("waiter/", views.waiter_tables, name="waiter_tables"),
    path("waiter/table/<int:table_id>/", views.waiter_order, name="waiter_order"),
    path("waiter/order/<int:order_id>/add/<int:item_id>/", views.add_item, name="add_item"),
    path("waiter/order/<int:order_id>/item/<int:item_id>/remove/", views.remove_item, name="remove_item"),
    path("waiter/order/<int:order_id>/item/<int:item_id>/note/", views.set_item_note, name="set_item_note"),
    path("waiter/order/<int:order_id>/customer/", views.set_customer, name="set_customer"),

    path("kitchen/", views.kitchen_panel, name="kitchen_panel"),
    path("kitchen/partial/", views.kitchen_panel_partial, name="kitchen_panel_partial"),
    path("kitchen/item/<int:item_id>/ready/", views.mark_ready, name="mark_ready"),

    path("billing/", views.billing_tables, name="billing_tables"),
    path("billing/order/<int:order_id>/", views.billing_detail, name="billing_detail"),
    path("billing/order/<int:order_id>/close/", views.close_order, name="close_order"),

    path("admin-summary/", views.admin_summary, name="admin_summary"),
    path("admin/export/", views.admin_export_csv, name="admin_export_csv"),
    path("admin/export/customers/", views.admin_export_customers_csv, name="admin_export_customers_csv"),
]
