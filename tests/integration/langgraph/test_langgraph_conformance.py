"""Conformance: the LangGraph backend against the sequential reference executor (decisions.md D-117, D-118, D-120, D-128).

The reference executor is the semantic oracle (D-128). For every scenario below both executors receive the
same compiled plan, context, prior outcomes and deterministic ports, and the LangGraph backend must return a
``RunResult`` (or ``RunRejection``) that is *equal to the reference's and serializes to the same bytes* — same
statuses, same reasons, same dispatch order, same halt. Each scenario also states what the run should look
like, so a scenario cannot pass vacuously by both executors doing nothing.

What is compared beyond the result is compared as facts, not as an ordered log: which nodes each port was
called for, what the verifier received, and what the guard was asked. The LangGraph backend runs a level's
nodes concurrently, and the order of concurrent calls is precisely the scheduling detail D-117 says is not
part of correctness.
"""

import random
from uuid import UUID

import pytest

from eidos.contracts import ExecutionId, MissionId, PlanId, PlanStepKind, StepId, TenantId
from eidos.runtime import (
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunRejectionCode,
    RunResult,
    SequentialExecutor,
    VerificationResult,
    WorkResult,
)

from eidos_backend_factories import (
    LockedVerifier,
    LockedWork,
    conform,
    locked_admit_all,
    locked_halt_when,
)
from eidos_factories import make_task_genome
from eidos_runtime_factories import EXECUTION_ID, compiled_of, context_for, statuses, succeeded_result

R = RunOutcome
Code = RunRejectionCode


def prior_for(compiled, *steps: str, **overrides) -> PriorOutcomes:
    """Prior SUCCEEDED outcomes for ``steps``, each of the right kind for its node."""
    kinds = {node.step_id: node.kind for node in compiled.nodes}
    fields = dict(
        tenant_id=compiled.tenant_id,
        mission_id=compiled.mission_id,
        execution_id=EXECUTION_ID,
        plan_id=compiled.plan_id,
        plan_version=compiled.plan_version,
        outcomes=tuple(succeeded_result(s, verify=kinds.get(StepId(s)) is PlanStepKind.VERIFY) for s in steps),
    )
    fields.update(overrides)
    return PriorOutcomes(**fields)


FAIL_A = lambda: {"a": WorkResult.failed("boom")}  # noqa: E731
NO_RESULT_A = lambda: {"a": WorkResult.no_result("nothing")}  # noqa: E731


def case(name, spec, *, verify=(), work=None, verifier=None, guard=None, prior=None, outcome=R.FINISHED, expect=None):
    return pytest.param(
        dict(spec=spec, verify=verify, work=work, verifier=verifier, guard=guard, prior=prior, outcome=outcome, expect=expect),
        id=name,
    )


def layered(width, depth):
    """``depth`` levels of ``width`` nodes; every node depends on the whole previous level."""
    spec = {}
    for level in range(depth):
        for k in range(width):
            spec[f"l{level}_{k}"] = " ".join(f"l{level - 1}_{j}" for j in range(width)) if level else ""
    return spec


SHAPES = [
    case("one_node", {"a": ""}, expect={"a": "succeeded"}),
    case("empty_plan", {}, expect={}),
    case("chain", {"a": "", "b": "a", "c": "b"}, expect={"a": "succeeded", "b": "succeeded", "c": "succeeded"}),
    case("diamond", {"a": "", "b": "a", "c": "a", "d": "b c"}),
    case("fan_out", {"root": "", "x": "root", "y": "root", "z": "root"}),
    case("fan_in", {"x": "", "y": "", "z": "", "join": "x y z"}),
    case("disconnected_components", {"a": "", "b": "a", "x": "", "y": "x", "lone": ""}),
    case("independent_node_beside_a_chain", {"a": "", "b": "a", "c": ""}),
    case("plan_order_is_not_topological", {"c": "b", "b": "a", "a": "", "z": ""}),
    case("join_of_predecessors_at_different_levels", {"a": "", "b": "a", "c": "b", "d": "a c"}),
    case("wide_level_and_a_join", {**{f"r{i}": "" for i in range(12)}, "join": " ".join(f"r{i}" for i in range(12))}),
    case("layered_5_by_4", layered(5, 4)),
    case("verify_at_the_end", {"a": "", "b": "a", "v": "b"}, verify=("v",), expect={"v": "succeeded"}),
    case("verify_in_the_middle", {"a": "", "v": "a", "b": "v"}, verify=("v",)),
    case("two_verify_nodes_in_a_row", {"a": "", "v1": "a", "v2": "v1"}, verify=("v1", "v2")),
    case("verify_joining_two_work_nodes", {"a": "", "b": "", "v": "b a"}, verify=("v",)),
]

