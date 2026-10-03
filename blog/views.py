from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .models import Post

POSTS_PER_PAGE = 9


def home(request):
    latest = Post.objects.live()[:3]
    return render(request, "blog/home.html", {"latest_posts": latest})


def post_list(request):
    paginator = Paginator(Post.objects.live(), POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "blog/post_list.html", {"page_obj": page_obj})


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug)
    is_preview = not post.is_live
    # Drafts and scheduled posts are visible only to signed-in staff who may view posts.
    if is_preview and not (request.user.is_authenticated and request.user.has_perm("blog.view_post")):
        raise Http404
    related = Post.objects.live().exclude(pk=post.pk)[:3]
    return render(
        request,
        "blog/post_detail.html",
        {"post": post, "related_posts": related, "is_preview": is_preview},
    )


def writer_guide(request):
    """Staff-only how-to for writers (sign-in required, kept out of Google)."""
    if not (request.user.is_authenticated and request.user.has_perm("blog.view_post")):
        return redirect_to_login(request.get_full_path(), reverse("admin:login"))
    return render(request, "blog/writer_guide.html")
