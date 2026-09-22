"""Wire facts to EIDOS facts, and nothing else: no I/O, no clock, no correlation lookup (that is the caller's job,
using ``MissionState.agent_tasks`` — see ``webhook.py``).

``agent_task_status_of`` is total over ``TaskStateWire`` (D-166): every member converts, by name, to the matching
``AgentTaskStatus`` member — the wire's ``TaskState`` and EIDOS's ``AgentTaskStatus`` were designed to share member
names exactly (Step 2), so this is a lookup, never a hand-written table that could silently omit a case.

``text_artifact_of`` reads *only* the text a remote task reported (D-153: an ``ArtifactRef`` and never artifact
content travels in an event; the content itself is written to the same ``ArtifactStore`` a local agent writes to,
through the same ``Artifact``/``artifact_ref_for`` shapes, so Analysis and Verification — unchanged, still local,
D-175 — read a remote result exactly as they read a local one). A part this package cannot use (not text, or a
declared ``media_type`` outside ``SUPPORTED_CONTENT_TYPES``) is skipped, never guessed at; a task with nothing usable
converts to no artifact, which ``node_status_for`` already reads as ``NO_RESULT``, not a failure (D-166) — the same
degradation an empty local response already has, not a new rule.
"""

from dataclasses import dataclass

from eidos.agents import cited_refs
from eidos.agents.base import CONTENT_TYPE_MARKDOWN, SUPPORTED_CONTENT_TYPES
from eidos.contracts import AgentTaskStatus, ArtifactRef

from .wire import Artifact, Part, TaskStateWire


def agent_task_status_of(state: TaskStateWire) -> AgentTaskStatus:
    """The wire ``TaskState`` as EIDOS's own ``AgentTaskStatus`` (D-166): a name lookup, total over all nine members."""
    return AgentTaskStatus[state.name]


def _usable_text(part: Part) -> str | None:
    if part.text is None or not part.text.strip():
        return None
    if part.media_type is not None and part.media_type not in SUPPORTED_CONTENT_TYPES:
        return None
    return part.text


@dataclass(frozen=True, slots=True)
class ConvertedArtifact:
    """What a remote artifact converts to for EIDOS's own store: text, its content type, and the refs it cites."""

    content: str
    content_type: str
    source_refs: tuple[ArtifactRef, ...]


def text_artifact_of(artifacts: tuple[Artifact, ...]) -> ConvertedArtifact | None:
    """The first wire artifact with a usable text part, converted — or ``None`` if nothing here is usable.

    Citations are parsed from the text with the same ``[[ref]]`` convention every agent's output already uses
    (``eidos.agents.cited_refs``), so a remote artifact's citations are checked by the unchanged verification rules
    exactly as a local one's are.
    """
    for artifact in artifacts:
        for part in artifact.parts:
            text = _usable_text(part)
            if text is not None:
                content_type = part.media_type if part.media_type in SUPPORTED_CONTENT_TYPES else CONTENT_TYPE_MARKDOWN
                return ConvertedArtifact(content=text, content_type=content_type, source_refs=cited_refs(text))
    return None
