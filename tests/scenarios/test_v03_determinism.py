"""Scenario: a whole mission is deterministic across interpreters (V0.3).

The validator, compiler and executors are deterministic components (CLAUDE.md §8): no hidden state, no
wall clock in logic, no dependence on set or dict iteration order. This runs a whole story — a mission that
fails verification, is replanned and finishes, and a mission that halts and resumes — in separate
interpreters with different ``PYTHONHASHSEED`` values, and requires the serialized validation reports,
compiled plans and run results to be byte-identical between them.

``drive`` also asserts, inside each interpreter, that the LangGraph backend agrees with the reference executor.
"""

import functools
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

STORY = r"""
import hashlib, sys
sys.path[:0] = ['src', 'tests/support']

from eidos.runtime import PriorOutcomes, VerificationResult
from eidos_backend_factories import locked_halt_when
from eidos_scenario_factories import drive, make_mission, make_mission_plan

digest = hashlib.sha256()


def record(attempt):
    digest.update(attempt.report.model_dump_json().encode())
    digest.update(attempt.compiled.model_dump_json().encode())
    digest.update(attempt.result.model_dump_json().encode())


caps = {"analyse": "analysis", "publish": "analysis"}
state = make_mission()

# 1. verification fails; 2. the mission is replanned and finishes
v1 = make_mission_plan(
    state, {"gather": "", "analyse": "gather", "check": "analyse", "publish": "check"}, verify=("check",), capability_of=caps
)
record(drive(state, v1, verifier=lambda: {"check": VerificationResult.failed("sources conflict")}))
v2 = make_mission_plan(
    state,
    {"gather": "", "gather_more": "", "analyse": "gather gather_more", "check": "analyse", "publish": "check"},
    verify=("check",), capability_of=caps, version=2, parent=v1, reason="verification failed at 'check'",
)
record(drive(state, v2))

# 3. a halted run, and its resumption
plan = make_mission_plan(make_mission(seed=2), {"a": "", "b": "", "c": "a b", "d": "c", "e": "d"})
other = make_mission(seed=2)
halted = drive(other, plan, guard=lambda: locked_halt_when(lambda r: r.dispatched_before_level >= 2, "two per run"))
record(halted)
record(drive(other, plan, prior=PriorOutcomes.succeeded_from(halted.result)))

print(digest.hexdigest())
"""

ROOT = Path(__file__).resolve().parents[2]


@functools.cache
def story_digest(hash_seed: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", STORY],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=dict(os.environ, PYTHONHASHSEED=hash_seed),
    )
    assert completed.returncode == 0, completed.stderr
    digest = completed.stdout.strip().splitlines()[-1]
    assert len(digest) == hashlib.sha256().digest_size * 2
    return digest


@pytest.mark.parametrize("other_seed", ["1", "42", "2718281828"])
def test_a_whole_mission_serializes_to_the_same_bytes_under_any_hash_seed(other_seed):
    assert story_digest(other_seed) == story_digest("0")
