"""Small corpora and helpers for the knowledge-layer tests (V1.3 Step 2). Not the benchmark fixture (D-213), which is authored at Step 5."""

from eidos.knowledge import ChunkingScheme, DocumentRef, KnowledgeDocument, document_id_of

SCHEME = ChunkingScheme(max_words=12)

OPS_MANUAL = (
    "Before the station is restarted after a storm shutdown, the duty engineer completes the written inspection checklist.\n\n"
    "The tidal barrier sensors must report normal readings, and the result is recorded in the operations log."
)
SAFETY_AUDIT = "The audit found that no turbine may be released to the network until the shift supervisor has signed off both steps."
GRID_AGREEMENT = "The grid operator must be notified thirty minutes before reconnection."
BLOG_POST = "A blog writes that engineers inspect the plant and note the sensor readings before letting turbines run again."


def ref_of(source_id: str, text: str) -> DocumentRef:
    return DocumentRef(source_id=source_id, document_id=document_id_of(text))


def doc(source_id: str, text: str, *derived_from: DocumentRef) -> KnowledgeDocument:
    return KnowledgeDocument(source_id=source_id, text=text, derived_from=tuple(derived_from))


def small_corpus() -> tuple[KnowledgeDocument, ...]:
    """Four sources, a byte-identical mirror under a fifth, and one declared derivation."""
    return (
        doc("ops", OPS_MANUAL),
        doc("audit", SAFETY_AUDIT),
        doc("grid", GRID_AGREEMENT),
        doc("blog", BLOG_POST, ref_of("audit", SAFETY_AUDIT)),
        doc("mirror", OPS_MANUAL),
    )
