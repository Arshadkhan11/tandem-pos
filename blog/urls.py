from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", views.home, name="site_home"),
    path("write/guide/", views.writer_guide, name="writer_guide"),
    path("write/", RedirectView.as_view(pattern_name="admin:blog_post_changelist"), name="write"),
    path("blog/", views.post_list, name="post_list"),
    path("blog/<slug:slug>/", views.post_detail, name="post_detail"),
]
