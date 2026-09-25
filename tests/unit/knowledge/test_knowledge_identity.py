"""Normalisation and every id derivation (decisions.md D-211, D-212; V1.3 Step 2).

Each expected value is restated independently with ``hashlib`` and ``json``, so the tests do not call the code they check to say what it should give.
Every special character is built from its code point, never typed, so no tool that rewrites text can quietly change what a test does.
"""

import hashlib
import inspect
import json
import re

import pytest

from eidos.knowledge import chunk_id_of, document_id_of, evidence_ref_of, is_source_id, normalise_text, snapshot_id_of

E_ACUTE = chr(0xE9)  # e with acute, precomposed
ACUTE = chr(0x301)  # combining acute accent
RING = chr(0x30A)  # combining ring above
A_RING = chr(0xC5)  # A with ring above, precomposed
NBSP = chr(0xA0)
EM_SPACE = chr(0x2003)
BOM = chr(0xFEFF)
LIGATURE_FI = chr(0xFB01)
FULLWIDTH_A = chr(0xFF21)
LONE_SURROGATE = chr(0xD800)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_json(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


# --- normalisation ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("a\r\nb", "a\nb"),
    ("a\rb", "a\nb"),
    ("a\nb", "a\nb"),
    ("a\r\nb\rc\nd", "a\nb\nc\nd"),
    ("a\r\r\nb", "a\n\nb"),
    ("a\r\n\r\nb", "a\n\nb"),
    ("\r\n", "\n"),
    ("", ""),
    ("e" + ACUTE, E_ACUTE),
    (E_ACUTE, E_ACUTE),
    ("A" + RING, A_RING),
])
def test_text_is_nfc_with_every_line_break_read_as_lf(raw, expected):
    assert normalise_text(raw) == expected


@pytest.mark.parametrize("text", [
    "  leading and trailing  ",
    "tab\tinside",
    BOM + "byte order mark kept",
    "trailing newline\n",
    "double  space",
    "non" + NBSP + "breaking" + NBSP + "space",
    "ligature " + LIGATURE_FI + " stays",
    "full" + FULLWIDTH_A + "width",
    EM_SPACE + "em space",
])
def test_nothing_else_is_normalised(text):
    assert normalise_text(text) == text


@pytest.mark.parametrize("text", ["a\r\nb", "e" + ACUTE, "x\ry", "already fine", "", "\r\r\n\n"])
def test_normalisation_is_idempotent(text):
    assert normalise_text(normalise_text(text)) == normalise_text(text)


def test_the_test_characters_are_what_they_claim_to_be():
    assert len(E_ACUTE) == 1 and len("e" + ACUTE) == 2 and E_ACUTE != "e" + ACUTE
    assert NBSP != " " and BOM.encode("utf-8") == b"\xef\xbb\xbf"


# --- document id -----------------------------------------------------------------------------------------------------------------


def test_the_document_id_is_the_sha256_of_the_normalised_text_restated_independently():
    assert document_id_of("hello\nworld") == sha("hello\nworld")
    assert document_id_of("hello\r\nworld") == sha("hello\nworld")
    assert document_id_of("caf" + E_ACUTE) == sha("caf" + E_ACUTE)


def test_the_document_id_is_lowercase_hex_of_sha256_length():
    assert re.fullmatch(r"[0-9a-f]{64}", document_id_of("anything"))


def test_one_document_has_one_id_whatever_its_line_endings_or_unicode_form():
    assert document_id_of("a\r\nb\r\n") == document_id_of("a\nb\n") == document_id_of("a\rb\r")
    assert document_id_of("cafe" + ACUTE) == document_id_of("caf" + E_ACUTE)


@pytest.mark.parametrize("a, b", [
    ("hello", "hellp"),
    ("hello", "hello "),
    ("hello", " hello"),
    ("hello\n", "hello"),
    ("a b", "a  b"),
    ("a\tb", "a b"),
    ("Hello", "hello"),
    ("", " "),
])
def test_different_text_has_a_different_document_id(a, b):
    assert document_id_of(a) != document_id_of(b)


def test_text_that_cannot_be_encoded_is_a_programming_error_not_a_silent_id():
    with pytest.raises(UnicodeEncodeError):
        document_id_of("lone surrogate " + LONE_SURROGATE)


# --- chunk id --------------------------------------------------------------------------------------------------------------------

BASE = dict(source_id="ops", document_id="d" * 64, chunking_scheme_id="paragraph-pack-v1/max_words=12", start=3, end=14, text="hello world")


def test_the_chunk_id_is_the_sha256_of_the_canonical_json_restated_independently():
    expected = sha_json({
        "version": "chunk-v1", "source_id": "ops", "document_id": "d" * 64, "chunking_scheme_id": "paragraph-pack-v1/max_words=12",
        "start": 3, "end": 14, "text_sha256": sha("hello world"),
    })
    assert chunk_id_of(**BASE) == expected


def test_the_canonical_json_escapes_non_ascii_so_that_no_encoding_can_change_an_id():
    expected = sha_json({
        "version": "chunk-v1", "source_id": E_ACUTE, "document_id": "d" * 64, "chunking_scheme_id": "paragraph-pack-v1/max_words=12",
        "start": 3, "end": 14, "text_sha256": sha("hello world"),
    })
    assert chunk_id_of(**{**BASE, "source_id": E_ACUTE}) == expected
    assert json.dumps({"k": E_ACUTE}, ensure_ascii=True) == '{"k": "' + chr(92) + 'u00e9"}'


