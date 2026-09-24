"""Within-mission replanning is deterministic (CLAUDE.md §8; decisions.md D-199, D-200; V1.1 Step 4).

Same mission, same scripted model, same candidate set => the same plans, step ids, event sequence, node
outcomes, replan reasons and recorded experiences — under any ``PYTHONHASHSEED``, and across repeated runs.
Mirrors ``tests/unit/expansion/test_expansion_determinism.py`` (a subprocess per seed, one digest compared).

What is *not* in the digest, deliberately: the random UUIDs the real ``UuidStrategyIds``/``UuidPlanIds``/
``UuidEventIds`` draw (D-182: every run gets genuinely fresh identity). Parent linkage is instead digested as
"is the previous plan's id", which is the fact that matters and is itself reproducible.
"""

import functools
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

STORY = r"""
import hashlib, json, sys, tempfile
from pathlib import Path
sys.path[:0] = ['src', 'tests/support']

from eidos.memory import JsonlExperienceStore
from eidos.planning import DeterministicSelector
from eidos.state import NodeSettledPayload, ReplanTriggeredPayload

from eidos_mission_factories import make_mission
from eidos_replanning_factories import fail_first_n_calls, replan, under_cited_first_n_calls
from eidos_validation_factories import make_system_limits


def describe(result):
    plan_index = {plan.plan_id: n for n, plan in enumerate(result.plans)}
    plans = [
        {
            "version": plan.version,
            "parent_is_previous_plan": (plan.parent_plan_id == result.plans[n - 1].plan_id) if n else None,
            "reason": plan.replan_reason,
            "steps": [
                [str(s.step_id), str(getattr(s, "capability", None)), [str(d) for d in s.depends_on]] for s in plan.steps
            ],
        }
        for n, plan in enumerate(result.plans)
    ]
    events = [[r.event.sequence, r.event.type.value] for r in result.log.records]
    settled = [
        [plan_index[r.payload.plan_id], str(r.payload.result.step_id), r.payload.result.status.value,
         str(r.payload.result.artifact), r.payload.result.reason]
        for r in result.log.records if isinstance(r.payload, NodeSettledPayload)
    ]
    triggers = [
        [plan_index[r.payload.failed_plan_id], plan_index[r.payload.next_plan_id], r.payload.cause.value, r.payload.reason]
        for r in result.log.records if isinstance(r.payload, ReplanTriggeredPayload)
    ]
    experiences = [
        [e.mission_status.value, e.run_outcome.value if e.run_outcome else None, e.verified,
         e.failure_cause.value if e.failure_cause else None, e.strategy_verification.value,
         [list(map(str, stage)) for stage in e.strategy_stage_shapes]]
        for e in result.experiences
    ]
    final = result.telemetry
    return {
        "plans": plans, "events": events, "settled": settled, "triggers": triggers, "experiences": experiences,
        "replans_used": result.replans_used,
        "final": [final.mission_status.value, final.run_outcome.value if final.run_outcome else None, final.verified,
                  final.failure_cause.value if final.failure_cause else None],
    }


def run(seed, capabilities, respond, **kwargs):
    with tempfile.TemporaryDirectory() as directory:
        store = JsonlExperienceStore.open(Path(directory) / "experience.jsonl")
        state = make_mission(capabilities=capabilities, seed=seed)
        return describe(replan(state, selector=DeterministicSelector(), store=store, respond=respond, **kwargs))


scenarios = [
    run(1, ("research", "cost"), fail_first_n_calls(1)),
    run(2, ("research", "cost", "security"), under_cited_first_n_calls(6), limits=make_system_limits(max_replans=2)),
    run(3, ("research", "cost", "security"), fail_first_n_calls(99), limits=make_system_limits(max_replans=1)),
]
digest = hashlib.sha256(json.dumps(scenarios, sort_keys=True, default=str).encode())
print(digest.hexdigest())
"""

ROOT = Path(__file__).resolve().parents[3]


def run_story(hash_seed: str) -> str:
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


@functools.cache
def story_digest(hash_seed: str) -> str:
    return run_story(hash_seed)


@pytest.mark.parametrize("other_seed", ["112233", "1", "2718281828"])
def test_l_a_replanned_mission_is_identical_under_any_hash_seed(other_seed):
    assert story_digest(other_seed) == story_digest("0")


def test_l_a_replanned_mission_is_identical_across_repeated_runs_with_the_same_seed():
    assert run_story("0") == story_digest("0")
