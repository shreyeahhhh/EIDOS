"""``web/fetch``: the one tool that reads web pages (decisions.md D-238; invariants 3, 12, 14, 16).

It implements the existing ``ToolPort`` (``eidos.agents.tool``), so everything the V1.2 gate already does applies to it unchanged: a call is refused unless the mission itself lists the ``web_fetch``
action, has a tool-call budget and autonomy of at least level 1; the call is recorded as a fact on the node that made it; each page becomes its own citable artifact whose reference names the tool,
the request and the page. **Nothing here is an agent, a plan or a model.**

**What a call is.** The Research agent calls its one tool with the mission goal as ``query`` (``eidos.agents.research``, unchanged). This adapter reads the ``https`` addresses written *in that goal*,
by a fixed pattern, and fetches exactly those: at most three, each through ``safe_https`` (see its rules: public hosts only, a checked address connected to directly, redirects re-validated,
bounded time and size). A goal with no address is a real, empty answer (no network is touched). More than three, or any one that cannot be fetched, is a typed failure that names the address: the call
is all-or-nothing, so a page is never silently left out. **Addresses found inside a fetched page are never followed**: the page is text, and text is data, never an instruction.

**What comes back.** Readable text: for HTML, the title, the meta description and the visible text with scripts, styles and markup removed; for any other accepted type, the text itself. A page whose
script renders its content says so in the document, because EIDOS reads what the server sent and does not run scripts or draw the page. Each document starts with the address it came from, so the
evidence shows its source. A NUL character (PostgreSQL cannot store one) becomes U+FFFD and other control characters are dropped.

It reads no environment, holds no state (so it is thread-safe), opens no file, logs nothing and sends no credential.
"""

import hashlib
import re
import time
import urllib.parse
from html.parser import HTMLParser

from eidos.agents import ToolDocument, ToolFailure, ToolFailureKind, ToolOutcome, ToolRequest, ToolResult
from eidos.capabilities import RESEARCH, ToolArgumentKind, ToolArgumentSpec, ToolDescriptor, ToolRegistry
from eidos.contracts import ActionId

from .safe_https import FetchError, Opener, Page, Resolver, fetch, open_https, resolve_host

WEB_FETCH_ACTION = "web_fetch"
WEB_FETCH_PROVIDER = "web"
WEB_FETCH_TOOL = "fetch"
WEB_FETCH_TOOL_ID = f"{WEB_FETCH_PROVIDER}/{WEB_FETCH_TOOL}"

MAX_ADDRESSES_PER_CALL = 3
MAX_QUERY_CHARS = 2000  # the API's own ceiling on a goal
TIMEOUT_SECONDS = 45.0  # one deadline for the whole call: a free-tier host can take most of a minute to wake
MAX_RESULT_BYTES = 49_152  # the text of every page together (provisional); a model's input is bounded too, and nothing is truncated

# This tool has no remote schema to pin: the digest is of the one argument schema EIDOS itself states, so a change to it is a change to this value.
_INPUT_SCHEMA_DIGEST = hashlib.sha256(f'{{"query":{{"max":{MAX_QUERY_CHARS},"min":1,"type":"string"}}}}'.encode("ascii")).hexdigest()

_ADDRESS = re.compile(r"https?://[^\s<>\"'`\\]+", re.IGNORECASE)
_TRAILING = ".,;:!?)]}>\"'"
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SKIPPED = frozenset({"script", "style", "noscript", "template", "svg", "iframe", "object", "embed", "canvas"})
_BLOCKS = frozenset({
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer", "nav", "main", "aside", "form", "pre", "blockquote",
    "hr", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "details", "summary",
})
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_NOTHING_VISIBLE = "(no readable text was found: the page may build its content with JavaScript, which EIDOS does not run)"


def web_fetch_descriptor() -> ToolDescriptor:
    """The allowlist entry, stated by EIDOS: read-only, the ``web_fetch`` action, one string argument, and the bounds admission hands to every call."""
    return ToolDescriptor(
        provider_id=WEB_FETCH_PROVIDER, tool_name=WEB_FETCH_TOOL, capability=RESEARCH, action_id=ActionId(WEB_FETCH_ACTION), read_only=True,
        arguments=(ToolArgumentSpec(name="query", kind=ToolArgumentKind.STRING, required=True, minimum=1, maximum=MAX_QUERY_CHARS),),
        timeout_seconds=TIMEOUT_SECONDS, max_result_bytes=MAX_RESULT_BYTES, input_schema_digest=_INPUT_SCHEMA_DIGEST,
    )


def web_fetch_registry() -> ToolRegistry:
    return ToolRegistry(tools=(web_fetch_descriptor(),))