def test_the_chunk_id_is_lowercase_hex_of_sha256_length_and_repeatable():
    assert re.fullmatch(r"[0-9a-f]{64}", chunk_id_of(**BASE))
    assert chunk_id_of(**BASE) == chunk_id_of(**BASE)


@pytest.mark.parametrize("field, value", [
    ("source_id", "mirror"),
    ("document_id", "e" * 64),
    ("chunking_scheme_id", "paragraph-pack-v1/max_words=13"),
    ("start", 4),
    ("end", 15),
    ("text", "hello worle"),
])
def test_every_input_changes_the_chunk_id(field, value):
    assert chunk_id_of(**{**BASE, field: value}) != chunk_id_of(**BASE)


def test_the_same_content_under_two_sources_has_two_chunk_ids():
    assert chunk_id_of(**{**BASE, "source_id": "original"}) != chunk_id_of(**{**BASE, "source_id": "mirror"})


def test_fields_cannot_be_shifted_into_each_other_to_forge_a_collision():
    a = chunk_id_of(**{**BASE, "source_id": "ab", "document_id": "c" * 64})
    b = chunk_id_of(**{**BASE, "source_id": "a", "document_id": "bc" + "c" * 62})
    assert a != b


# --- evidence reference ----------------------------------------------------------------------------------------------------------


def test_the_evidence_reference_is_derived_from_the_chunk_id_alone():
    chunk_id = "0123456789abcdef" + "f" * 48
    assert evidence_ref_of(chunk_id) == "evidence:0123456789abcdef"


def test_the_evidence_reference_is_citable_and_repeatable():
    ref = evidence_ref_of(chunk_id_of(**BASE))
    assert re.fullmatch(r"evidence:[0-9a-f]{16}", ref)
    assert "[" not in ref and "]" not in ref and "\n" not in ref
    assert ref == evidence_ref_of(chunk_id_of(**BASE))


def test_different_chunk_ids_give_different_references_for_these_inputs():
    refs = {evidence_ref_of(chunk_id_of(**{**BASE, "start": n, "end": n + 11})) for n in range(200)}
    assert len(refs) == 200


# --- source id -------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["ops", "A1", "a.b-c_d", "0start", "x" * 64, "a"])
def test_a_plain_declared_identifier_is_a_source_id(value):
    assert is_source_id(value)


@pytest.mark.parametrize("value", ["", " ", "a b", "a\n", "\na", "-a", ".a", "_a", "x" * 65, E_ACUTE, "a/b", "a:b", "a,b", None, 3, b"ops"])
def test_anything_else_is_not_a_source_id(value):
    assert not is_source_id(value)


# --- snapshot id -----------------------------------------------------------------------------------------------------------------

DOCS = [("ops", "a" * 64), ("audit", "b" * 64)]
EDGES = [("ops", "a" * 64, "audit", "b" * 64)]
SCHEME = "paragraph-pack-v1/max_words=12"


def test_the_snapshot_id_is_the_sha256_of_the_canonical_json_restated_independently():
    expected = sha_json({
        "version": "snapshot-v1", "normalisation": "nfc-lf-v1", "chunking_scheme_id": SCHEME,
        "documents": [["audit", "b" * 64], ["ops", "a" * 64]], "derivations": [["ops", "a" * 64, "audit", "b" * 64]],
    })
    assert snapshot_id_of(chunking_scheme_id=SCHEME, documents=DOCS, derivations=EDGES) == expected


def test_the_snapshot_id_does_not_depend_on_the_order_or_repetition_of_what_it_is_given():
    base = snapshot_id_of(chunking_scheme_id=SCHEME, documents=DOCS, derivations=EDGES)
    assert snapshot_id_of(chunking_scheme_id=SCHEME, documents=list(reversed(DOCS)), derivations=EDGES) == base
    assert snapshot_id_of(chunking_scheme_id=SCHEME, documents=DOCS + DOCS, derivations=EDGES + EDGES) == base


@pytest.mark.parametrize("change", ["scheme", "document added", "document changed", "source changed", "derivation added", "derivation removed"])
def test_every_part_of_the_corpus_changes_the_snapshot_id(change):
    scheme, docs, edges = SCHEME, list(DOCS), list(EDGES)
    if change == "scheme":
        scheme = "paragraph-pack-v1/max_words=13"
    elif change == "document added":
        docs.append(("grid", "c" * 64))
    elif change == "document changed":
        docs[0] = ("ops", "f" * 64)
    elif change == "source changed":
        docs[0] = ("other", "a" * 64)
    elif change == "derivation added":
        edges.append(("audit", "b" * 64, "ops", "a" * 64))
    else:
        edges = []
    assert snapshot_id_of(chunking_scheme_id=scheme, documents=docs, derivations=edges) != snapshot_id_of(
        chunking_scheme_id=SCHEME, documents=DOCS, derivations=EDGES
    )


def test_no_id_is_derived_from_a_clock_a_random_value_or_the_execution():
    for function in (document_id_of, chunk_id_of, evidence_ref_of, snapshot_id_of, normalise_text):
        parameters = set(inspect.signature(function).parameters)
        assert parameters.isdisjoint({"query", "plan_id", "execution_id", "mission_id", "clock", "now", "uuid", "seed", "query_id"}), function.__name__
