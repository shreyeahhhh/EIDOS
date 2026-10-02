"""What a provider said when it refused a call (decisions.md D-242).

A bare "the provider answered HTTP status 404" cannot be acted on: a model name the account cannot use, a wrong base URL, a model that was never pulled and a deprecated model all look the same. Both
providers say which in the body of the answer (``{"error": {"message": "The model ``x`` does not exist ..."}}`` for Groq, ``{"error": "model 'x' not found"}`` for Ollama), so the message carries that
explanation, cut to a fixed length and with any secret removed. Nothing here can fail: a body that is missing, is not JSON or has no message gives the plain status line exactly as before.
"""

import json
import urllib.error

MAX_DETAIL_CHARS = 200
_READ_BYTES = 16_384  # a provider's error is a sentence or two; a body larger than this is cut, cannot be parsed, and gives the plain status line


def http_failure_message(prefix: str, error: urllib.error.HTTPError, *, secrets: tuple[str, ...] = ()) -> str:
    """``"<prefix> HTTP status <code>"``, followed by ``": <the provider's own message>"`` when it gave one. Each of ``secrets`` that appears in that message is replaced by ``[redacted]``."""
    plain = f"{prefix} HTTP status {error.code}"
    try:
        document = json.loads(error.read(_READ_BYTES).decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — an unreadable error body is not a reason to lose the status that was already known
        return plain
    detail = None
    if isinstance(document, dict):
        reported = document.get("error")
        if isinstance(reported, dict):
            reported = reported.get("message")
        if isinstance(reported, str):
            detail = reported
    if detail is None or not detail.strip():
        return plain
    detail = " ".join(detail.split())
    for secret in secrets:
        if secret:
            detail = detail.replace(secret, "[redacted]")
    if len(detail) > MAX_DETAIL_CHARS:
        detail = detail[: MAX_DETAIL_CHARS - 1] + "…"
    return f"{plain}: {detail}"
