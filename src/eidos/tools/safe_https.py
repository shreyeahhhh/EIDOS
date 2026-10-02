"""Fetch one public web page over HTTPS in a way that cannot be turned against this deployment's own network (decisions.md D-238).

A deployment that fetches a URL a user typed is a deployment that can be told to fetch ``https://169.254.169.254/`` (a cloud metadata service), ``https://localhost:8000/`` (its own API), an
address on its provider's private network, or a public name that an attacker's DNS makes point at any of those. Everything here exists to make that impossible, and each rule is a refusal, never a
repair: a URL is fetched exactly as given or not at all.

What is enforced, in this order, for the URL and again for every redirect it leads to:

1. **https only, the standard port only, no user name or password in the address.**
2. **A real public host name only.** An IP address in any spelling (``127.0.0.1``, ``2130706433``, ``0x7f.1``, ``[::1]``) is refused: the name must have at least one dot and a letter-only (or
   ``xn--``) top-level label, and must not end in a local-only suffix (``.local``, ``.internal``, ...).
3. **Every address the name resolves to must be public.** If *any* of them is loopback, private, link-local, carrier-grade NAT, multicast, reserved, an IPv4-mapped or NAT64 or 6to4 or Teredo
   form of one of those, the whole name is refused. (A host that mixes public and private records is exactly what a DNS-rebinding attacker serves.)
4. **The connection goes to the address that was just checked, not to the name.** The name is resolved once; the socket is opened to that literal address, and TLS verifies the certificate against
   the *name*. A second lookup cannot return a different answer, so there is no window between checking and connecting. (On a DNS64 network an IPv4-only host resolves to a ``64:ff9b::`` address;
   that is judged by the IPv4 address inside it, so a public site still works and a private one wrapped that way is still refused.)
5. **Redirects are followed by hand, at most three, each one validated from step 1.** A redirect to ``http://``, to an IP, to a private name, or to a name that now resolves privately is refused.
6. **Bounded in time and size.** One deadline covers DNS, every connection and every read; the body is read in chunks up to a byte cap and a larger page is refused (not truncated). Nothing is
   decompressed (``Accept-Encoding: identity``) so a compression bomb cannot be sent; a compressed answer is refused.
7. **Text only.** Only text, JSON, XML and HTML content types are accepted.

The request carries no cookie, no credential, no caller header and no proxy setting (``http.client`` does not read proxy variables); ``GET`` is the only method. Standard library only; no
environment is read here, no file is touched and nothing is logged.
"""

import http.client
import ipaddress
import re
import socket
import ssl
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

MAX_URL_CHARS = 2048
MAX_REDIRECTS = 3
MAX_DOWNLOAD_BYTES = 524_288
MAX_ADDRESSES_TRIED = 4
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 15.0
DNS_TIMEOUT_SECONDS = 10.0
USER_AGENT = "EIDOS-web-fetch/1 (read-only; sends no credentials)"

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
TEXT_CONTENT_TYPES = frozenset({
    "text/html", "text/plain", "text/markdown", "text/css", "text/csv", "text/xml", "text/javascript",
    "application/json", "application/xml", "application/xhtml+xml", "application/javascript",
})
LOCAL_ONLY_SUFFIXES = (".local", ".localhost", ".internal", ".localdomain", ".home.arpa", ".lan", ".intranet", ".corp")

_HOST = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$")
_UNSAFE_IN_TARGET = re.compile(r"[\x00-\x20\x7f]")
_NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")  # RFC 6052: a translator forwards to the IPv4 address in the last 32 bits, which is therefore the address that matters
_RESERVED_LOW_V6 = ipaddress.ip_network("::/8")  # ::, ::1, the IPv4-compatible forms and the local-use NAT64 prefix 64:ff9b:1::/48 (it begins with a zero byte): IANA reserves the whole block


