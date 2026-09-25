"""The chunker (decisions.md D-212, D-215, D-222; V1.3 Step 2): spans worked out by hand, then properties over seeded random documents.

Every special character is built from its code point, never typed, so no tool that rewrites text can quietly change what a test does.
"""

import random

import pytest
from pydantic import ValidationError

from eidos.knowledge import ChunkingScheme, chunk_document, chunk_id_of, chunk_spans, document_id_of, normalise_text

E_ACUTE = chr(0xE9)
O_UMLAUT = chr(0xF6)
ACUTE = chr(0x301)
NBSP = chr(0xA0)
EM_SPACE = chr(0x2003)
IDEOGRAPHIC_SPACE = chr(0x3000)
LINE_SEPARATOR = chr(0x2028)
EMOJI = chr(0x1F600)

# exactly the whitespace the chunker documents: nothing more, nothing less
WHITESPACE = [0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000]
NOT_WHITESPACE = [0x1C, 0x1D, 0x1E, 0x1F, 0xAD, 0x180E, 0x200B, 0x200C, 0x200D, 0x2060, 0x3001, 0xFEFF, 0x2D, 0x5F]


def spans(text: str, max_words: int) -> list[tuple[int, int]]:
    return list(chunk_spans(text, ChunkingScheme(max_words=max_words)))


# --- the scheme ------------------------------------------------------------------------------------------------------------------


def test_the_scheme_id_names_the_algorithm_and_its_bound():
    assert ChunkingScheme(max_words=85).scheme_id == "paragraph-pack-v1/max_words=85"
    assert ChunkingScheme(max_words=1).scheme_id == "paragraph-pack-v1/max_words=1"


def test_the_bound_is_required_positive_and_an_integer():
    with pytest.raises(ValidationError):
        ChunkingScheme()  # no default: the caller states the bound
    for bad in (0, -1, 5.0, "5", None):
        with pytest.raises(ValidationError):
            ChunkingScheme(max_words=bad)


# --- spans worked out by hand ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, max_words, expected", [
    ("one two three", 2, [(0, 7), (8, 13)]),
    ("one two three", 3, [(0, 13)]),
    ("one two three", 99, [(0, 13)]),
    ("a b\n\nc d\n\ne f g", 4, [(0, 8), (10, 15)]),
    ("a b c d e", 2, [(0, 3), (4, 7), (8, 9)]),
    ("x\n\na b c d", 3, [(0, 1), (3, 8), (9, 10)]),
    ("a b\nc d", 3, [(0, 5), (6, 7)]),
    ("a b\nc d", 4, [(0, 7)]),
    ("a b\n  \nc d e", 3, [(0, 3), (7, 12)]),
    ("a b\nc d e", 3, [(0, 5), (6, 9)]),
    ("a\n\n\n\nb c", 2, [(0, 1), (5, 8)]),
    ("  hello world \n", 5, [(2, 13)]),
    ("solo", 1, [(0, 4)]),
    ("a b c", 1, [(0, 1), (2, 3), (4, 5)]),
])
def test_paragraphs_are_packed_and_an_oversize_paragraph_is_cut_into_windows(text, max_words, expected):
    assert spans(text, max_words) == expected


@pytest.mark.parametrize("text", ["", " ", "\n", "  \n\t \n ", NBSP + IDEOGRAPHIC_SPACE])
def test_text_with_no_words_has_no_chunks(text):
    assert spans(text, 3) == []


def test_a_single_line_break_is_not_a_paragraph_break_but_a_blank_line_is():
    assert spans("a b\nc d e", 3) == [(0, 5), (6, 9)]
    assert spans("a b\n\nc d e", 3) == [(0, 3), (5, 10)]
    assert spans("a b\n \t \nc d e", 3) == [(0, 3), (8, 13)]


def test_a_paragraph_that_fits_is_never_split_and_the_current_chunk_is_closed_before_one_that_does_not():
    assert spans("a b\n\nc d\n\ne f", 3) == [(0, 3), (5, 8), (10, 13)]
    assert spans("a\n\nb\n\nc\n\nd", 2) == [(0, 4), (6, 10)]


@pytest.mark.parametrize("code_point", WHITESPACE, ids=lambda c: f"U+{c:04X}")
def test_every_character_of_the_fixed_whitespace_set_separates_words(code_point):
    assert spans("a" + chr(code_point) + "b", 1) == [(0, 1), (2, 3)]


@pytest.mark.parametrize("code_point", NOT_WHITESPACE, ids=lambda c: f"U+{c:04X}")
def test_characters_outside_the_fixed_set_do_not_separate_words(code_point):
    assert spans("a" + chr(code_point) + "b", 1) == [(0, 3)]


def test_offsets_count_code_points_not_bytes_or_utf16_units():
    assert spans("h" + E_ACUTE + "llo w" + O_UMLAUT + "rld", 1) == [(0, 5), (6, 11)]
    assert spans(EMOJI + " ok", 1) == [(0, 1), (2, 4)]


def test_a_line_separator_character_is_whitespace_but_not_a_line_break():
    # five words in one paragraph (U+2028 is not a line feed), so they are cut into windows of three and two
    assert spans("a b" + LINE_SEPARATOR * 2 + "c d e", 3) == [(0, 6), (7, 10)]


# --- documents -------------------------------------------------------------------------------------------------------------------


