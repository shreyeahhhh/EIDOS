"""The lexical retriever: exact, in process, pinned to one snapshot, standard library only (decisions.md D-208, D-216, D-219, D-220, D-225; V1.3 Step 4).

``LexicalKnowledgePort`` is a ``KnowledgePort`` over one ``KnowledgeSnapshot``. It builds an in-memory term index from the snapshot's chunks when it is made and answers a request by
scoring every chunk that shares a term with the query, so the answer is exact: there is no approximation, no model, no network, no file and nothing that persists.

The scheme is ``lexical-bm25-v1/k1=1.2/b=0.75/tokens=word-v1``. A token is a run of word characters of the NFC text, lower-cased; there is no stop list and no stemming. A chunk's score is the
sum over the distinct query terms it contains of ``idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / average_length))``, with ``idf = ln(1 + (N - df + 0.5) / (df + 0.5))`` over the snapshot's
chunks; ``k1`` and ``b`` are the customary values, fixed before any run and never tuned. The arithmetic is exact decimal arithmetic, whose logarithm is correctly rounded, so a score does
not depend on the platform's math library, and each score is rounded to a fixed quantum, so a tie is a real tie. Hits are ordered by score descending and then ``chunk_id`` ascending, and
ranked from 1. A chunk that shares no term with the query is not a hit, so an empty result is possible and is a real result.

The port is built once and never changed, so it is safe to call from any number of threads.
"""

import re
from collections import Counter
from decimal import ROUND_HALF_EVEN, Context, Decimal

from .contracts import KnowledgeChunk, KnowledgeSnapshot
from .identity import normalise_text
from .retrieval import KB_ID_PATTERN, RetrievalFailure, RetrievalFailureKind, RetrievalRequest, RetrievalResult, RetrievedChunk

TOKENIZER_ID = "word-v1"
LEXICAL_SCORE_KIND = "lexical-bm25-v1"
K1 = Decimal("1.2")
B = Decimal("0.75")
LEXICAL_SCHEME_ID = f"{LEXICAL_SCORE_KIND}/k1={K1}/b={B}/tokens={TOKENIZER_ID}"
SCORE_QUANTUM = Decimal("1e-9")
DECIMAL_PRECISION = 40

_WORD = re.compile(r"\w+")
_KB_ID = re.compile(KB_ID_PATTERN)


def tokenise(text: str) -> tuple[str, ...]:
    """The tokens of ``text`` under ``word-v1``, in order and with repeats."""
    return tuple(_WORD.findall(normalise_text(text).lower()))


class LexicalKnowledgePort:
    def __init__(self, snapshot: KnowledgeSnapshot, *, kb_id: str):
        if _KB_ID.fullmatch(kb_id) is None:
            raise ValueError("a knowledge base id has the shape of a source id")
        self._kb_id = kb_id
        self._snapshot_id = snapshot.snapshot_id
        self._chunks: tuple[KnowledgeChunk, ...] = snapshot.chunks
        self._frequencies: tuple[Counter[str], ...] = tuple(Counter(tokenise(chunk.text)) for chunk in self._chunks)
        self._lengths: tuple[int, ...] = tuple(sum(counts.values()) for counts in self._frequencies)
        document_frequency: Counter[str] = Counter()
        for counts in self._frequencies:
            document_frequency.update(counts.keys())
        self._document_frequency = document_frequency

    @property
    def kb_id(self) -> str:
        return self._kb_id

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_id

    @property
    def scheme_id(self) -> str:
        return LEXICAL_SCHEME_ID

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult | RetrievalFailure:
        for name, served in (("kb_id", self._kb_id), ("snapshot_id", self._snapshot_id), ("scheme_id", LEXICAL_SCHEME_ID)):
            asked = getattr(request, name)
            if asked != served:
                return RetrievalFailure(kind=RetrievalFailureKind.REQUEST_MISMATCH, message=f"this port serves {name} {served!r}, and the request names {asked!r}")
        chosen = self._ranked(request.text)[: request.top_k]
        size = sum(len(chunk.text.encode("utf-8")) for _, chunk in chosen)
        if size > request.max_result_bytes:
            return RetrievalFailure(
                kind=RetrievalFailureKind.RESULT_TOO_LARGE, message=f"the {len(chosen)} best hits hold {size} bytes of text, over the bound of {request.max_result_bytes}"
            )
        return RetrievalResult(
            query_id=request.query_id,
            kb_id=self._kb_id,
            snapshot_id=self._snapshot_id,
            scheme_id=LEXICAL_SCHEME_ID,
            score_kind=LEXICAL_SCORE_KIND,
            hits=tuple(RetrievedChunk(rank=rank, chunk=chunk, score=float(score)) for rank, (score, chunk) in enumerate(chosen, start=1)),
        )

    def _ranked(self, text: str) -> list[tuple[Decimal, KnowledgeChunk]]:
        """Every chunk that shares a term with ``text``, best first: score descending, then ``chunk_id`` ascending."""
        terms = sorted({term for term in tokenise(text) if self._document_frequency[term]})
        if not terms:  # no term of the query is in any chunk: nothing to score (and, when a term is in a chunk, the total length below is never zero)
            return []
        context = Context(prec=DECIMAL_PRECISION, rounding=ROUND_HALF_EVEN)  # made per call, and every step below uses it: the ambient context and other threads play no part
        one, half = Decimal(1), Decimal("0.5")
        count = Decimal(len(self._chunks))
        average_length = context.divide(Decimal(sum(self._lengths)), count)
        saturation_top = context.add(K1, one)
        weight = {
            term: context.ln(
                context.add(
                    one,
                    context.divide(
                        context.add(context.subtract(count, Decimal(self._document_frequency[term])), half), context.add(Decimal(self._document_frequency[term]), half)
                    ),
                )
            )
            for term in terms
        }
        scored: list[tuple[Decimal, KnowledgeChunk]] = []
        for chunk, frequencies, length in zip(self._chunks, self._frequencies, self._lengths):
            scale = context.add(context.subtract(one, B), context.multiply(B, context.divide(Decimal(length), average_length)))
            score = Decimal(0)
            matched = False
            for term in terms:  # a fixed order, so the sum never depends on the hash seed
                tf = frequencies.get(term, 0)
                if tf == 0:
                    continue
                matched = True
                saturation = context.divide(context.multiply(Decimal(tf), saturation_top), context.add(Decimal(tf), context.multiply(K1, scale)))
                score = context.add(score, context.multiply(weight[term], saturation))
            if matched:
                scored.append((score.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_EVEN, context=context), chunk))
        scored.sort(key=lambda item: (item[0].copy_negate(), item[1].chunk_id))
        return scored