class FetchError(Exception):
    """A page that was not fetched, and why. ``kind`` is one of ``refused``, ``unreachable``, ``timeout``, ``too_large``, ``unsupported``, ``http_status``; the message is safe to show and
    never contains an address the name resolved to (that would describe this deployment's network to whoever typed the URL)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind, self.message = kind, message


@dataclass(frozen=True, slots=True)
class RawResponse:
    status: int
    headers: dict[str, str]  # names lower-case
    body: bytes


@dataclass(frozen=True, slots=True)
class Page:
    requested: str
    url: str  # where the page was finally read from (after any redirects)
    content_type: str  # the media type, lower-case, no parameters
    charset: str | None
    body: bytes


Resolver = Callable[[str, float], list[str]]
Opener = Callable[[str, str, str, float, int], RawResponse]  # (host, validated address, request target, deadline, byte cap)


def _remaining(deadline: float, cap: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise FetchError("timeout", "did not finish in time")
    return min(left, cap)


# --- 1 and 2: the address itself ----------------------------------------------------------------------------------------------------


def check_url(url: str) -> tuple[str, str]:
    """``(host, request target)`` for a URL that may be fetched; ``FetchError("refused")`` for every other."""
    if len(url) > MAX_URL_CHARS:
        raise FetchError("refused", "the address is too long")
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        raise FetchError("refused", "this is not a valid web address") from None
    if parts.scheme.lower() != "https":
        raise FetchError("refused", "only https addresses are fetched")
    if "@" in parts.netloc:
        raise FetchError("refused", "an address with a user name or password is not fetched")
    if port not in (None, 443):
        raise FetchError("refused", "only the standard https port is used")
    if not parts.hostname:
        raise FetchError("refused", "the address has no host name")
    try:
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise FetchError("refused", "the host name is not valid") from None
    if not _HOST.fullmatch(host) or host.endswith(LOCAL_ONLY_SUFFIXES):
        raise FetchError("refused", "only public host names are fetched (not an IP address, a single-word name or a local name)")
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    if _UNSAFE_IN_TARGET.search(target):
        raise FetchError("refused", "the address contains characters that cannot be sent")
    return host, urllib.parse.quote(target, safe="%/:@!$&'()*+,;=?~-._")  # non-ASCII text in a path is percent-encoded (an existing %XX is left alone), as a browser would send it


# --- 3: where the name leads --------------------------------------------------------------------------------------------------------


def is_public_address(text: str) -> bool:
    """True only for an address on the public internet. Anything that cannot be parsed, or is a disguised form of a non-public one, is False."""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is 127.0.0.1
        elif ip in _NAT64_WELL_KNOWN:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)  # 64:ff9b::7f00:1 is 127.0.0.1; 64:ff9b::6812:1613 is a public host reached through a DNS64 network
        elif ip.sixtofour is not None or ip.teredo is not None or ip in _RESERVED_LOW_V6:
            return False
    return ip.is_global and not ip.is_multicast


def resolve_host(host: str, deadline: float) -> list[str]:
    """Every address ``host`` resolves to, resolved once and bounded by the deadline (``getaddrinfo`` has no timeout of its own)."""
    allowed = _remaining(deadline, DNS_TIMEOUT_SECONDS)  # before any lookup starts: past the deadline, no query is sent at all
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(socket.getaddrinfo, host, 443, 0, socket.SOCK_STREAM)
        try:
            infos = future.result(timeout=allowed)
        except TimeoutError:
            raise FetchError("timeout", "the host name did not resolve in time") from None
        except OSError:
            raise FetchError("unreachable", "the host name could not be resolved") from None
    finally:
        pool.shutdown(wait=False)  # a resolver that never returns must not hold this call
    seen: dict[str, None] = {}
    for info in infos:
        seen[str(info[4][0]).split("%", 1)[0]] = None
    return list(seen)


def _require_public(addresses: list[str]) -> list[str]:
    if not addresses:
        raise FetchError("unreachable", "the host name did not resolve")
    if not all(is_public_address(address) for address in addresses):
        raise FetchError("refused", "that host name leads to a private or reserved address, so it is not fetched")
    return addresses


# --- 4: the connection --------------------------------------------------------------------------------------------------------------


def open_https(host: str, address: str, target: str, deadline: float, max_bytes: int) -> RawResponse:
    """One GET to the already-checked ``address``, with TLS verified against ``host``. The body is read only for a final answer, in chunks, up to ``max_bytes``."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPSConnection(host, 443, context=context)
    try:
        raw = socket.create_connection((address, 443), timeout=_remaining(deadline, CONNECT_TIMEOUT_SECONDS))
        raw.settimeout(_remaining(deadline, READ_TIMEOUT_SECONDS))
        tls = context.wrap_socket(raw, server_hostname=host)  # the certificate must be the name's; the socket is the checked address's
        connection.sock = tls
        connection.request(
            "GET", target,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,application/json;q=0.8,*/*;q=0.1", "Accept-Encoding": "identity", "Connection": "close"},
        )
        # Set once, before the response: http.client closes its socket as soon as it has read the headers of a "Connection: close" answer, after which the socket cannot be touched. No single read
        # can then wait longer than this, and the deadline is checked between reads, so the call overruns its deadline by at most one read timeout.
        tls.settimeout(_remaining(deadline, READ_TIMEOUT_SECONDS))
        response = connection.getresponse()
        headers = {name.lower(): value for name, value in response.getheaders()}
        if response.status in REDIRECT_STATUSES or not 200 <= response.status < 300:
            return RawResponse(response.status, headers, b"")
        if _media_type(headers)[0] not in TEXT_CONTENT_TYPES or headers.get("content-encoding", "identity").strip().lower() not in ("", "identity"):
            return RawResponse(response.status, headers, b"")  # ``fetch`` refuses it by its headers; a PDF, an image or a compressed body is never downloaded
        declared = headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise FetchError("too_large", f"the page is larger than {max_bytes // 1024} KB")
        body = bytearray()
        while len(body) <= max_bytes:
            _remaining(deadline, READ_TIMEOUT_SECONDS)  # raises once the deadline has passed
            chunk = response.read(min(16_384, max_bytes + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        if len(body) > max_bytes:
            raise FetchError("too_large", f"the page is larger than {max_bytes // 1024} KB")
        return RawResponse(response.status, headers, bytes(body))
    except FetchError:
        raise
    except ssl.SSLCertVerificationError:
        raise FetchError("unreachable", "its certificate could not be verified") from None
    except TimeoutError:
        raise FetchError("timeout", "did not answer in time") from None
    except (OSError, http.client.HTTPException):
        raise FetchError("unreachable", "could not be reached securely") from None
    finally:
        connection.close()


def _first_that_answers(opener: Opener, host: str, addresses: list[str], target: str, deadline: float, max_bytes: int) -> RawResponse:
    failure: FetchError | None = None
    for address in addresses[:MAX_ADDRESSES_TRIED]:
        try:
            return opener(host, address, target, deadline, max_bytes)
        except FetchError as error:
            if error.kind != "unreachable":
                raise
            failure = error  # another of the checked addresses (an IPv6 one on a host with no IPv6 route, say) may answer
    raise failure if failure is not None else FetchError("unreachable", "could not be reached")


# --- 5, 6 and 7: the page -----------------------------------------------------------------------------------------------------------


def _media_type(headers: dict[str, str]) -> tuple[str, str | None]:
    value = headers.get("content-type", "")
    media, _, parameters = value.partition(";")
    match = re.search(r"charset\s*=\s*\"?([A-Za-z0-9._:-]{1,40})", parameters)
    return media.strip().lower(), (match.group(1) if match else None)


def fetch(url: str, *, deadline: float, max_bytes: int = MAX_DOWNLOAD_BYTES, resolver: Resolver = resolve_host, opener: Opener = open_https) -> Page:
    """The page at ``url``, or ``FetchError``. ``deadline`` is a ``time.monotonic()`` reading. ``resolver`` and ``opener`` exist so a test can run this without a network; a real call uses the defaults."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        host, target = check_url(current)
        addresses = _require_public(resolver(host, deadline))
        raw = _first_that_answers(opener, host, addresses, target, deadline, max_bytes)
        if raw.status in REDIRECT_STATUSES:
            location = raw.headers.get("location")
            if not location:
                raise FetchError("http_status", f"the page redirected without saying where (HTTP {raw.status})")
            current = urllib.parse.urljoin(current, location)  # validated from the top on the next pass: a redirect is a new, untrusted URL
            continue
        if not 200 <= raw.status < 300:
            raise FetchError("http_status", f"the page answered HTTP {raw.status}")
        if raw.headers.get("content-encoding", "identity").strip().lower() not in ("", "identity"):
            raise FetchError("unsupported", "the page came compressed, which is not accepted")
        media, charset = _media_type(raw.headers)
        if media not in TEXT_CONTENT_TYPES:
            raise FetchError("unsupported", f"the page is {media or 'of an unknown type'}, not text, HTML or JSON")
        return Page(requested=url, url=current, content_type=media, charset=charset, body=raw.body)
    raise FetchError("refused", f"the address redirected more than {MAX_REDIRECTS} times")