FAILURES = [
    case("failed_first_node", {"a": "", "b": "a", "c": "a"}, work=FAIL_A, outcome=R.FAILED,
         expect={"a": "failed", "b": "skipped", "c": "skipped"}),
    case("failed_first_node_skips_a_long_chain", {"a": "", "b": "a", "c": "b", "d": "c"}, work=FAIL_A, outcome=R.FAILED,
         expect={"a": "failed", "b": "skipped", "c": "skipped", "d": "skipped"}),
    case("no_result_predecessor", {"a": "", "b": "a"}, work=NO_RESULT_A, outcome=R.FAILED,
         expect={"a": "no_result", "b": "skipped"}),
    case("independent_branch_continues", {"a": "", "b": "a", "c": ""}, work=FAIL_A, outcome=R.FAILED,
         expect={"a": "failed", "b": "skipped", "c": "succeeded"}),
    case("independent_branches_continue_across_levels", {"a": "", "b": "a", "c": "b", "x": "", "y": "x", "z": "y"},
         work=FAIL_A, outcome=R.FAILED,
         expect={"a": "failed", "b": "skipped", "c": "skipped", "x": "succeeded", "y": "succeeded", "z": "succeeded"}),
    case("one_failing_predecessor_skips_a_join", {"x": "", "y": "", "join": "x y"},
         work=lambda: {"x": WorkResult.failed("boom")}, outcome=R.FAILED,
         expect={"x": "failed", "y": "succeeded", "join": "skipped"}),
    case("a_join_names_every_blocker", {"y": "", "x": "", "ok": "", "join": "x ok y"},
         work=lambda: {"y": WorkResult.failed("1"), "x": WorkResult.no_result("2")}, outcome=R.FAILED),
    case("executor_raises", {"a": "", "b": "a", "c": ""}, work=lambda: {"a": RuntimeError("kaboom")}, outcome=R.FAILED,
         expect={"a": "failed", "b": "skipped", "c": "succeeded"}),
    case("executor_raises_with_no_message", {"a": ""}, work=lambda: {"a": ValueError()}, outcome=R.FAILED),
    case("executor_returns_none", {"a": "", "b": "a"}, work=lambda: {"a": lambda context, node: None}, outcome=R.FAILED),
    case("executor_returns_the_wrong_type", {"a": ""}, work=lambda: {"a": lambda context, node: "artifact:a"}, outcome=R.FAILED),
    case("verification_fails", {"a": "", "v": "a", "b": "v"}, verify=("v",),
         verifier=lambda: {"v": VerificationResult.failed("contradicted")}, outcome=R.FAILED,
         expect={"a": "succeeded", "v": "verification_failed", "b": "skipped"}),
    case("verification_inconclusive", {"a": "", "v": "a", "b": "v"}, verify=("v",),
         verifier=lambda: {"v": VerificationResult.inconclusive("insufficient")}, outcome=R.FAILED,
         expect={"v": "verification_inconclusive", "b": "skipped"}),
    case("verifier_raises", {"a": "", "v": "a"}, verify=("v",),
         verifier=lambda: {"v": RuntimeError("verifier down")}, outcome=R.FAILED, expect={"v": "failed"}),
    case("verifier_returns_the_wrong_type", {"a": "", "v": "a"}, verify=("v",),
         verifier=lambda: {"v": lambda context, node, predecessors: True}, outcome=R.FAILED, expect={"v": "failed"}),
    case("verify_node_behind_a_failure_is_skipped", {"a": "", "v": "a"}, verify=("v",), work=FAIL_A, outcome=R.FAILED,
         expect={"a": "failed", "v": "skipped"}),
]

