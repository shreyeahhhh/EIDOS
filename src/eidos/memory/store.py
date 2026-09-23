"""``ExperienceStore`` and its JSONL adapter (decisions.md D-198; V1.0 Step 3).

**Persistence only.** This is the one module in ``eidos.memory`` ever permitted file I/O — ``experience.py`` and
``relevance.py`` stay exactly as pure as every other core layer in this project (D-198's own "pure logic free of
I/O, clock, randomness, network"). Nothing here ranks, filters, or selects: it holds and returns
``ExecutionExperience`` records, unchanged, in the order they were appended.

**JSONL, one ``ExecutionExperience`` per line — the same discipline ``eidos.state.replay``'s own ``dump_jsonl``/
``load_jsonl`` already established for the event log (D-157), applied here to a different record type.** A
line that does not parse is a typed rejection naming its line number, exactly mirroring
``ReplayRejectionCode.MALFORMED_LINE`` one layer over: the *whole* load fails, explicitly, rather than silently
dropping the one bad record and quietly continuing with an incomplete history — inspected against the
repository's own established convention before writing this, not invented.

**Load-once, cached, immutable.** ``JsonlExperienceStore.open(path)`` reads the file exactly once — a missing
file is an empty history, not an error, matching every other "nothing recorded yet" case in this project — and
caches the result as a plain Python tuple. ``all()`` returns that cached tuple directly; because a tuple is
itself immutable, a caller can never mutate the store's own state through what ``all()`` hands back, and no
defensive copy is needed. ``append()`` writes exactly the one new line to the file and extends the cached tuple
by concatenation — it never re-reads the file, matching the required semantics exactly.

**Not thread-safe**, mirroring ``eidos.state.log.EventLog``'s own identical stance: whoever calls this from
several threads serializes access themselves. Nothing here reads a clock or draws an identifier — every field on
the ``ExecutionExperience`` being appended was already decided by its own caller (``evaluate_experience``).

**Boundary**: this module may use the filesystem; it imports nothing from ``eidos.selectors``, ``eidos.agents``,
``eidos.backends``, the remote-protocol boundary package, any vendor library, any database driver, or the
benchmark harness under ``tests/``. ``ExperienceStore`` itself is a bare ``Protocol`` (``append``, ``all``) — the
same shape ``eidos.recording.ports.Clock``/``IdSource`` already use for an injected port.
"""

from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import Field, ValidationError

from eidos.contracts import EidosModel

from .experience import ExecutionExperience


class ExperienceStore(Protocol):
    """An injected port: appends one ``ExecutionExperience`` and returns every one held, in append order. Mirrors
    ``eidos.recording.ports.Clock``/``IdSource``'s own shape — a Protocol here, a real adapter (``JsonlExperienceStore``)
    below."""

    def append(self, experience: ExecutionExperience) -> None: ...

    def all(self) -> tuple[ExecutionExperience, ...]: ...


class ExperienceLoadRejectionCode(StrEnum):
    MALFORMED_LINE = "malformed_line"  # a JSONL line that is not a valid ExecutionExperience


class ExperienceLoadRejection(EidosModel):
    """Why a persisted history did not load. Mirrors ``eidos.state.replay.ReplayRejection``'s own shape, one
    layer over: a typed code, a reason, and the exact line that failed — never a partial, filtered history."""

    code: ExperienceLoadRejectionCode
    reason: str = Field(min_length=1)
    line: int = Field(ge=1)


def dump_experience_jsonl(records: Iterable[ExecutionExperience]) -> str:
    """One record per line, each newline-terminated; an empty history is the empty string. Mirrors
    ``eidos.state.replay.dump_jsonl`` exactly, for ``ExecutionExperience`` instead of ``EventRecord``."""
    return "".join(record.model_dump_json() + "\n" for record in records)


def load_experience_jsonl(text: str) -> tuple[ExecutionExperience, ...] | ExperienceLoadRejection:
    """Parse the JSONL form. A blank or malformed line is a typed rejection naming its number; nothing is
    skipped — the whole load either succeeds or names exactly where it could not. Mirrors
    ``eidos.state.replay.load_jsonl`` exactly. The empty string parses to an empty history."""
    lines = text.split("\n")  # not splitlines(): a strict JSON dump never contains a raw U+2028/U+2029 line separator, but this matches
    if lines and lines[-1] == "":  # the precedent exactly rather than assuming; splitlines() would be a silent, undocumented behavior change
        lines.pop()  # the newline that ends the last record
    records = []
    for number, line in enumerate(lines, start=1):
        try:
            records.append(ExecutionExperience.model_validate_json(line))
        except ValidationError as error:  # covers both invalid JSON syntax and a schema violation (confirmed empirically, matches load_jsonl)
            first = error.errors()[0]
            return ExperienceLoadRejection(code=ExperienceLoadRejectionCode.MALFORMED_LINE, reason=str(first["msg"]) or "invalid", line=number)
    return tuple(records)


class JsonlExperienceStore:
    """The real ``ExperienceStore``: a local, append-only JSONL file. Construct only through ``open`` — never
    directly — so a store is never held without first having actually read (or confirmed the absence of) its
    own file."""

    def __init__(self, path: Path, history: tuple[ExecutionExperience, ...]) -> None:
        self._path = path
        self._history = history

    @classmethod
    def open(cls, path: Path) -> "JsonlExperienceStore | ExperienceLoadRejection":
        """Read ``path`` exactly once. A missing file is an empty history, not an error — the ordinary
        "nothing recorded yet" case, matching every other cold-start path in this project. A malformed line is
        a typed rejection; the store is not constructed."""
        if not path.exists():
            return cls(path, ())
        loaded = load_experience_jsonl(path.read_text(encoding="utf-8"))
        if isinstance(loaded, ExperienceLoadRejection):
            return loaded
        return cls(path, loaded)

    def append(self, experience: ExecutionExperience) -> None:
        """Persist ``experience`` and extend the cached history — never a re-read of the file."""
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(experience.model_dump_json() + "\n")
        self._history = self._history + (experience,)

    def all(self) -> tuple[ExecutionExperience, ...]:
        """The cached history, in append order. A tuple is itself immutable, so this can never let a caller
        mutate the store's own state."""
        return self._history
