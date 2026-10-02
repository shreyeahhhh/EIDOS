"""Real-network tests of ``web/fetch``: an explicit opt-in, excluded from the default run (decisions.md D-238).

They make real outbound HTTPS requests with the real resolver and the real TLS connection, and never run unless selected with ``-m web_fetch``. When selected they never skip: a missing network is a
failure that says so, because an opt-in that silently did nothing would look like a pass (CLAUDE.md section 6). What they prove is what no scripted test can: that the resolver, the pinned
connection and TLS verification work together against the real internet, and that a public name which points at a private address is refused by the real resolver. They assert nothing about any
site's content beyond the one stable page they fetch.

    python -m pytest -m web_fetch -s tests/integration/tools/test_web_fetch_real.py
"""

import time

import pytest

from eidos.tools.safe_https import FetchError, fetch

pytestmark = pytest.mark.web_fetch


def deadline() -> float:
    return time.monotonic() + 40


def test_a_real_public_page_is_fetched_over_a_verified_connection_to_a_checked_address():
    page = fetch("https://example.com/", deadline=deadline())
    assert page.content_type == "text/html" and b"Example Domain" in page.body


def test_a_real_page_through_the_tool_becomes_a_source_labelled_document():
    from eidos.agents import ToolArgument, ToolRequest, ToolResult
    from eidos.tools import WEB_FETCH_TOOL_ID, WebFetchTool

    request = ToolRequest(tool_id=WEB_FETCH_TOOL_ID, arguments=(ToolArgument(name="query", value="Read https://example.com/ please"),), timeout_seconds=40, max_result_bytes=49_152)
    outcome = WebFetchTool().call(request)
    assert isinstance(outcome, ToolResult), outcome
    (document,) = outcome.documents
    assert document.content.startswith("URL: https://example.com/\n\n") and "Example Domain" in document.content


@pytest.mark.parametrize("url", ["https://localtest.me/", "https://127.0.0.1.nip.io/"])
def test_a_real_public_name_that_points_at_this_machine_is_refused_by_the_real_resolver(url):
    with pytest.raises(FetchError) as caught:
        fetch(url, deadline=deadline())
    assert caught.value.kind == "refused", caught.value.message  # "unreachable" would mean the lookup failed, not that the protection worked


@pytest.mark.parametrize("url", ["https://169.254.169.254/latest/meta-data/", "https://127.0.0.1/", "https://[::1]/", "http://example.com/", "https://localhost/"])
def test_addresses_that_could_reach_this_network_or_are_not_https_are_refused_before_any_lookup(url):
    with pytest.raises(FetchError) as caught:
        fetch(url, deadline=deadline())
    assert caught.value.kind == "refused"


def test_a_certificate_that_does_not_verify_is_never_accepted():
    with pytest.raises(FetchError) as caught:
        fetch("https://expired.badssl.com/", deadline=deadline())
    assert caught.value.kind == "unreachable" and "certificate" in caught.value.message


def test_a_page_that_is_not_text_is_refused():
    with pytest.raises(FetchError) as caught:
        fetch("https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", deadline=deadline())
    assert caught.value.kind == "unsupported"