HALTS = [
    case("halt_at_level_two", {"a": "", "b": "a", "c": "b"}, guard=lambda: locked_halt_when(lambda r: r.level == 2),
         outcome=R.HALTED, expect={"a": "succeeded", "b": "not_reached", "c": "not_reached"}),
    case("halt_denies_one_node_and_the_rest_of_the_level_still_runs", {"a": "", "b": "a", "c": "a", "d": "a", "e": "c"},
         guard=lambda: locked_halt_when(lambda r: r.step_id == "b"), outcome=R.HALTED,
         expect={"b": "not_reached", "c": "succeeded", "d": "succeeded", "e": "not_reached"}),
    case("halt_in_the_first_level", {"a": "", "b": "a", "c": ""}, guard=lambda: locked_halt_when(lambda r: True, "no budget"),
         outcome=R.HALTED, expect={"a": "not_reached", "b": "not_reached", "c": "not_reached"}),
    case("halt_in_the_last_level", {"a": "", "b": "a", "c": "b"}, guard=lambda: locked_halt_when(lambda r: r.step_id == "c"),
         outcome=R.HALTED, expect={"c": "not_reached", "b": "succeeded"}),
    case("halt_takes_precedence_over_an_earlier_failure", {"a": "", "b": "a", "x": "", "y": "x"}, work=FAIL_A,
         guard=lambda: locked_halt_when(lambda r: r.level == 2), outcome=R.HALTED,
         expect={"a": "failed", "b": "skipped", "x": "succeeded", "y": "not_reached"}),
    case("rank_based_budget_admits_a_prefix_of_each_level", {"root": "", "a": "root", "b": "root", "c": "root", "d": "root"},
         guard=lambda: locked_halt_when(lambda r: r.dispatched_before_level + r.rank_in_level >= 3), outcome=R.HALTED,
         expect={"a": "succeeded", "b": "succeeded", "c": "not_reached", "d": "not_reached"}),
    case("skipped_nodes_of_the_halting_level_still_resolve", {"a": "", "x": "", "b": "a", "c": "x", "d": "c"},
         work=FAIL_A, guard=lambda: locked_halt_when(lambda r: r.step_id == "c"), outcome=R.HALTED,
         expect={"b": "skipped", "c": "not_reached", "d": "not_reached"}),
    case("first_denied_node_is_the_recorded_halt", {"a": "", "b": "a", "c": "a", "d": "a"},
         guard=lambda: locked_halt_when(lambda r: r.step_id in ("c", "d"), "stop"), outcome=R.HALTED),
    case("halt_after_a_verify_node_passed", {"a": "", "v": "a", "z": "v"}, verify=("v",),
         guard=lambda: locked_halt_when(lambda r: r.step_id == "z"), outcome=R.HALTED, expect={"v": "succeeded", "z": "not_reached"}),
    case("verify_nodes_are_put_to_the_guard", {"a": "", "v": "a"}, verify=("v",),
         guard=lambda: locked_halt_when(lambda r: r.step_id == "v"), outcome=R.HALTED, expect={"v": "not_reached"}),
    case("guard_that_raises_fails_closed", {"a": "", "b": "a"}, guard=lambda: _raising_guard(), outcome=R.HALTED,
         expect={"a": "not_reached", "b": "not_reached"}),
    case("guard_that_answers_none_fails_closed", {"a": ""}, guard=lambda: _junk_guard(None), outcome=R.HALTED),
    case("guard_that_answers_a_string_fails_closed", {"a": ""}, guard=lambda: _junk_guard("admit"), outcome=R.HALTED),
]


def _raising_guard():
    from eidos_runtime_factories import RaisingGuard

    return RaisingGuard()


def _junk_guard(value):
    from eidos_runtime_factories import JunkGuard

    return JunkGuard(value)


def _resumes(spec, *, steps, verify=(), work=None, guard=None, outcome=R.FINISHED, expect=None, name):
    return case(
        name, spec, verify=verify, work=work, guard=guard, outcome=outcome, expect=expect,
        prior=lambda compiled: prior_for(compiled, *steps),
    )