def addresses_in(text: str) -> list[str]:
    """The web addresses written in ``text``, in order, once each. ``http://`` ones are included on purpose: they are refused by name rather than silently ignored."""
    found: dict[str, None] = {}
    for match in _ADDRESS.finditer(text):
        found[match.group(0).rstrip(_TRAILING)] = None
    return list(found)


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self.description: str | None = None
        self.scripts = False
        self._skipped = 0
        self._in_title = False

    def _open(self, tag: str, attributes, *, void: bool) -> None:
        if tag == "script":
            self.scripts = True
        if tag in _SKIPPED:
            if not void:
                self._skipped += 1
        elif tag == "title":
            self._in_title = not void
        elif tag == "meta" and self.description is None:
            values = {name: (value or "") for name, value in attributes}
            if values.get("name", "").lower() in ("description", "og:description") or values.get("property", "").lower() == "og:description":
                self.description = values.get("content", "").strip() or None
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, void=False)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, void=True)

    def handle_endtag(self, tag):
        if tag in _SKIPPED:
            self._skipped = max(0, self._skipped - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skipped:
            return
        (self.title if self._in_title else self.parts).append(data)


def _clean(text: str) -> str:
    text = text.replace(chr(0), chr(0xFFFD))
    text = _CONTROL.sub("", text)
    lines = [re.sub(r"[ \t\r\f\v ]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _decode(body: bytes, charset: str | None) -> str:
    for name in (charset, "utf-8"):
        if name:
            try:
                return body.decode(name, errors="replace")
            except (LookupError, TypeError, ValueError):
                continue
    return body.decode("utf-8", errors="replace")


def _readable(page: Page) -> str:
    text = _decode(page.body, page.charset)
    if page.content_type not in _HTML_TYPES:
        return _clean(text)
    parser = _VisibleText()
    parser.feed(text)
    parser.close()
    lines = []
    title = _clean(" ".join(parser.title))
    if title:
        lines.append(f"Title: {title}")
    if parser.description:
        lines.append(f"Description: {_clean(parser.description)}")
    visible = _clean("".join(parser.parts))
    if not visible and parser.scripts:
        visible = _NOTHING_VISIBLE
    elif not visible:
        visible = "(the page has no visible text)"
    return "\n".join(lines) + ("\n\n" if lines else "") + visible


def _document(page: Page) -> ToolDocument:
    final = urllib.parse.urlsplit(page.url)
    host = (final.hostname or "page")[:100]
    header = [f"URL: {page.requested}"]
    if page.url != page.requested:
        header.append(f"Redirected to: https://{final.netloc}{final.path}")  # the query is left out: a redirect can carry a session token the page's owner issued
    digest = hashlib.sha256(page.url.encode("utf-8")).hexdigest()[:10]
    return ToolDocument(document_id=f"{re.sub(r'[^A-Za-z0-9_.-]', '_', host)}-{digest}", content="\n".join(header) + "\n\n" + _readable(page))


_FAILURE_KINDS = {
    "refused": ToolFailureKind.TOOL_ERROR,
    "http_status": ToolFailureKind.TOOL_ERROR,
    "unsupported": ToolFailureKind.TOOL_ERROR,
    "unreachable": ToolFailureKind.UNAVAILABLE,
    "timeout": ToolFailureKind.TIMEOUT,
    "too_large": ToolFailureKind.RESULT_TOO_LARGE,
}


class WebFetchTool:
    """A ``ToolPort``. Stateless, so safe on any number of worker threads; total (it returns a ``ToolFailure``, it does not raise)."""

    def __init__(self, *, resolver: Resolver = resolve_host, opener: Opener = open_https) -> None:
        self._resolver, self._opener = resolver, opener

    def call(self, request: ToolRequest) -> ToolOutcome:
        try:
            return self._call(request)
        except Exception:  # noqa: BLE001 — a tool is total; an unforeseen fault is a typed failure that names no detail
            return ToolFailure(kind=ToolFailureKind.TOOL_ERROR, message="the web fetch failed unexpectedly")

    def _call(self, request: ToolRequest) -> ToolOutcome:
        query = next((argument.value for argument in request.arguments if argument.name == "query"), None)
        if not isinstance(query, str):
            return ToolFailure(kind=ToolFailureKind.TOOL_ERROR, message="the call has no query")
        addresses = addresses_in(query)
        if not addresses:
            return ToolResult(documents=())  # nothing to read; no network is touched
        if len(addresses) > MAX_ADDRESSES_PER_CALL:
            return ToolFailure(
                kind=ToolFailureKind.TOOL_ERROR,
                message=f"the goal names {len(addresses)} web addresses; at most {MAX_ADDRESSES_PER_CALL} are fetched, so none were. Name fewer.",
            )
        deadline = time.monotonic() + request.timeout_seconds
        documents: dict[str, ToolDocument] = {}
        for address in addresses:
            try:
                page = fetch(address, deadline=deadline, resolver=self._resolver, opener=self._opener)
            except FetchError as error:
                return ToolFailure(kind=_FAILURE_KINDS[error.kind], message=f"{address[:200]}: {error.message}")
            document = _document(page)
            documents[document.document_id] = document
        return ToolResult(documents=tuple(documents.values()))
