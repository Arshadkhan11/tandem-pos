"""
URL configuration for the public marketing site + blog (tandemretreat.com).

Served by a separate gunicorn process from tandem.urls (the staff app at
app.tandemretreat.com) so public traffic can never compete with live
ordering-service traffic for the same worker pool. Both processes share
the same codebase and database.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    path("", include("blog.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
