"""The fetcher that must never reach this deployment's own network (decisions.md D-238).

Every test runs without a network: the resolver and the connection are replaced by scripted ones that record exactly what they were asked, so the tests can prove not only what is refused but
that a refused address is never connected to. What is held: only https, the standard port, no credentials in the address; only real public host names (no IP in any spelling); every resolved
address must be public or the whole name is refused; the connection goes to the checked address, not the name; every redirect is revalidated and bounded; time and size are bounded; only text is
accepted and nothing compressed.
"""

import time

import pytest

from eidos.tools.safe_https import (
    MAX_REDIRECTS,
    FetchError,
    RawResponse,
    check_url,
    fetch,
    is_public_address,
    resolve_host,
)

PUBLIC_A = "93.184.216.34"
PUBLIC_B = "2606:2800:220:1:248:1893:25c8:1946"


def later(seconds: float = 30.0) -> float:
    return time.monotonic() + seconds


def refused(url: str) -> FetchError:
    with pytest.raises(FetchError) as caught:
        check_url(url)
    assert caught.value.kind == "refused"
    return caught.value


# --- the address itself ----------------------------------------------------------------------------------------------------------


def test_an_ordinary_https_address_is_accepted_and_split_into_host_and_target():
    assert check_url("https://Example.COM/a/b?x=1#frag") == ("example.com", "/a/b?x=1")
    assert check_url("https://example.com") == ("example.com", "/")
    assert check_url("https://example.com:443/") == ("example.com", "/")
    assert check_url("https://sub.my-site.co.uk/page") == ("sub.my-site.co.uk", "/page")
    assert check_url("https://bücher.example/") == ("xn--bcher-kva.example", "/")


def test_non_ascii_text_in_the_path_is_percent_encoded_not_a_crash_and_existing_escapes_are_kept():
    assert check_url("https://example.com/café?q=ü")[1] == "/caf%C3%A9?q=%C3%BC"
    assert check_url("https://example.com/a%20b/%C3%A9")[1] == "/a%20b/%C3%A9"  # not encoded twice
    assert check_url("https://example.com/日本語")[1] == "/%E6%97%A5%E6%9C%AC%E8%AA%9E"
    assert check_url("https://example.com/a/b;c=d,e?x=1&y=2")[1] == "/a/b;c=d,e?x=1&y=2"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",  # not https
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
        "//example.com/",
        "example.com/",
        "https://user:pass@example.com/",  # credentials in the address
        "https://user@example.com/",
        "https://example.com:8080/",  # not the standard port
        "https://example.com:22/",
        "https://example.com:99999/",
        "https://",
        "https:///path",
        "https://example.com/pa th",
        "https://example.com/a\r\nHost: evil.example",
        "https://example.com/" + "a" * 3000,
    ],
)
def test_a_url_that_is_not_plain_https_to_the_standard_port_is_refused(url):
    refused(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/",
        "https://10.0.0.5/",
        "https://169.254.169.254/latest/meta-data/",  # a cloud metadata service
        "https://192.168.1.1/",
        "https://[::1]/",
        "https://[::ffff:127.0.0.1]/",
        "https://[fe80::1]/",
        "https://2130706433/",  # 127.0.0.1 as one decimal number
        "https://0x7f.0.0.1/",  # hexadecimal
        "https://0177.0.0.1/",  # octal
        "https://127.1/",
        "https://localhost/",
        "https://localhost:443/",
        "https://intranet/",  # a single-word name
        "https://eidos-backend/",  # a name on a private network
        "https://metadata.google.internal/",
        "https://printer.local/",
        "https://app.localhost/",
        "https://router.home.arpa/",
    ],
)
def test_an_ip_address_in_any_spelling_and_a_local_or_single_word_name_is_refused(url):
    refused(url)


