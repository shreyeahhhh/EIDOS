"""Deterministic identity for the knowledge layer: text normalisation and every id derivation (decisions.md D-211, D-212).

Pure: no I/O, no clock, no randomness, and no dependence on the hash seed, the query, the plan or the execution. Text is normalised to Unicode NFC with
CRLF and CR read as LF and nothing else, so one document has one identity on every checkout. NFC follows the Unicode version of the running interpreter.
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable

NORMALISATION_VERSION = "nfc-lf-v1"
CHUNK_ID_VERSION = "chunk-v1"
SNAPSHOT_ID_VERSION = "snapshot-v1"
EVIDENCE_REF_PREFIX = "evidence:"
EVIDENCE_REF_HEX_LENGTH = 16

SHA256_HEX = r"^[0-9a-f]{64}$"
SOURCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
SCHEME_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._=/-]{0,127}$"

_SOURCE_ID = re.compile(SOURCE_ID_PATTERN)


def is_source_id(value: object) -> bool:
    return isinstance(value, str) and _SOURCE_ID.fullmatch(value) is not None


def normalise_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest_json(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def document_id_of(text: str) -> str:
    return _sha256_text(normalise_text(text))


def chunk_id_of(*, source_id: str, document_id: str, chunking_scheme_id: str, start: int, end: int, text: str) -> str:
    return _digest_json(
        {
            "version": CHUNK_ID_VERSION,
            "source_id": source_id,
            "document_id": document_id,
            "chunking_scheme_id": chunking_scheme_id,
            "start": start,
            "end": end,
            "text_sha256": _sha256_text(text),
        }
    )


def evidence_ref_of(chunk_id: str) -> str:
    return EVIDENCE_REF_PREFIX + chunk_id[:EVIDENCE_REF_HEX_LENGTH]


def snapshot_id_of(
    *,
    chunking_scheme_id: str,
    documents: Iterable[tuple[str, str]],
    derivations: Iterable[tuple[str, str, str, str]],
) -> str:
    return _digest_json(
        {
            "version": SNAPSHOT_ID_VERSION,
            "normalisation": NORMALISATION_VERSION,
            "chunking_scheme_id": chunking_scheme_id,
            "documents": sorted(set(documents)),
            "derivations": sorted(set(derivations)),
        }
    )
