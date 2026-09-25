"""The fixed document corpus, the keyword search over it and the declared input schema of the one approved tool (decisions.md D-203, D-207; V1.2 Step 4).

Standard library only, and no ``eidos`` import: the scripted tool port (Phase A) and the local reference server (Phase B, run as a subprocess) both read
this one module, so they answer identically and a difference between the two paths can only come from the transport. **It is keyword matching and
nothing else** (D-203 ruling 8): no ranking model, no embeddings, no index. A query is split into lower-case alphanumeric words of three or more
characters, minus a few stop words; a document scores one for each distinct query word it contains; the documents that score are ordered by score
(highest first) and then by id, so the answer never depends on iteration order, the clock or the hash seed.
"""

import re

CORPUS = (
    ("doc-events", "Events are recorded in an append-only log. Every mission event carries identity, sequence and timestamp, and duplicates are ignored."),
    ("doc-replay", "A completed mission can be replayed from its recorded events without running any agent again. Replay rebuilds the mission state deterministically."),
    ("doc-verification", "Verification is separate from completion. An agent returning output is never success; verification checks that citations resolve and sources are distinct."),
    ("doc-budgets", "Execution is bounded by explicit budgets such as agent calls and tool calls. Exhausting a budget stops the work rather than looping."),
    ("doc-policy", "Governance is deterministic. Whether an action is allowed is decided in code from an allowlist, and never by a prompt."),
    ("doc-unrelated", "The cafeteria menu changes on Tuesdays and features soup."),
)

DEFAULT_LIMIT = 3  # what the server returns when a caller gives no limit; EIDOS's allowlist entry has no default and sends none unless asked
MAX_LIMIT = 10

_STOP_WORDS = frozenset({"and", "the", "how", "for", "are", "can", "not", "was", "its", "any"})
_WORD = re.compile(r"[a-z0-9]+")

# The input schema the reference server declares for ``search_documents``. The allowlist entry pins a digest of it (see ``eidos_search_fixture``).
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 256},
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
    },
    "required": ["query"],
    "additionalProperties": False,
}
TOOL_NAME = "search_documents"
TOOL_DESCRIPTION = "Search a small fixed set of documents by keyword and return the matching documents."


def words(text: str) -> frozenset[str]:
    return frozenset(word for word in _WORD.findall(text.lower()) if len(word) >= 3 and word not in _STOP_WORDS)


def keyword_search(query: str, limit: int = DEFAULT_LIMIT) -> tuple[tuple[str, str], ...]:
    """The ``(id, text)`` of the documents that share a word with ``query``, best first, at most ``limit`` of them."""
    wanted = words(query)
    scored = []
    for document_id, text in CORPUS:
        score = len(wanted & words(text))
        if score:
            scored.append((-score, document_id, text))
    scored.sort()
    return tuple((document_id, text) for _, document_id, text in scored[:limit])
