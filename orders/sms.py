"""Fire-and-forget SMS helpers.

Real customer SMS in India needs TRAI DLT registration + a gateway (MSG91/Fast2SMS/etc).
Until SMS_API_KEY is set, messages are logged only so closing a bill never blocks.
"""
from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def _normalize_msisdn(phone: str) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) == 10:
        return digits
    if digits.startswith("91") and len(digits) == 12:
        return digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        return digits[1:]
    return digits


def _send_fast2sms(phone10: str, message: str) -> None:
    api_key = getattr(settings, "SMS_API_KEY", "") or ""
    if not api_key:
        logger.info("SMS skipped (no SMS_API_KEY): to=%s msg=%s", phone10, message)
        return

    # Fast2SMS quick SMS API — requires DLT-approved sender/template in production.
    params = urllib.parse.urlencode({
        "authorization": api_key,
        "route": "q",
        "message": message,
        "numbers": phone10,
        "flash": "0",
    })
    url = f"https://www.fast2sms.com/dev/bulkV2?{params}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            logger.info("SMS sent to=%s status=%s body=%s", phone10, resp.status, body[:200])
    except urllib.error.URLError as exc:
        logger.warning("SMS failed to=%s error=%s", phone10, exc)


def send_sms_async(phone: str, message: str) -> None:
    """Best-effort SMS — never blocks the waiter UI."""
    if not getattr(settings, "SMS_ENABLED", False):
        return
    phone10 = _normalize_msisdn(phone)
    if len(phone10) != 10:
        logger.info("SMS skipped (bad phone): %r", phone)
        return

    thread = threading.Thread(
        target=_send_fast2sms,
        args=(phone10, message),
        daemon=True,
        name="tandem-sms",
    )
    thread.start()