PRIORS = [
    _resumes({"a": "", "b": "a"}, steps=("a",), name="resume_after_the_first_node", expect={"a": "succeeded", "b": "succeeded"}),
    _resumes({"a": "", "b": "a", "c": "b", "d": "a"}, steps=("a",), name="descendants_of_a_prior_node_run"),
    _resumes({"a": "", "b": "a", "x": "", "y": "x"}, steps=("a", "b"), name="prior_in_a_deeper_level_beside_a_live_branch"),
    _resumes({"a": "", "v": "b", "b": "a"}, steps=("a",), verify=("v",), name="verifier_receives_prior_artifacts"),
    _resumes({"a": "", "v": "a", "b": "v"}, steps=("a", "v", "b"), verify=("v",), name="every_node_prior_succeeded"),
    _resumes({"a": "", "v": "a"}, steps=("a",), verify=("v",), name="prior_verify_predecessor_reaches_the_verifier"),
    _resumes({"a": "", "b": "a"}, steps=("a",), guard=lambda: locked_halt_when(lambda r: True, "no budget"),
             outcome=R.HALTED, name="prior_does_not_bypass_admission", expect={"a": "succeeded", "b": "not_reached"}),
    _resumes({"a": "", "b": "", "c": "", "d": "a b c"}, steps=("a",), name="rank_ignores_prior_nodes"),
    _resumes({"x": "", "p": "", "q": "p", "r": "q"}, steps=("p", "q"),
             guard=lambda: locked_halt_when(lambda r: r.step_id == "x"), outcome=R.HALTED,
             name="halt_beside_prior_nodes_that_reach_a_later_level", expect={"x": "not_reached", "r": "not_reached", "q": "succeeded"}),
]


def _rejected(spec, *, name, prior=None, ctx=None, verify=(), expect_code):
    return pytest.param(
        dict(spec=spec, verify=verify, prior=prior, ctx=ctx, expect_code=expect_code), id=name
    )


REJECTIONS = [
    _rejected({"a": ""}, name="wrong_tenant", expect_code=Code.WRONG_TENANT,
              ctx=lambda c: context_for(c, tenant_id=TenantId(UUID(int=801)),
                                        task_genome=make_task_genome(tenant_id=TenantId(UUID(int=801))))),
    _rejected({"a": ""}, name="wrong_mission", expect_code=Code.WRONG_MISSION,
              ctx=lambda c: context_for(c, mission_id=MissionId(UUID(int=802)))),
    _rejected({"a": ""}, name="wrong_plan", expect_code=Code.WRONG_PLAN,
              ctx=lambda c: context_for(c, plan_id=PlanId(UUID(int=803)))),
    _rejected({"a": ""}, name="wrong_plan_version", expect_code=Code.WRONG_PLAN_VERSION,
              ctx=lambda c: context_for(c, plan_version=9)),
    _rejected({"a": "", "b": "a"}, name="prior_names_an_unknown_step", expect_code=Code.INVALID_PRIOR_STATE,
              prior=lambda c: prior_for(c, "ghost")),
    _rejected({"a": "", "b": "a"}, name="prior_contradicts_the_edges", expect_code=Code.INVALID_PRIOR_STATE,
              prior=lambda c: prior_for(c, "b")),
    _rejected({"a": "", "b": "a"}, name="prior_of_another_execution", expect_code=Code.INVALID_PRIOR_STATE,
              prior=lambda c: prior_for(c, "a", execution_id=ExecutionId(UUID(int=903)))),
    _rejected({"a": "", "b": "a"}, name="prior_of_another_plan_version", expect_code=Code.INVALID_PRIOR_STATE,
              prior=lambda c: prior_for(c, "a", plan_version=42)),
    _rejected({"a": "", "v": "a"}, name="prior_outcome_of_the_wrong_kind", expect_code=Code.INVALID_PRIOR_STATE, verify=("v",),
              prior=lambda c: PriorOutcomes(
                  tenant_id=c.tenant_id, mission_id=c.mission_id, execution_id=EXECUTION_ID, plan_id=c.plan_id,
                  plan_version=c.plan_version, outcomes=(succeeded_result("a", verify=True),))),
]


def run_case(params):
    compiled = compiled_of(params["spec"], verify=params["verify"])
    prior = params["prior"](compiled) if params["prior"] else None
    reference, backend, runs = conform(
        compiled, work_script=params["work"], verifier_script=params["verifier"], guard=params["guard"], prior=prior
    )
    return compiled, reference, backend, runs


