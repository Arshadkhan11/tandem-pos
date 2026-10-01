from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import Post

POSTS_PER_PAGE = 9


def home(request):
    latest = Post.objects.filter(status=Post.STATUS_PUBLISHED)[:3]
    return render(request, "blog/home.html", {"latest_posts": latest})


def post_list(request):
    published = Post.objects.filter(status=Post.STATUS_PUBLISHED)
    paginator = Paginator(published, POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "blog/post_list.html", {"page_obj": page_obj})


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, status=Post.STATUS_PUBLISHED)
    related = Post.objects.filter(status=Post.STATUS_PUBLISHED).exclude(pk=post.pk)[:3]
    return render(request, "blog/post_detail.html", {"post": post, "related_posts": related})
