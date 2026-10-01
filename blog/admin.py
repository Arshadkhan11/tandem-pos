from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "author", "published_at", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title", "excerpt"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("title", "slug", "status", "author")}),
        ("Content", {"fields": ("cover_image", "excerpt", "body")}),
        ("SEO", {"fields": ("meta_description",)}),
        ("Dates", {"fields": ("published_at", "created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)
