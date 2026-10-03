from django.contrib import admin
from django.urls import NoReverseMatch
from django.utils.html import format_html

from .models import Post

admin.site.site_header = "Tandem"
admin.site.site_title = "Tandem"
admin.site.index_title = "Welcome"
admin.site.index_template = "blog/admin/index.html"


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["title", "state_badge", "author", "published_at", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title", "excerpt", "focus_keyword"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["public_link", "created_at", "updated_at"]
    save_on_top = True
    change_list_template = "blog/admin/post_change_list.html"
    change_form_template = "blog/admin/post_change_form.html"
    view_on_site = False
    fieldsets = (
        ("Write your story", {"fields": ("title", "body", "excerpt")}),
        ("Cover image", {"fields": ("cover_image", "cover_alt")}),
        ("Publishing", {"fields": ("status", "published_at", "public_link")}),
        (
            "Google and sharing (SEO)",
            {"fields": ("seo_title", "meta_description", "slug", "focus_keyword", "noindex")},
        ),
        ("Details", {"classes": ("collapse",), "fields": ("author", "created_at", "updated_at")}),
    )

    class Media:
        css = {"all": ("blog/admin_seo.css",)}
        js = ("blog/admin_seo.js",)

    @admin.display(description="State", ordering="status")
    def state_badge(self, obj):
        colours = {"Live": "#2e7d32", "Scheduled": "#b26a00", "Draft": "#6b6b6b"}
        return format_html(
            '<strong style="color:{}">{}</strong>', colours[obj.state], obj.state
        )

    @admin.display(description="Link to the post")
    def public_link(self, obj):
        if not obj or not obj.pk:
            return "Save the post first, then a link to it appears here."
        try:
            url = obj.get_absolute_url()
        except NoReverseMatch:  # e.g. opened from the staff-app domain
            url = f"https://tandemretreat.com/blog/{obj.slug}/"
        note = "" if obj.is_live else " (drafts and scheduled posts: only signed-in staff can open it)"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open the post</a>{}', url, note)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            fields.append("author")
        return fields

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)
