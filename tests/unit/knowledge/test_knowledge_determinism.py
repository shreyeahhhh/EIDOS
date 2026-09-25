"""The knowledge layer under different ``PYTHONHASHSEED`` values (decisions.md D-212, CLAUDE.md section 8; V1.3 Step 2).

A snapshot, its ids and the independence count are pure functions of what is declared. A subprocess per seed builds the same corpus and prints one digest of the
result; the digests must agree with each other and with an in-process run. The same technique as ``tests/unit/policy/test_policy_digest_and_determinism.py``.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eidos.knowledge import build_snapshot, independent_sources
from eidos_knowledge_factories import SCHEME, small_corpus

ROOT = Path(__file__).resolve().parents[3]

STORY = """
import hashlib, sys
sys.path[:0] = ['src', 'tests/support']
from eidos.knowledge import KnowledgeDocument, build_snapshot, independent_sources
from eidos_knowledge_factories import SCHEME, small_corpus

variant = sys.argv[1]
documents = small_corpus()
if variant == "crlf":
    documents = tuple(KnowledgeDocument(source_id=d.source_id, text=d.text.replace(chr(10), chr(13) + chr(10)), derived_from=d.derived_from) for d in documents)
elif variant == "reversed":
    documents = tuple(reversed(documents))
snapshot = build_snapshot(documents, SCHEME)
cited = [chunk.document_ref for chunk in snapshot.chunks]
result = snapshot.model_dump_json() + repr(independent_sources(cited, snapshot.derivation_map))
print(hashlib.sha256(result.encode("utf-8")).hexdigest())
"""


def story(seed: str, variant: str) -> str:
    environment = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run([sys.executable, "-c", STORY, variant], capture_output=True, text=True, cwd=ROOT, env=environment)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def in_process() -> str:
    snapshot = build_snapshot(small_corpus(), SCHEME)
    cited = [chunk.document_ref for chunk in snapshot.chunks]
    return hashlib.sha256((snapshot.model_dump_json() + repr(independent_sources(cited, snapshot.derivation_map))).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("seed", ["0", "1", "42", "2718281828"])
def test_the_snapshot_and_the_count_are_identical_under_every_hash_seed(seed):
    assert story(seed, "plain") == in_process()


@pytest.mark.parametrize("variant", ["crlf", "reversed"])
def test_line_endings_and_declaration_order_change_nothing_in_a_fresh_process(variant):
    assert story("7", variant) == in_process()


def test_the_story_really_exercises_the_corpus():
    snapshot = build_snapshot(small_corpus(), SCHEME)
    assert len(snapshot.chunks) == 13 and len(snapshot.derivations) == 1