# --- where a name leads ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "2001:4860:4860::8888",
        "::ffff:8.8.8.8",  # an IPv4-mapped *public* address is still public
        "64:ff9b::6812:1613", "64:ff9b::808:808",  # DNS64: a public IPv4 host (104.18.22.19, 8.8.8.8) as a network that only speaks IPv6 sees it
    ],
)
def test_public_addresses_are_public(address):
    assert is_public_address(address) is True


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "127.255.255.254", "0.0.0.0", "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.255", "192.168.0.1",
        "169.254.169.254", "169.254.0.1",  # link-local, including the metadata service
        "100.64.0.1", "100.127.255.255",  # carrier-grade NAT: where some providers' private networks live
        "192.0.0.1", "192.0.2.1", "198.18.0.1", "198.51.100.1", "203.0.113.1",  # protocol, documentation and benchmarking blocks
        "224.0.0.1", "239.255.255.255", "240.0.0.1", "255.255.255.255",  # multicast, reserved, broadcast
        "::1", "::", "::7f00:1",  # loopback, unspecified, an IPv4-compatible form of 127.0.0.1
        "fe80::1", "fc00::1", "fd12:3456:789a::1",  # link-local and unique-local
        "ff02::1",  # multicast
        "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "::ffff:192.168.1.1",  # an IPv4 private address written as IPv6
        "64:ff9b::7f00:1", "64:ff9b::a9fe:a9fe", "64:ff9b:1::1",  # NAT64: reaches the IPv4 address inside it
        "2002:7f00:1::", "2002:0a00:1::",  # 6to4 wrapping 127.0.0.1 and 10.0.0.1
        "2001::1",  # Teredo
        "2001:db8::1",  # documentation
        "not-an-address", "", "999.1.1.1", "1.2.3",
    ],
)
def test_every_private_reserved_or_disguised_address_is_not_public(address):
    assert is_public_address(address) is False


@pytest.mark.parametrize(
    "address",
    ["64:ff9b::7f00:1", "64:ff9b::a9fe:a9fe", "64:ff9b:1::1", "2002:7f00:1::", "2002:0a00:1::", "2001::1", "::1", "::7f00:1", "::"],
)
def test_the_disguised_ipv6_forms_are_refused_by_this_module_even_if_the_standard_library_calls_them_global(monkeypatch, address):
    # The stdlib's classification of these ranges has changed between Python patch versions; the container may not run the interpreter these tests do.
    import ipaddress

    monkeypatch.setattr(ipaddress.IPv6Address, "is_global", property(lambda self: True))
    monkeypatch.setattr(ipaddress.IPv6Address, "is_multicast", property(lambda self: False))
    assert is_public_address(address) is False


def scripted_resolver(*addresses: str):
    asked: list[str] = []

    def resolver(host, deadline):
        asked.append(host)
        return list(addresses)

    resolver.asked = asked  # type: ignore[attr-defined]
    return resolver


class Opener:
    """A connection that records exactly which address it was told to connect to, and what it was asked for."""

    def __init__(self, *responses: RawResponse | FetchError):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, host, address, target, deadline, max_bytes):
        self.calls.append((host, address, target))
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, FetchError):
            raise item
        return item


def page(body: bytes = b"<p>hello</p>", content_type: str = "text/html; charset=utf-8", **headers) -> RawResponse:
    return RawResponse(200, {"content-type": content_type, **headers}, body)


def redirect(location: str, status: int = 302) -> RawResponse:
    return RawResponse(status, {"location": location}, b"")


def test_a_name_that_resolves_to_a_private_address_is_refused_and_never_connected_to():
    for private in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "::ffff:127.0.0.1", "192.168.0.10"):
        opener = Opener(page())
        with pytest.raises(FetchError) as caught:
            fetch("https://rebind.example.com/", deadline=later(), resolver=scripted_resolver(private), opener=opener)
        assert caught.value.kind == "refused"
        assert opener.calls == []  # not one connection attempt
        assert private not in caught.value.message  # the message does not describe this network to whoever typed the URL