@pytest.mark.parametrize("params", SHAPES + FAILURES + HALTS + PRIORS)
def test_the_langgraph_backend_returns_exactly_what_the_reference_executor_returns(params):
    _, reference, backend, _ = run_case(params)
    assert isinstance(reference, RunResult) and isinstance(backend, RunResult)
    assert backend.outcome is params["outcome"]  # the scenario really exercised what it claims
    if params["expect"] is not None:
        expected = params["expect"]
        assert {k: v for k, v in statuses(backend).items() if k in expected} == expected


@pytest.mark.parametrize("params", REJECTIONS)
def test_context_and_prior_rejections_are_identical_and_nothing_runs(params):
    compiled = compiled_of(params["spec"], verify=params["verify"])
    prior = params["prior"](compiled) if params["prior"] else None
    context = params["ctx"](compiled) if params["ctx"] else None
    reference, backend, runs = conform(compiled, prior=prior, context=context)
    assert isinstance(reference, RunRejection) and isinstance(backend, RunRejection)
    assert backend.code is params["expect_code"]
    for _, work, verifier, guard in runs:
        assert work.calls == [] and verifier.calls == [] and guard.requests == []


def test_a_resume_chain_agrees_at_every_link():
    compiled = compiled_of({"a": "", "b": "a", "c": "b", "d": "c"})
    _, first, _ = conform(compiled, guard=lambda: locked_halt_when(lambda r: r.level == 2))[:3]
    assert first.outcome is R.HALTED
    prior = PriorOutcomes.succeeded_from(first)
    _, second, _ = conform(compiled, prior=prior, guard=lambda: locked_halt_when(lambda r: r.level == 4))[:3]
    assert second.outcome is R.HALTED
    _, third, _ = conform(compiled, prior=PriorOutcomes.succeeded_from(second))[:3]
    assert third.outcome is R.FINISHED and third.dispatched == ("d",)


def test_a_resume_after_a_failure_reruns_only_what_did_not_succeed_under_both_executors():
    compiled = compiled_of({"a": "", "b": "a", "c": "b"})
    _, failed, _ = conform(compiled, work_script=lambda: {"b": WorkResult.failed("transient")})[:3]
    _, resumed, runs = conform(compiled, prior=PriorOutcomes.succeeded_from(failed))[:3]
    assert resumed.outcome is R.FINISHED and resumed.dispatched == ("b", "c")
    for _, work, *_ in runs:
        assert sorted(work.calls) == ["b", "c"]  # a is never called again


# --- a large, seeded, randomized comparison -----------------------------------------------------------------------


WORK_KINDS = ["produced", "produced", "failed", "no_result", "raises", "none"]
VERIFY_KINDS = ["pass", "pass", "fail", "inconclusive", "raises", "junk"]


def _work_entry(kind: str):
    return {
        "failed": lambda: WorkResult.failed("f"),
        "no_result": lambda: WorkResult.no_result("n"),
        "raises": lambda: RuntimeError("boom"),
        "none": lambda: (lambda context, node: None),
    }.get(kind)


def _verify_entry(kind: str):
    return {
        "fail": lambda: VerificationResult.failed("f"),
        "inconclusive": lambda: VerificationResult.inconclusive("i"),
        "raises": lambda: RuntimeError("down"),
        "junk": lambda: (lambda context, node, predecessors: 7),
    }.get(kind)


def _random_case(seed: int):
    rng = random.Random(seed)
    n = rng.randint(1, 14)
    names = [f"n{i}" for i in range(n)]
    p = rng.choice([0.1, 0.3, 0.55, 0.85])
    spec = {name: tuple(names[j] for j in range(i) if rng.random() < p) for i, name in enumerate(names)}
    order = names[:]
    rng.shuffle(order)  # plan order need not be topological
    spec = {name: " ".join(spec[name]) for name in order}
    verify = tuple(name for name in names if rng.random() < 0.3)
    work = {name: _work_entry(rng.choice(WORK_KINDS)) for name in names if name not in verify}
    verifier = {name: _verify_entry(rng.choice(VERIFY_KINDS)) for name in verify}
    guard_kind = rng.choice(["admit", "admit", "budget", "level", "raises"])
    budget = rng.randint(0, 7)
    level = rng.randint(1, 4)
    return spec, verify, work, verifier, guard_kind, budget, level, rng


