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


class StaticReferenceTests(TestCase):
    """A {% static %} tag pointing at a missing file crashes the page in production
    (ManifestStaticFilesStorage raises). Catch that before it ships."""

    def test_every_static_reference_in_templates_exists(self):
        import re
        from pathlib import Path

        from django.conf import settings
        from django.contrib.staticfiles import finders

        pattern = re.compile(r"""{%\s*static\s+['"]([^'"]+)['"]\s*%}""")
        missing = []
        for template in Path(settings.BASE_DIR).glob("*/templates/**/*.html"):
            for ref in pattern.findall(template.read_text()):
                if finders.find(ref) is None:
                    missing.append(f"{template.relative_to(settings.BASE_DIR)} -> {ref}")
        self.assertEqual(missing, [], "templates reference static files that do not exist")


@override_settings(**TEST_SETTINGS)
class BloggerRoleTests(TestCase):
    """The Blogger role must be able to write posts and must not be able to touch anything else."""

    def setUp(self):
        self.owner = User.objects.create_superuser("owner", "o@example.com", "pw12345")

    def hire(self, username="writer", role="blogger"):
        c = Client()
        c.force_login(self.owner)
        r = c.post(
            reverse("admin:auth_user_add"),
            {
                "username": username,
                "password1": "a-long-Safe-pass-77",
                "password2": "a-long-Safe-pass-77",
                "role": role,
                "display_name": "Asha",
            },
        )
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["adminform"].form.errors)
        return User.objects.get(username=username)

    def login_as(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_blogger_gets_staff_but_not_superuser_and_only_blog_permissions(self):
        user = self.hire()
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        perms = set(user.user_permissions.values_list("codename", flat=True))
        self.assertEqual(perms, {"add_post", "change_post", "view_post"})

    def test_blogger_sees_only_the_blog_in_admin(self):
        user = self.hire()
        r = self.login_as(user).get(reverse("admin:index"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Posts")
        for hidden in ("Orders", "Menu items", "Staff profiles", "Users", "Restaurant settings", "Tables"):
            self.assertNotContains(r, hidden)

    def test_blogger_cannot_open_other_admin_areas(self):
        user = self.hire()
        c = self.login_as(user)
        for name in ("admin:auth_user_changelist", "admin:orders_order_changelist",
                     "admin:orders_menuitem_changelist", "admin:orders_staffprofile_changelist"):
            self.assertEqual(c.get(reverse(name)).status_code, 403, name)

    def test_blogger_can_write_but_not_delete(self):
        user = self.hire()
        c = self.login_as(user)
        r = c.post(
            reverse("admin:blog_post_add"),
            {"title": "My first story", "slug": "", "status": "draft", "body": "<p>Hello</p>",
             "excerpt": "", "cover_alt": "", "seo_title": "", "meta_description": "",
             "focus_keyword": "", "published_at_0": "", "published_at_1": ""},
        )
        self.assertEqual(r.status_code, 302)
        post = Post.objects.get(title="My first story")
        self.assertEqual(post.author, user)
        self.assertEqual(c.get(reverse("admin:blog_post_delete", args=[post.pk])).status_code, 403)

    @override_settings(ROOT_URLCONF="tandem.urls")  # the staff-app login lives on the other site's URLs
    def test_blogger_cannot_log_into_the_restaurant_app(self):
        self.hire()
        r = Client().post("/login/waiter/", {"username": "writer", "password": "a-long-Safe-pass-77"})
        self.assertContains(r, "not a waiter login")

    def test_changing_role_away_from_blogger_removes_access(self):
        user = self.hire()
        profile = user.staff
        profile.role = "waiter"
        profile.save()
        from orders.admin import StaffUserAdmin
        StaffUserAdmin._sync_django_admin_flags(user)
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertEqual(user.user_permissions.count(), 0)

    def test_waiter_still_gets_no_admin_access(self):
        user = self.hire("waiter9", "waiter")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


@override_settings(**TEST_SETTINGS)
class WritersDeskTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        self.now = timezone.now()
        self.future = Post.objects.create(
            title="Scheduled story", body="<p>later</p>", status=Post.STATUS_PUBLISHED,
            published_at=self.now + timedelta(days=2),
        )
        self.draft = Post.objects.create(title="Secret draft", body="<p>wip</p>")
        self.staff = User.objects.create_superuser("boss", "b@example.com", "pw12345")

    def test_scheduled_post_is_hidden_from_visitors_everywhere(self):
        c = Client()
        for url in (reverse("site_home"), reverse("post_list")):
            self.assertNotContains(c.get(url), "Scheduled story")
        self.assertEqual(c.get(self.future.get_absolute_url()).status_code, 404)

    def test_scheduled_post_goes_live_when_its_time_arrives(self):
        from datetime import timedelta
        Post.objects.filter(pk=self.future.pk).update(published_at=self.now - timedelta(minutes=1))
        self.assertContains(Client().get(reverse("post_list")), "Scheduled story")

    def test_staff_can_preview_drafts_and_scheduled_posts_with_noindex(self):
        c = Client()
        c.force_login(self.staff)
        for post in (self.draft, self.future):
            r = c.get(post.get_absolute_url())
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "Only signed-in staff can see this page")
            self.assertContains(r, 'content="noindex, nofollow"')

    def test_seo_fields_reach_the_page(self):
        post = Post.objects.create(
            title="Plain title", body="<p>x</p>", status=Post.STATUS_PUBLISHED,
            seo_title="Sunset Spots Near Nandi Hills | Tandem", meta_description="A short Google description.",
            cover_alt="Orange sky over the hills", noindex=True,
        )
        r = Client().get(post.get_absolute_url())
        self.assertContains(r, "<title>Sunset Spots Near Nandi Hills | Tandem</title>", html=True)
        self.assertContains(r, 'name="description" content="A short Google description."')
        self.assertContains(r, 'content="noindex"')

    def test_duplicate_titles_get_unique_addresses_instead_of_crashing(self):
        a = Post.objects.create(title="Same title", body="<p>a</p>")
        b = Post.objects.create(title="Same title", body="<p>b</p>")
        self.assertNotEqual(a.slug, b.slug)

    def test_write_shortcut_leads_to_the_posts_screen(self):
        r = Client().get("/write/")
        self.assertRedirects(r, reverse("admin:blog_post_changelist"), fetch_redirect_response=False)

    def test_admin_media_files_exist(self):
        from django.contrib.staticfiles import finders
        from blog.admin import PostAdmin
        media = PostAdmin.Media
        for path in list(media.js) + list(media.css["all"]):
            self.assertIsNotNone(finders.find(path), path)


@override_settings(**TEST_SETTINGS)
class WriterGuideTests(TestCase):
    def setUp(self):
        from orders.admin import StaffUserAdmin
        from orders.models import StaffProfile

        self.owner = User.objects.create_superuser("owner2", "o2@example.com", "pw12345")
        self.writer = User.objects.create_user("writer2", password="pw12345")
        StaffProfile.objects.create(user=self.writer, role="blogger", display_name="Asha")
        StaffUserAdmin._sync_django_admin_flags(self.writer)
        self.waiter = User.objects.create_user("waiter2", password="pw12345")
        StaffProfile.objects.create(user=self.waiter, role="waiter", display_name="Wally")
        StaffUserAdmin._sync_django_admin_flags(self.waiter)

    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_guide_needs_sign_in(self):
        r = Client().get(reverse("writer_guide"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("admin:login"), r["Location"])

    def test_waiters_cannot_open_the_guide(self):
        r = self.client_for(self.waiter).get(reverse("writer_guide"))
        self.assertEqual(r.status_code, 302)

    def test_blogger_and_owner_can_read_it_and_it_stays_out_of_google(self):
        for user in (self.writer, self.owner):
            r = self.client_for(user).get(reverse("writer_guide"))
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "The Tandem Writer")
            self.assertContains(r, "Add images")
            self.assertContains(r, "What helps a post rank on Google")
            self.assertContains(r, 'content="noindex, nofollow"')

    def test_guide_is_linked_from_the_writers_admin_screens(self):
        c = self.client_for(self.writer)
        for url in (reverse("admin:index"), reverse("admin:blog_post_changelist"), reverse("admin:blog_post_add")):
            self.assertContains(c.get(url), 'href="/write/guide/"', msg_prefix=url)

    @override_settings(ROOT_URLCONF="tandem.urls")
    def test_admin_still_works_on_the_staff_app_domain_without_the_guide_link(self):
        r = self.client_for(self.owner).get(reverse("admin:blog_post_changelist"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Writer's guide")

    def test_guide_contents_links_point_at_real_sections(self):
        import re
        html = self.client_for(self.owner).get(reverse("writer_guide")).content.decode()
        targets = set(re.findall(r'href="#([a-z]+)"', html))
        ids = set(re.findall(r'id="([a-z]+)"', html))
        self.assertTrue(targets)
        self.assertEqual(targets - ids, set())

    def test_guide_html_has_no_unclosed_or_mismatched_tags(self):
        from html.parser import HTMLParser

        void = {"br", "hr", "img", "meta", "link", "input", "source", "col", "area", "base", "embed", "param", "track", "wbr"}

        class Balance(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack, self.errors = [], []

            def handle_starttag(self, tag, attrs):
                if tag not in void:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if tag in void:
                    return
                if not self.stack or self.stack[-1] != tag:
                    self.errors.append("unexpected </%s> after %s" % (tag, self.stack[-3:]))
                else:
                    self.stack.pop()

        p = Balance()
        p.feed(self.client_for(self.owner).get(reverse("writer_guide")).content.decode())
        self.assertEqual(p.errors, [])
        self.assertEqual(p.stack, [])


@override_settings(**TEST_SETTINGS)
class StaleLoginFormTests(TestCase):
    """A stale/expired login form must give a friendly retry, never a server error."""

    def test_stale_admin_login_form_reloads_the_page_with_a_message(self):
        c = Client(enforce_csrf_checks=True)
        url = reverse("admin:login") + "?next=/django-admin/blog/post/"
        r = c.post(url, {"username": "nobody", "password": "x"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], url)
        again = c.get(r["Location"])
        self.assertEqual(again.status_code, 200)
        self.assertContains(again, "Session expired")

    @override_settings(ROOT_URLCONF="tandem.urls")
    def test_restaurant_app_still_redirects_stale_logins_to_its_own_login_page(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/login/chef/", {"username": "nobody", "password": "x"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/login/chef/")