def test_one_private_address_among_public_ones_refuses_the_whole_name():
    opener = Opener(page())
    with pytest.raises(FetchError) as caught:
        fetch("https://mixed.example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A, "10.0.0.7", PUBLIC_B), opener=opener)
    assert caught.value.kind == "refused" and opener.calls == []


def test_the_connection_goes_to_the_address_that_was_checked_never_to_the_name():
    resolver, opener = scripted_resolver(PUBLIC_A), Opener(page())
    result = fetch("https://example.com/docs?page=2", deadline=later(), resolver=resolver, opener=opener)
    assert resolver.asked == ["example.com"]  # resolved exactly once
    assert opener.calls == [("example.com", PUBLIC_A, "/docs?page=2")]  # the literal address, with the name only for TLS and the Host header
    assert result.body == b"<p>hello</p>" and result.content_type == "text/html" and result.charset == "utf-8"


def test_a_public_host_on_a_dns64_network_is_fetched_and_a_private_one_wrapped_the_same_way_is_not():
    opener = Opener(page())
    result = fetch("https://portfolio.example.com/", deadline=later(), resolver=scripted_resolver("64:ff9b::d818:3912", "216.24.57.18"), opener=opener)
    assert result.body and opener.calls[0][1] == "64:ff9b::d818:3912"  # reached through the translator, as the network intends
    blocked = Opener(page())
    with pytest.raises(FetchError) as caught:
        fetch("https://evil.example.com/", deadline=later(), resolver=scripted_resolver("64:ff9b::a00:1", PUBLIC_A), opener=blocked)  # 10.0.0.1 inside the NAT64 prefix
    assert caught.value.kind == "refused" and blocked.calls == []


def test_an_address_that_does_not_answer_falls_back_to_another_checked_address_and_nothing_else():
    opener = Opener(FetchError("unreachable", "no route"), page())
    result = fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_B, PUBLIC_A), opener=opener)
    assert [call[1] for call in opener.calls] == [PUBLIC_B, PUBLIC_A] and result.body


def test_a_name_that_does_not_resolve_is_unreachable_not_a_success():
    with pytest.raises(FetchError) as caught:
        fetch("https://nowhere.example.com/", deadline=later(), resolver=scripted_resolver(), opener=Opener(page()))
    assert caught.value.kind == "unreachable"


# --- redirects --------------------------------------------------------------------------------------------------------------------


def test_a_redirect_is_followed_by_hand_and_the_new_address_is_checked_again_from_the_start():
    resolver, opener = scripted_resolver(PUBLIC_A), Opener(redirect("/new/place"), page())
    result = fetch("https://example.com/old", deadline=later(), resolver=resolver, opener=opener)
    assert result.requested == "https://example.com/old" and result.url == "https://example.com/new/place"
    assert [call[2] for call in opener.calls] == ["/old", "/new/place"]
    assert resolver.asked == ["example.com", "example.com"]  # resolved and checked again for the new request


@pytest.mark.parametrize(
    "location",
    [
        "http://example.com/downgrade",  # https to http
        "https://127.0.0.1/",
        "https://169.254.169.254/latest/meta-data/",
        "https://localhost/admin",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
        "ftp://example.com/",
        "javascript:alert(1)",
        "file:///etc/passwd",
    ],
)
def test_a_redirect_to_anywhere_that_could_not_be_fetched_directly_is_refused(location):
    opener = Opener(redirect(location), page())
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/start", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=opener)
    assert caught.value.kind == "refused"
    assert len(opener.calls) == 1  # the first page was asked for; the place it pointed at was not


def test_a_redirect_to_a_name_that_now_resolves_privately_is_refused_before_connecting():
    answers = iter([[PUBLIC_A], ["10.0.0.9"]])
    opener = Opener(redirect("https://sneaky.example.com/"), page())
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/", deadline=later(), resolver=lambda host, deadline: next(answers), opener=opener)
    assert caught.value.kind == "refused" and len(opener.calls) == 1


def test_a_redirect_loop_stops_at_the_bound():
    opener = Opener(redirect("/again"))
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=opener)
    assert caught.value.kind == "refused" and len(opener.calls) == MAX_REDIRECTS + 1


