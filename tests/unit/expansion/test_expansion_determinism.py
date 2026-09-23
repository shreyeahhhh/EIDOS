"""``expand_strategy`` serializes to identical bytes under different ``PYTHONHASHSEED``s (CLAUDE.md §8; decisions.md
D-194, D-195), mirroring ``tests/scenarios/test_v03_determinism.py``'s own established pattern, scoped to this one
pure function.
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
from uuid import UUID
sys.path[:0] = ['src', 'tests/support']

from eidos.contracts import CapabilityId, MissionId, TenantId
from eidos.expansion import expand_strategy
from eidos.planning import Strategy, StrategyStage, VerificationPosture

from eidos_expansion_factories import FixedPlanIdSource

def stage(*caps):
    return StrategyStage(capabilities=tuple(CapabilityId(c) for c in caps))

strategy = Strategy(
    tenant_id=TenantId(UUID(int=1)),
    mission_id=MissionId(UUID(int=2)),
    strategy_id=UUID(int=3),
    stages=(stage("research"), stage("cost", "security"), stage("architecture")),
    verification=VerificationPosture.FINAL,
    rationale="a representative multi-stage strategy",
)

digest = hashlib.sha256()
digest.update(expand_strategy(strategy, ids=FixedPlanIdSource()).model_dump_json().encode())
print(digest.hexdigest())
"""

ROOT = Path(__file__).resolve().parents[3]


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
def test_expansion_serializes_to_the_same_bytes_under_any_hash_seed(other_seed):
    assert story_digest(other_seed) == story_digest("0")
