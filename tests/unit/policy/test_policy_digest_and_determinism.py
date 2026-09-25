"""The argument digest, and tool admission's determinism under different ``PYTHONHASHSEED`` values (decisions.md D-203, CLAUDE.md §8; V1.2 Step 2).

The digest is the identity a duplicate is recognised by (D-203 ruling 5), so it must be canonical, independent of argument order, and identical
in every process. The determinism story runs a table of admissions in a subprocess per seed and compares one digest of the results — the same
technique as ``tests/unit/expansion/test_expansion_determinism.py``.
"""

import functools
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from eidos.policy import args_digest

# --- args_digest ---------------------------------------------------------------------------------------------------------------


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def test_the_digest_is_the_sha256_of_the_canonical_json_restated_independently():
    assert args_digest({"query": "evidence"}) == sha('{"query":"evidence"}')
    assert args_digest({"limit": 3, "query": "evidence"}) == sha('{"limit":3,"query":"evidence"}')
    assert args_digest({}) == sha("{}")


def test_the_digest_is_lowercase_hex_of_sha256_length():
    assert re.fullmatch(r"[0-9a-f]{64}", args_digest({"query": "x"}))


def test_the_order_arguments_are_given_in_never_changes_the_digest():
    assert args_digest({"query": "x", "limit": 2}) == args_digest({"limit": 2, "query": "x"})


def test_non_ascii_text_is_escaped_so_the_digest_never_depends_on_an_encoding_or_a_normal_form():
    assert args_digest({"query": "é"}) == sha('{"query":"\\u00e9"}')
    assert args_digest({"query": "€"}) != args_digest({"query": "e"})


def test_a_string_and_an_integer_never_collide():
    assert args_digest({"limit": "1"}) != args_digest({"limit": 1})


@pytest.mark.parametrize("a, b", [
    ({"query": "a"}, {"query": "b"}),
    ({"query": "a"}, {"query": "a "}),
    ({"query": "a"}, {"Query": "a"}),
    ({"query": "a", "limit": 1}, {"query": "a", "limit": 2}),
    ({"query": "a"}, {"query": "a", "limit": 1}),
    ({"query": '"'}, {"query": "'"}),
])
def test_different_arguments_have_different_digests(a, b):
    assert args_digest(a) != args_digest(b)


def test_the_digest_neither_reads_nor_changes_the_mapping():
    arguments = {"query": "x", "limit": 3}
    first = args_digest(arguments)
    assert arguments == {"query": "x", "limit": 3} and list(arguments) == ["query", "limit"]
    assert args_digest(arguments) == first


# --- determinism under different hash seeds ------------------------------------------------------------------------------------

STORY = r"""
import hashlib, json, sys
sys.path[:0] = ['src', 'tests/support']

from eidos.contracts import AutonomyLevel
from eidos.policy import args_digest
from eidos_tool_factories import (
    READ_ACTION, SEARCH_TOOL_ID, admit, invocation, make_attempt_plan_id, make_execution_id, make_search_descriptor, make_tool_registry,
)

cases = [
    dict(),
    dict(tool_id="nope/nope"),
    dict(registry=make_tool_registry(make_search_descriptor(read_only=False))),
    dict(allowed_actions=()),
    dict(autonomy_level=AutonomyLevel.RECOMMEND_ONLY),
    dict(arguments={"zzz": 1, "query": 5, "limit": 0, "aaa": "x"}),
    dict(arguments={"query": "é€", "limit": 10}),
    dict(max_tool_calls=0),
    dict(max_tool_calls=None),
    dict(max_tool_calls=2, prior_invocations=(invocation(plan=1, arguments={"query": "a"}), invocation(plan=1, arguments={"query": "b"}))),
    dict(plan_id=make_attempt_plan_id(2), max_tool_calls=2, prior_invocations=(invocation(plan=1, arguments={"query": "a"}), invocation(plan=1, arguments={"query": "b"}))),
    dict(prior_invocations=(invocation(),)),
    dict(prior_invocations=(invocation(stored=False),), max_tool_calls=1),
    dict(execution_id=make_execution_id(9), prior_invocations=(invocation(execution=1),)),
]
digest = hashlib.sha256()
for case in cases:
    digest.update(admit(**case).model_dump_json().encode())
digest.update(args_digest({"limit": 3, "query": "evidence"}).encode())
print(digest.hexdigest())
"""

ROOT = Path(__file__).resolve().parents[3]


@functools.cache
def story_digest(hash_seed: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", STORY], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=hash_seed),
    )
    assert completed.returncode == 0, completed.stderr
    digest = completed.stdout.strip().splitlines()[-1]
    assert len(digest) == hashlib.sha256().digest_size * 2
    return digest


@pytest.mark.parametrize("other_seed", ["1", "42", "112233", "2718281828"])
def test_admission_serializes_to_the_same_bytes_under_any_hash_seed(other_seed):
    assert story_digest(other_seed) == story_digest("0")


def test_the_story_really_exercises_every_kind_of_decision():
    # A guard on the guard: if the table stopped covering all three decisions, agreement across seeds would prove little.
    from eidos_tool_factories import admit, invocation
    from eidos.policy import ToolDecision

    kinds = {admit().decision, admit(tool_id="nope/nope").decision, admit(prior_invocations=(invocation(),)).decision}
    assert kinds == set(ToolDecision)


def story_cases() -> list[dict]:
    """The story's own table of cases, evaluated in-process so the guard below reads the table the subprocess really runs."""
    source = STORY.split("digest = hashlib")[0].replace("sys.path[:0] = ['src', 'tests/support']\n", "")
    namespace: dict = {}
    exec(compile(source, "<story>", "exec"), namespace)
    return namespace["cases"]


def test_the_story_table_reaches_every_decision_and_every_denial_code():
    from eidos_tool_factories import admit
    from eidos.policy import ToolDecision, ToolDenialCode

    admissions = [admit(**case) for case in story_cases()]
    assert {admission.decision for admission in admissions} == set(ToolDecision)
    assert {admission.denial.code for admission in admissions if admission.denial is not None} == set(ToolDenialCode)
