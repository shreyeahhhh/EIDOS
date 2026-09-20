"""Scenario: a whole V0.4 mission is deterministic across interpreters (CLAUDE.md §8).

Real agents over a *scripted* model, run through the single-pass runner on both executors: a verified run, a run whose analysis fails
verification, an unbound capability, and a halt followed by a resume. The serialized reports and the artifacts each agent stored must be
byte-identical under different ``PYTHONHASHSEED`` values. (The scripted model is deterministic by construction; a real model is not, and no
claim is made about one here.)
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

from eidos.contracts import StepId
from eidos.runtime import PriorOutcomes
from eidos_backend_factories import locked_halt_when
from eidos_scenario_factories import make_mission, make_mission_plan
from eidos_v04_factories import answer_by_task, drive_baseline

digest = hashlib.sha256()
CAP = {"gather": "research", "analyse": "cost"}
state = make_mission(capabilities=("research", "cost", "billing"))
plan = make_mission_plan(state, {"gather": "", "analyse": "gather", "check": "analyse"}, verify=("check",), capability_of=CAP)


def record(attempt):
    digest.update(attempt.report.model_dump_json().encode())
    for step in ("gather", "analyse"):
        stored = attempt.reference.store.get_step_artifact(state.execution_id, StepId(step))
        digest.update((stored.model_dump_json() if stored else "none").encode())


record(drive_baseline(state, plan))
record(drive_baseline(state, plan, respond=answer_by_task(analysis="Cites a [[ghost]] source.")))
unbound = make_mission_plan(state, {"gather": "", "analyse": "gather"}, capability_of={"gather": "research", "analyse": "billing"})
record(drive_baseline(state, unbound))
paused = drive_baseline(state, plan, guard=lambda: locked_halt_when(lambda r: r.step_id == "analyse", "held"))
record(paused)
record(drive_baseline(state, plan, prior=PriorOutcomes.succeeded_from(paused.report.run), rigs=paused.rigs))
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


@pytest.mark.parametrize("other_seed", ["1", "2718281828"])
def test_a_whole_v04_mission_serializes_to_the_same_bytes_under_any_hash_seed(other_seed):
    assert story_digest(other_seed) == story_digest("0")
