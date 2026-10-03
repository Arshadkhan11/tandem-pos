import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from django_ckeditor_5.fields import CKEditor5Field


class PostQuerySet(models.QuerySet):
    def live(self):
        """Posts visitors can see: published, and not scheduled for the future."""
        return self.filter(status=Post.STATUS_PUBLISHED, published_at__lte=timezone.now())


class Post(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft (only you can see it)"),
        (STATUS_PUBLISHED, "Published"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(
        "Web address ending",
        max_length=220,
        unique=True,
        blank=True,
        help_text="The last part of the link, e.g. best-sunset-spots-near-nandi-hills. Filled in "
        "from the title; keep it short and include your main keyword.",
    )
    cover_image = models.ImageField(upload_to="blog/covers/", blank=True, null=True)
    cover_alt = models.CharField(
        "Cover image description",
        max_length=140,
        blank=True,
        help_text="Describe the picture in a few words (helps Google Images and screen readers).",
    )
    excerpt = models.CharField(
        "Short summary",
        max_length=300,
        blank=True,
        help_text="One or two sentences shown under the title and on the Journal page.",
    )
    body = CKEditor5Field("Story", config_name="default")
    seo_title = models.CharField(
        "Google title",
        max_length=70,
        blank=True,
        help_text="The blue headline on Google, about 50-60 characters. Leave empty to use the "
        "post title.",
    )
    meta_description = models.CharField(
        "Google description",
        max_length=160,
        blank=True,
        help_text="The grey text under the headline on Google, about 120-155 characters.",
    )
    focus_keyword = models.CharField(
        "Main keyword",
        max_length=80,
        blank=True,
        help_text="The phrase you want this post to rank for. Used by the checklist only; "
        "visitors never see it.",
    )
    noindex = models.BooleanField(
        "Hide from Google",
        default=False,
        help_text="Tick to keep this post out of Google search results.",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    published_at = models.DateTimeField(
        "Publish date and time",
        null=True,
        blank=True,
        help_text="Set a future time to schedule the post. Leave empty to publish immediately.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or "post"
            slug, n = base, 2
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("post_detail", args=[self.slug])

    @property
    def is_live(self):
        return (
            self.status == self.STATUS_PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )

    @property
    def state(self):
        if self.is_live:
            return "Live"
        if self.status == self.STATUS_PUBLISHED:
            return "Scheduled"
        return "Draft"

    @property
    def description(self):
        return self.meta_description or self.excerpt

    def reading_time_minutes(self):
        text = re.sub(r"<[^>]+>", " ", self.body or "")
        words = len(text.split())
        return max(1, round(words / 200))