def test_a_redirect_that_says_nowhere_is_an_error_not_a_page():
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=Opener(RawResponse(302, {}, b"")))
    assert caught.value.kind == "http_status"


# --- the answer -------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 429, 500, 502, 503])
def test_an_error_status_is_a_failure_that_names_the_status(status):
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=Opener(RawResponse(status, {}, b"")))
    assert caught.value.kind == "http_status" and str(status) in caught.value.message


@pytest.mark.parametrize(
    "content_type",
    ["application/pdf", "image/png", "video/mp4", "application/octet-stream", "application/zip", "text/event-stream", "multipart/form-data", ""],
)
def test_only_text_json_xml_and_html_are_accepted(content_type):
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=Opener(page(content_type=content_type)))
    assert caught.value.kind == "unsupported"


@pytest.mark.parametrize("content_type", ["text/html", "text/plain; charset=iso-8859-1", "application/json", "TEXT/HTML; Charset=UTF-8", "text/markdown", "application/xhtml+xml"])
def test_the_accepted_types_are_accepted(content_type):
    assert fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=Opener(page(content_type=content_type))).body


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "compress"])
def test_a_compressed_answer_is_refused_because_nothing_is_decompressed(encoding):
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=Opener(page(**{"content-encoding": encoding})))
    assert caught.value.kind == "unsupported"


def test_an_identity_encoding_is_fine():
    assert fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A), opener=Opener(page(**{"content-encoding": "identity"}))).body


def test_the_opener_is_told_the_byte_cap_and_the_deadline():
    seen = {}

    def opener(host, address, target, deadline, max_bytes):
        seen.update(deadline=deadline, max_bytes=max_bytes)
        return page()

    deadline = later(5)
    fetch("https://example.com/", deadline=deadline, max_bytes=1234, resolver=scripted_resolver(PUBLIC_A), opener=opener)
    assert seen == {"deadline": deadline, "max_bytes": 1234}


def test_a_too_large_page_is_refused_not_truncated():
    opener = Opener(FetchError("too_large", "the page is larger than 512 KB"), page())
    with pytest.raises(FetchError) as caught:
        fetch("https://example.com/", deadline=later(), resolver=scripted_resolver(PUBLIC_A, PUBLIC_B), opener=opener)
    assert caught.value.kind == "too_large" and len(opener.calls) == 1  # a size failure is not retried on the next address, which would only download it again


# --- time -------------------------------------------------------------------------------------------------------------------------


def test_a_deadline_that_has_passed_stops_the_resolver_before_any_lookup():
    with pytest.raises(FetchError) as caught:
        resolve_host("example.com", time.monotonic() - 1)
    assert caught.value.kind == "timeout"


def test_a_resolver_that_never_answers_is_cut_off_by_the_deadline(monkeypatch):
    import threading

    import eidos.tools.safe_https as module

    release = threading.Event()
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args, **kwargs: release.wait(5) or [])
    started = time.monotonic()
    with pytest.raises(FetchError) as caught:
        resolve_host("slow.example.com", time.monotonic() + 0.2)
    release.set()
    assert caught.value.kind == "timeout" and time.monotonic() - started < 2


def test_a_resolver_failure_is_unreachable(monkeypatch):
    import socket

    import eidos.tools.safe_https as module

    def fail(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(module.socket, "getaddrinfo", fail)
    with pytest.raises(FetchError) as caught:
        resolve_host("nosuch.example.com", later())
    assert caught.value.kind == "unreachable"


def test_the_resolver_returns_each_address_once_without_a_scope_id(monkeypatch):
    import socket

    import eidos.tools.safe_https as module

    infos = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (PUBLIC_B, 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_A, 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_A, 443)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1%eth0", 443, 0, 2)),
    ]
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args, **kwargs: infos)
    assert resolve_host("example.com", later()) == [PUBLIC_B, PUBLIC_A, "fe80::1"]  # the scope id is stripped, so the link-local address is recognised and the name refused later