def test_a_document_becomes_identified_chunks_of_its_normalised_text():
    scheme = ChunkingScheme(max_words=5)
    text = "Alpha beta gamma delta epsilon zeta"
    chunks = chunk_document(source_id="ops", text=text, scheme=scheme)
    assert [(c.start, c.end, c.text) for c in chunks] == [(0, 30, "Alpha beta gamma delta epsilon"), (31, 35, "zeta")]
    for chunk in chunks:
        assert chunk.source_id == "ops" and chunk.document_id == document_id_of(text)
        assert chunk.chunk_id == chunk_id_of(
            source_id="ops", document_id=document_id_of(text), chunking_scheme_id="paragraph-pack-v1/max_words=5", start=chunk.start, end=chunk.end, text=chunk.text
        )
    assert len({c.chunk_id for c in chunks}) == 2


def test_line_endings_and_unicode_form_change_nothing_about_the_chunks():
    scheme = ChunkingScheme(max_words=4)
    lf = "First line here\n\nSecond caf" + E_ACUTE + " paragraph\nwith more words in it"
    crlf = lf.replace("\n", "\r\n")
    nfd = lf.replace(E_ACUTE, "e" + ACUTE)
    assert nfd != lf and len(nfd) == len(lf) + 1
    base = chunk_document(source_id="ops", text=lf, scheme=scheme)
    assert chunk_document(source_id="ops", text=crlf, scheme=scheme) == base
    assert chunk_document(source_id="ops", text=nfd, scheme=scheme) == base
    assert chunk_document(source_id="ops", text=lf.replace("\n", "\r"), scheme=scheme) == base


def test_the_same_content_under_two_sources_has_the_same_spans_and_different_chunk_ids():
    scheme = ChunkingScheme(max_words=3)
    original = chunk_document(source_id="original", text="one two three four five", scheme=scheme)
    mirror = chunk_document(source_id="mirror", text="one two three four five", scheme=scheme)
    assert [(c.start, c.end, c.text) for c in original] == [(c.start, c.end, c.text) for c in mirror]
    assert not {c.chunk_id for c in original} & {c.chunk_id for c in mirror}
    assert {c.document_id for c in original} == {c.document_id for c in mirror}


def test_the_scheme_is_part_of_a_chunks_identity_even_when_the_spans_agree():
    text = "one two three"
    small = chunk_document(source_id="ops", text=text, scheme=ChunkingScheme(max_words=50))
    large = chunk_document(source_id="ops", text=text, scheme=ChunkingScheme(max_words=60))
    assert [(c.start, c.end) for c in small] == [(c.start, c.end) for c in large]
    assert small[0].chunk_id != large[0].chunk_id


def test_a_document_with_no_words_has_no_chunks():
    assert chunk_document(source_id="ops", text="  \r\n \t", scheme=ChunkingScheme(max_words=3)) == ()


# --- properties over seeded random documents -------------------------------------------------------------------------------------

WORDS = ["alpha", "b" + E_ACUTE + "ta", chr(0x3B3), "x", "longerword", "delta7", chr(0x4E2D) + chr(0x6587), "o'clock", "e-mail", EMOJI]
SEPARATORS = [" ", "  ", "\t", "\n", "\n\n", "\n \n", "\n\n\n", NBSP, EM_SPACE, "\n\t\n"]


def random_text(rng: random.Random) -> str:
    parts = []
    if rng.random() < 0.2:
        parts.append(rng.choice(SEPARATORS))
    for _ in range(rng.randint(0, 60)):
        parts.append(rng.choice(WORDS))
        parts.append(rng.choice(SEPARATORS))
    return "".join(parts)


@pytest.mark.parametrize("seed, max_words", [(seed, m) for seed in range(120) for m in (1, 2, 3, 7, 25)])
def test_chunks_cover_every_word_once_in_order_within_the_bound_and_without_overlap(seed, max_words):
    text = random_text(random.Random(seed))
    found = spans(text, max_words)
    assert [w for start, end in found for w in text[start:end].split()] == text.split()
    for start, end in found:
        assert len(text[start:end].split()) <= max_words
        assert not text[start].isspace() and not text[end - 1].isspace()
    for (_, previous_end), (next_start, _) in zip(found, found[1:]):
        assert previous_end <= next_start
    assert spans(text, max_words) == found
    assert spans(text + " \n\n ", max_words) == found
    assert spans("\t \n" + text, max_words) == [(s + 3, e + 3) for s, e in found]


@pytest.mark.parametrize("seed", range(60))
def test_a_bound_at_least_the_number_of_words_gives_one_chunk_over_the_whole_text(seed):
    text = random_text(random.Random(seed))
    words = text.split()
    found = spans(text, max(len(words), 1))
    if not words:
        assert found == []
    else:
        assert len(found) == 1
        assert text[found[0][0] : found[0][1]].split() == words


@pytest.mark.parametrize("seed", range(40))
def test_chunk_document_agrees_with_the_spans_of_the_normalised_text(seed):
    rng = random.Random(1000 + seed)
    text = random_text(rng).replace("\n", rng.choice(["\n", "\r\n", "\r"]))
    scheme = ChunkingScheme(max_words=rng.choice([1, 3, 9]))
    normalised = normalise_text(text)
    chunks = chunk_document(source_id="src", text=text, scheme=scheme)
    assert [(c.start, c.end) for c in chunks] == list(chunk_spans(normalised, scheme))
    for chunk in chunks:
        assert chunk.text == normalised[chunk.start : chunk.end]
