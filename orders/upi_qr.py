"""Decode UPI QR images (admin RestaurantSettings helper)."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

_ZBAR_CANDIDATES = (
    Path("/opt/homebrew/lib/libzbar.dylib"),  # Apple Silicon Homebrew
    Path("/usr/local/lib/libzbar.dylib"),
    Path("/usr/lib/x86_64-linux-gnu/libzbar.so.0"),
    Path("/usr/lib/libzbar.so.0"),
)


def _prepare_pyzbar():
    """Return pyzbar.decode, or None if zbar is unavailable."""
    found = None
    for path in _ZBAR_CANDIDATES:
        if path.exists():
            found = path
            break
    if found is not None:
        try:
            ctypes.CDLL(str(found))
        except OSError:
            pass
        libdir = str(found.parent)
        prev = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        if libdir not in prev.split(":"):
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                f"{libdir}:{prev}" if prev else libdir
            )
        # pyzbar's find_library often misses Homebrew — force its loader.
        try:
            from pyzbar import zbar_library

            lib_path = str(found)

            def _load():
                return ctypes.cdll.LoadLibrary(lib_path), []

            zbar_library.load = _load  # type: ignore[method-assign]
        except Exception:
            pass

    try:
        from pyzbar.pyzbar import decode as zbar_decode
        return zbar_decode
    except Exception:
        return None


def parse_upi_uri(data: str) -> dict | None:
    """Extract pa / pn from a upi://pay?... string. Returns None if not UPI."""
    if not data:
        return None
    raw = data.strip()
    if not raw.lower().startswith("upi://"):
        return None
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)
    pa = (qs.get("pa") or [""])[0].strip()
    pn = unquote((qs.get("pn") or [""])[0].strip())
    if not pa:
        return None
    return {"pa": pa, "pn": pn}


def decode_upi_from_image(image_file) -> dict | None:
    """
    Try to read a UPI QR from an uploaded image.
    Returns {"pa", "pn"} or None. Never raises.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    zbar_decode = _prepare_pyzbar()
    if zbar_decode is None:
        return None

    try:
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        img = Image.open(image_file)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        results = zbar_decode(img)
        for result in results:
            data = result.data.decode("utf-8", errors="replace")
            parsed = parse_upi_uri(data)
            if parsed:
                return parsed
    except Exception:
        return None
    finally:
        if hasattr(image_file, "seek"):
            try:
                image_file.seek(0)
            except Exception:
                pass
    return None
