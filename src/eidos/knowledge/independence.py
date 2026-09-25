"""Counting independent sources (decisions.md D-209, D-221): pure, deterministic, and never inferred.

Independence rests on declared source identity. Different declared sources stay distinct even for identical content. A cited document that directly declares an
origin which is also cited adds nothing on its own and is set aside. Only relationships declared directly between documents are read: nothing is followed through a
chain of declarations and nothing is inferred from similarity or matching text. The declared sources of the documents that remain are what is counted.
"""

from collections.abc import Iterable, Mapping

from .contracts import DocumentRef


def independent_sources(cited: Iterable[DocumentRef], derived_from: Mapping[DocumentRef, Iterable[DocumentRef]]) -> tuple[str, ...]:
    """The distinct declared sources, sorted, of the cited documents that do not directly derive from another cited document."""
    documents = frozenset(cited)
    return tuple(
        sorted(
            {
                document.source_id
                for document in documents
                if not any(origin in documents for origin in derived_from.get(document, ()))
            }
        )
    )


def independent_source_count(cited: Iterable[DocumentRef], derived_from: Mapping[DocumentRef, Iterable[DocumentRef]]) -> int:
    return len(independent_sources(cited, derived_from))
