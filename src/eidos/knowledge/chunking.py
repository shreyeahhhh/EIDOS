"""The chunker: deterministic, tokenizer-free and shared by every retriever (decisions.md D-212, D-215, D-222).

Paragraphs are packed greedily into chunks of at most ``max_words`` words; a paragraph longer than that is cut into windows of ``max_words`` words. A word is a run of
characters that are not whitespace, whitespace being the fixed set below, so no result depends on the Unicode tables of the interpreter. The word-piece bound of a
particular model is checked where that model's tokenizer is, never here.
"""

import re

from pydantic import Field

from eidos.contracts import EidosModel

from .contracts import KnowledgeChunk
from .identity import chunk_id_of, document_id_of, normalise_text

SCHEME_NAME = "paragraph-pack-v1"

_WHITESPACE_CODE_POINTS = (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000)
_WORD = re.compile("[^" + "".join(re.escape(chr(code_point)) for code_point in _WHITESPACE_CODE_POINTS) + "]+")


class ChunkingScheme(EidosModel):
    """How a document is cut. ``max_words`` has no default: the caller states the bound."""

    max_words: int = Field(ge=1)

    @property
    def scheme_id(self) -> str:
        return f"{SCHEME_NAME}/max_words={self.max_words}"


def _span(words: list[tuple[int, int]]) -> tuple[int, int]:
    return words[0][0], words[-1][1]


def chunk_spans(text: str, scheme: ChunkingScheme) -> tuple[tuple[int, int], ...]:
    """The ``(start, end)`` code-point spans of the chunks of ``text``, which is taken as given (normalise it first)."""
    words = [(match.start(), match.end()) for match in _WORD.finditer(text)]
    paragraphs: list[list[tuple[int, int]]] = []
    for index, word in enumerate(words):
        if index == 0 or text.count("\n", words[index - 1][1], word[0]) >= 2:
            paragraphs.append([word])
        else:
            paragraphs[-1].append(word)
    limit = scheme.max_words
    spans: list[tuple[int, int]] = []
    current: list[tuple[int, int]] = []
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            if current:
                spans.append(_span(current))
                current = []
            for offset in range(0, len(paragraph), limit):
                spans.append(_span(paragraph[offset : offset + limit]))
        elif len(current) + len(paragraph) <= limit:
            current = current + paragraph
        else:
            spans.append(_span(current))
            current = list(paragraph)
    if current:
        spans.append(_span(current))
    return tuple(spans)


def chunk_document(*, source_id: str, text: str, scheme: ChunkingScheme) -> tuple[KnowledgeChunk, ...]:
    """The chunks of one document, identified: the text is normalised here, so a caller cannot forget to."""
    normalised = normalise_text(text)
    document_id = document_id_of(text)
    return tuple(
        KnowledgeChunk(
            chunk_id=chunk_id_of(
                source_id=source_id,
                document_id=document_id,
                chunking_scheme_id=scheme.scheme_id,
                start=start,
                end=end,
                text=normalised[start:end],
            ),
            document_id=document_id,
            source_id=source_id,
            start=start,
            end=end,
            text=normalised[start:end],
        )
        for start, end in chunk_spans(normalised, scheme)
    )
