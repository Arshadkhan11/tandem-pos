from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Post

TEST_SETTINGS = dict(
    ROOT_URLCONF="tandem.urls_site",
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)


@override_settings(**TEST_SETTINGS)
class PostModelTests(TestCase):
    def test_slug_auto_generated_from_title(self):
        post = Post.objects.create(title="Best Sunset Spots Near Nandi Hills", body="<p>hi</p>")
        self.assertEqual(post.slug, "best-sunset-spots-near-nandi-hills")

    def test_published_at_set_on_publish(self):
        post = Post.objects.create(title="A Post", body="<p>x</p>", status=Post.STATUS_DRAFT)
        self.assertIsNone(post.published_at)
        post.status = Post.STATUS_PUBLISHED
        post.save()
        self.assertIsNotNone(post.published_at)

    def test_reading_time_strips_html_and_counts_words(self):
        body = "<p>" + ("word " * 400) + "</p>"
        post = Post.objects.create(title="Long Post", body=body)
        self.assertEqual(post.reading_time_minutes(), 2)


@override_settings(**TEST_SETTINGS)
class PostViewTests(TestCase):
    def setUp(self):
        self.published = Post.objects.create(
            title="Things To Do Near Nandi Hills",
            body="<p>Great views.</p>",
            excerpt="A short guide.",
            status=Post.STATUS_PUBLISHED,
        )
        self.draft = Post.objects.create(
            title="Unpublished Draft",
            body="<p>Not ready.</p>",
            status=Post.STATUS_DRAFT,
        )

    def test_home_shows_only_published_posts(self):
        r = Client().get(reverse("site_home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Things To Do Near Nandi Hills")
        self.assertNotContains(r, "Unpublished Draft")

    def test_post_list_shows_only_published_posts(self):
        r = Client().get(reverse("post_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Things To Do Near Nandi Hills")
        self.assertNotContains(r, "Unpublished Draft")

    def test_published_post_detail_is_reachable(self):
        r = Client().get(self.published.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Great views.")

    def test_draft_post_detail_is_not_reachable(self):
        r = Client().get(reverse("post_detail", args=[self.draft.slug]))
        self.assertEqual(r.status_code, 404)


@override_settings(**TEST_SETTINGS)
class PostAdminTests(TestCase):
    def test_admin_sets_author_automatically(self):
        staff = User.objects.create_superuser("blogadmin", "a@example.com", "pw12345")
        c = Client()
        c.force_login(staff)
        r = c.post(
            reverse("admin:blog_post_add"),
            {
                "title": "New Post",
                "slug": "",
                "status": Post.STATUS_DRAFT,
                "excerpt": "",
                "body": "<p>hello</p>",
                "meta_description": "",
                "published_at_0": "", "published_at_1": "",
            },
        )
        post = Post.objects.get(title="New Post")
        self.assertEqual(post.author, staff)