def _scripts(work, verifier):
    return (
        lambda: {k: v() for k, v in work.items() if v is not None},
        lambda: {k: v() for k, v in verifier.items() if v is not None},
    )


def _guard(kind, budget, level):
    if kind == "budget":
        return lambda: locked_halt_when(lambda r: r.dispatched_before_level + r.rank_in_level >= budget, "budget")
    if kind == "level":
        return lambda: locked_halt_when(lambda r: r.level == level, "level")
    if kind == "raises":
        return _raising_guard
    return None


def _random_run(seed: int):
    spec, verify, work, verifier, guard_kind, budget, level, rng = _random_case(seed)
    compiled = compiled_of(spec, verify=verify)
    work_script, verifier_script = _scripts(work, verifier)
    prior = None
    if rng.random() < 0.5:  # resume from an earlier, unguarded run of the same plan
        first, *_ = conform(compiled, work_script=work_script, verifier_script=verifier_script)
        successes = [o for o in PriorOutcomes.succeeded_from(first).outcomes]
        if successes and rng.random() < 0.25:
            successes.pop(rng.randrange(len(successes)))  # may contradict the plan's edges: both must reject
        prior = PriorOutcomes.succeeded_from(first).model_copy(update={"outcomes": tuple(successes)})
    return conform(
        compiled, work_script=work_script, verifier_script=verifier_script,
        guard=_guard(guard_kind, budget, level), prior=prior,
    )


@pytest.mark.parametrize("seed", range(150))
def test_the_backend_matches_the_reference_on_random_plans_scripts_guards_and_priors(seed):
    reference, backend, _ = _random_run(seed)
    assert backend == reference


def test_the_random_comparison_really_covers_every_kind_of_run():
    seen = set()
    for seed in range(150):
        reference, _, _ = _random_run(seed)
        if isinstance(reference, RunRejection):
            seen.add("rejection")
            continue
        seen.add(reference.outcome.value)
        seen.update(r.status.value for r in reference.results)
        if reference.dispatched != tuple(r.step_id for r in reference.results if r.status.value not in ("skipped", "not_reached")):
            seen.add("resumed")
    assert {"finished", "failed", "halted", "rejection", "resumed"} <= seen
    assert {"succeeded", "failed", "no_result", "skipped", "not_reached",
            "verification_failed", "verification_inconclusive"} <= seen


# --- concurrency and scheduling perturbation ------------------------------------------------------------------------------


def _slow(seconds_by_step):
    import time

    def entry(step_id):
        def run(context, node):
            time.sleep(seconds_by_step[step_id])
            return WorkResult.produced(f"artifact:{step_id}")

        return run

    return lambda: {step: entry(step) for step in seconds_by_step}


@pytest.mark.parametrize("delays", [(0.06, 0.03, 0.0), (0.0, 0.03, 0.06), (0.03, 0.0, 0.06), (0.0, 0.0, 0.0)])
def test_completion_order_within_a_level_never_changes_the_result(delays):
    spec = {"root": "", "x": "root", "y": "root", "z": "root", "join": "x y z"}
    compiled = compiled_of(spec)
    seconds = {"root": 0.0, "x": delays[0], "y": delays[1], "z": delays[2], "join": 0.0}
    reference, backend, _ = conform(compiled, work_script=_slow(seconds))
    assert backend == reference and backend.dispatched == ("root", "x", "y", "z", "join")


def test_a_wide_level_with_mixed_failures_agrees_under_real_concurrency():
    spec = layered(24, 3)
    compiled = compiled_of(spec)
    failing = {f"l0_{k}": WorkResult.failed("f") for k in (3, 11, 17)}
    reference, backend, _ = conform(compiled, work_script=lambda: dict(failing))
    assert backend == reference and backend.outcome is R.FAILED
    assert all(r.status.value == "skipped" for r in backend.results[24:])  # a failed predecessor skips every join


def test_repeated_runs_of_the_backend_are_identical():
    compiled = compiled_of({"a": "", "b": "a", "c": "a", "v": "b c", "d": "v"}, verify=("v",))
    results = [
        conform(compiled, work_script=lambda: {"b": WorkResult.no_result("x")})[1] for _ in range(5)
    ]
    assert all(r == results[0] for r in results)
    assert len({r.model_dump_json() for r in results}) == 1
