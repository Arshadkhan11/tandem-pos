from django.conf import settings
from django.core.files.storage import FileSystemStorage


class InlineImageStorage(FileSystemStorage):
    """Where images dropped into the editor are saved: media/blog/inline/.

    Keeping every blog upload under media/blog/ lets the web server publish just that
    folder and nothing else in media/ (for example the UPI QR image)."""

    def __init__(self, *args, **kwargs):
        kwargs["location"] = settings.MEDIA_ROOT / "blog" / "inline"
        kwargs["base_url"] = settings.MEDIA_URL + "blog/inline/"
        super().__init__(*args, **kwargs)
