"""The LangGraph backend itself (decisions.md D-113, D-115, D-116, D-117, D-119, D-123, D-127).

Conformance with the reference executor is in ``test_langgraph_conformance.py``. This file tests what is
particular to running on LangGraph: what the graph is made of, what its state holds (and does not), what is
handed to and returned from LangGraph, how the recursion limit is set, how a fault in LangGraph surfaces, and
the guarantees that no persistence, retry, network or ambient configuration is involved.
"""

import dataclasses
import json
import os
import socket
import subprocess
import sys
import typing
from pathlib import Path

import pytest
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

import eidos.backends.langgraph.executor as backend_module
from eidos.backends.langgraph import BackendError, LangGraphExecutor
from eidos.backends.langgraph.executor import _RunState, _layout, _recursion_limit
from eidos.contracts import MissionState, StepId
from eidos.runtime import (
    NodeResult,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunResult,
    VerificationResult,
    WorkResult,
    context_from_state,
)

from eidos_backend_factories import conform, locked_admit_all, locked_halt_when
from eidos.compiler import compile_plan
from eidos_compiler_factories import forged_accepted_report
from eidos_factories import (
    make_agent_step,
    make_mission_state,
    make_plan,
    make_reliability_contract,
    make_task_genome,
)
from eidos_runtime_factories import (
    RaisingGuard,
    ScriptedVerifier,
    ScriptedWork,
    admit_all,
    compiled_of,
    context_for,
    statuses,
    succeeded_result,
)


def executor(work=None, verifier=None, guard=None) -> LangGraphExecutor:
    return LangGraphExecutor(
        work_executor=work or ScriptedWork(),
        verifier=verifier or ScriptedVerifier(),
        admission_guard=guard or admit_all(),
    )


DIAMOND = {"a": "", "b": "a", "c": "a", "d": "b c"}


# --- what the graph is made of ------------------------------------------------------------------------------------


def build(compiled, prior=None):
    return executor()._build_graph(compiled, context_for(compiled), _layout(compiled, prior))


def test_the_graphs_state_is_outcomes_and_nothing_else():
    # D-113: the only user state is `outcomes`; every other channel is LangGraph's own routing.
    assert list(typing.get_type_hints(_RunState, include_extras=True)) == ["outcomes"]
    graph = build(compiled_of(DIAMOND))
    user_channels = [c for c in graph.channels if not c.startswith(("__", "branch:", "join:"))]
    assert user_channels == ["outcomes"]
    assert list(graph.get_input_jsonschema()["properties"]) == ["outcomes"]


def test_the_graph_has_no_checkpointer_no_store_and_no_cache():
    graph = build(compiled_of(DIAMOND))
    assert isinstance(graph, CompiledStateGraph)
    assert graph.checkpointer is None and graph.store is None and graph.cache is None


def test_the_graph_has_one_node_per_compiled_node_named_by_plan_position():
    compiled = compiled_of({"z": "", "a": "z", "m": ""})  # names never appear in the graph
    assert sorted(build(compiled).nodes) == ["__start__", "n0", "n1", "n2"]


def test_the_graphs_edges_are_exactly_the_compiled_plans_predecessor_relation():
    compiled = compiled_of({"c": "b a", "b": "a", "a": "", "d": "c", "e": "a d"})
    names = {node.step_id: f"n{node.position}" for node in compiled.nodes}
    expected = {(names[p], names[node.step_id]) for node in compiled.nodes for p in node.predecessors}
    graph = build(compiled)
    edges = {
        (e.source, e.target)
        for e in graph.get_graph().edges
        if not e.source.startswith("__") and not e.target.startswith("__")
    }
    assert edges == expected  # nothing added, nothing dropped


def test_every_root_hangs_off_the_start_node_and_nothing_else_does():
    compiled = compiled_of({"a": "", "b": "a", "x": "", "y": "x"})
    graph = build(compiled)
    from_start = {e.target for e in graph.get_graph().edges if e.source == "__start__"}
    assert from_start == {"n0", "n2"}


@pytest.mark.parametrize("step_id", ["__start__", "__end__", "a:b", "a|b", "with space", "D-092", ""])
def test_awkward_step_ids_run_because_nodes_are_named_by_position(step_id):
    # LangGraph rejects some names; a step id is arbitrary text, so it never becomes a node name.
    plan = make_plan(steps=(
        make_agent_step(step_id=StepId(step_id)),
        make_agent_step(step_id=StepId("after"), depends_on=(StepId(step_id),)),
    ))
    report = compile_plan(plan, forged_accepted_report(plan))  # compiled_of splits on spaces, so build directly
    assert report.succeeded
    compiled = report.compiled
    result = executor().run(compiled, context_for(compiled))
    assert isinstance(result, RunResult) and result.outcome is RunOutcome.FINISHED
    assert result.dispatched == (step_id, "after")


def test_a_fresh_graph_is_built_for_every_run():
    compiled = compiled_of({"a": ""})
    built = []
    original = LangGraphExecutor._build_graph

    def spy(self, *args):
        graph = original(self, *args)
        built.append(graph)
        return graph

    LangGraphExecutor._build_graph = spy
    try:
        for _ in range(3):
            executor().run(compiled, context_for(compiled))
    finally:
        LangGraphExecutor._build_graph = original
    assert len(built) == 3 and len({id(g) for g in built}) == 3


# --- what goes into LangGraph, and what comes out ------------------------------------------------------------------------


@pytest.fixture
def captured(monkeypatch):
    """Record every ``invoke`` on a compiled graph: its input and its config."""
    calls = []
    original = CompiledStateGraph.invoke

    def spy(self, input, config=None, **kwargs):
        calls.append((input, config, kwargs))
        return original(self, input, config, **kwargs)

    monkeypatch.setattr(CompiledStateGraph, "invoke", spy)
    return calls


def test_the_input_is_outcomes_only_and_the_config_is_only_a_recursion_limit(captured):
    compiled = compiled_of(DIAMOND)
    executor().run(compiled, context_for(compiled))
    ((given, config, kwargs),) = captured
    assert set(given) == {"outcomes"} and given["outcomes"] == {}
    assert config == {"recursion_limit": 3 + 2}  # depth 3 + overhead 2, computed from the compiled levels
    assert kwargs == {}  # no thread_id, no checkpoint, no interrupt, no callbacks, no stream mode


def test_prior_outcomes_enter_only_as_outcomes(captured):
    compiled = compiled_of({"a": "", "b": "a"})
    prior = PriorOutcomes(
        tenant_id=compiled.tenant_id, mission_id=compiled.mission_id, execution_id=context_for(compiled).execution_id,
        plan_id=compiled.plan_id, plan_version=compiled.plan_version, outcomes=(succeeded_result("a"),),
    )
    executor().run(compiled, context_for(compiled), prior)
    ((given, _, _),) = captured
    assert set(given) == {"outcomes"}
    assert given["outcomes"] == {"a": succeeded_result("a")}
    assert all(isinstance(v, NodeResult) for v in given["outcomes"].values())


def test_mission_state_never_reaches_langgraph(captured):
    compiled = compiled_of({"a": "", "b": "a"})
    contract = make_reliability_contract(tenant_id=compiled.tenant_id)
    state = make_mission_state(
        tenant_id=compiled.tenant_id, mission_id=compiled.mission_id,
        reliability_contract=contract, task_genome=make_task_genome(contract=contract),
    )
    before = state.model_dump_json()
    result = executor().run(compiled, context_from_state(state, compiled))
    assert isinstance(result, RunResult) and state.model_dump_json() == before
    ((given, config, _),) = captured
    assert not any(isinstance(v, MissionState) for v in list(given.values()) + list((config or {}).values()))
    assert "mission" not in json.dumps(config or {}, default=str).lower()


def test_the_ports_receive_the_frozen_context_and_the_compiled_nodes_themselves():
    compiled = compiled_of({"a": "", "v": "a"}, verify=("v",))
    context = context_for(compiled)
    work, verifier = ScriptedWork(), ScriptedVerifier()
    executor(work, verifier).run(compiled, context)
    assert work.contexts[0] is context and verifier.contexts[0] is context  # the very object, never a copy
    assert work.nodes[0] is compiled.nodes[0]
    assert type(work.contexts[0]).__module__.startswith("eidos.")  # nothing LangGraph-shaped reaches a port


def test_no_langgraph_object_appears_in_a_result():
    compiled = compiled_of({"a": "", "b": "a", "v": "b"}, verify=("v",))
    result = executor().run(compiled, context_for(compiled))
    seen = [type(result), type(result.halt)] + [type(r) for r in result.results]
    assert all(t.__module__.startswith(("eidos.", "builtins")) for t in seen)
    assert "langgraph" not in result.model_dump_json().lower()


# --- the recursion limit --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 2, 7, 40])
def test_the_recursion_limit_is_the_plans_depth_plus_two(n):
    spec = {"s0": ""} | {f"s{i}": f"s{i - 1}" for i in range(1, n)}
    compiled = compiled_of(spec)
    assert _recursion_limit(compiled) == n + 2
    result = executor().run(compiled, context_for(compiled))
    assert result.outcome is RunOutcome.FINISHED and len(result.dispatched) == n


def test_a_deep_chain_runs_under_the_explicit_limit_whatever_the_environments_default_is(monkeypatch):
    # The library's default is read from an environment variable — ambient configuration. The backend never
    # depends on it: it always passes its own limit.
    monkeypatch.setenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "3")
    n = 400
    spec = {"s0": ""} | {f"s{i}": f"s{i - 1}" for i in range(1, n)}
    compiled = compiled_of(spec)
    result = executor().run(compiled, context_for(compiled))
    assert result.outcome is RunOutcome.FINISHED and len(result.dispatched) == n


def test_a_recursion_error_from_langgraph_is_a_backend_error_not_a_run_outcome(monkeypatch):
    monkeypatch.setattr(backend_module, "_recursion_limit", lambda compiled: 1)
    compiled = compiled_of({"a": "", "b": "a", "c": "b"})
    with pytest.raises(BackendError, match="the LangGraph backend failed: GraphRecursionError") as raised:
        executor().run(compiled, context_for(compiled))
    assert isinstance(raised.value.__cause__, GraphRecursionError)


# --- empty plans and all-prior plans ------------------------------------------------------------------------------------------


def test_an_empty_plan_finishes_without_building_a_graph(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a graph was built for an empty plan")

    monkeypatch.setattr(backend_module, "StateGraph", refuse)
    compiled = compiled_of({})
    result = executor().run(compiled, context_for(compiled))
    assert result.outcome is RunOutcome.FINISHED and result.results == () and result.dispatched == ()


def test_a_rejected_run_builds_no_graph_and_calls_no_port(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a graph was built for a rejected run")

    monkeypatch.setattr(backend_module, "StateGraph", refuse)
    compiled = compiled_of({"a": ""})
    work = ScriptedWork()
    result = executor(work).run(compiled, context_for(compiled, plan_version=9))
    assert isinstance(result, RunRejection) and work.calls == []


def test_a_plan_whose_nodes_are_all_prior_succeeded_calls_no_port():
    compiled = compiled_of({"a": "", "v": "a"}, verify=("v",))
    prior = PriorOutcomes(
        tenant_id=compiled.tenant_id, mission_id=compiled.mission_id, execution_id=context_for(compiled).execution_id,
        plan_id=compiled.plan_id, plan_version=compiled.plan_version,
        outcomes=(succeeded_result("a"), succeeded_result("v", verify=True)),
    )
    work, verifier, guard = ScriptedWork(), ScriptedVerifier(), admit_all()
    result = executor(work, verifier, guard).run(compiled, context_for(compiled), prior)
    assert (work.calls, verifier.calls, guard.requests) == ([], [], [])
    assert result.outcome is RunOutcome.FINISHED and result.dispatched == ()


# --- faults in LangGraph are BackendErrors -------------------------------------------------------------------------------------


def test_two_writes_to_one_key_are_a_backend_error(monkeypatch):
    def node_function(self, node, context, layout):
        # Every node claims the first node's key: a fault that only a reducer can catch.
        first = "a"
        return lambda state: {"outcomes": {first: succeeded_result(first)}}

    monkeypatch.setattr(LangGraphExecutor, "_node_function", node_function)
    compiled = compiled_of({"a": "", "b": "", "c": ""})
    with pytest.raises(BackendError, match="written twice"):
        executor().run(compiled, context_for(compiled))


def test_a_node_that_records_no_outcome_is_a_backend_error(monkeypatch):
    monkeypatch.setattr(LangGraphExecutor, "_node_function", lambda self, node, context, layout: (lambda state: {}))
    compiled = compiled_of({"a": "", "b": "a"})
    with pytest.raises(BackendError, match="without an outcome for step"):
        executor().run(compiled, context_for(compiled))


def test_an_unexpected_exception_inside_a_wrapper_is_a_backend_error_never_a_run_outcome(monkeypatch):
    def broken(self, node, context, layout, outcomes):
        raise RuntimeError("the adapter itself has a bug")

    monkeypatch.setattr(LangGraphExecutor, "_settle", broken)
    compiled = compiled_of({"a": ""})
    with pytest.raises(BackendError, match="RuntimeError: the adapter itself has a bug"):
        executor().run(compiled, context_for(compiled))


def test_a_halt_that_is_not_a_guard_denial_is_a_backend_error(monkeypatch):
    real = LangGraphExecutor._settle

    def forged(self, node, context, layout, outcomes):
        result = real(self, node, context, layout, outcomes)
        if node.step_id == "a" and result is not None:
            return NodeResult(step_id=node.step_id, kind=node.kind, status=NodeStatus.NOT_REACHED, reason="something else")
        return result

    monkeypatch.setattr(LangGraphExecutor, "_settle", forged)
    compiled = compiled_of({"a": ""})
    with pytest.raises(BackendError, match="was not a guard denial"):
        executor().run(compiled, context_for(compiled))


def test_port_faults_and_bad_plans_are_never_backend_errors():
    compiled = compiled_of({"a": "", "v": "a", "b": "v"}, verify=("v",))
    work = ScriptedWork({"a": RuntimeError("x")})
    result = executor(work, ScriptedVerifier({"v": RuntimeError("y")}), RaisingGuard()).run(compiled, context_for(compiled))
    assert isinstance(result, RunResult)  # a raising guard halts; nothing escapes as an exception
    rejected = executor().run(compiled, context_for(compiled, plan_version=9))
    assert isinstance(rejected, RunRejection)


# --- no retry, no persistence, no network -----------------------------------------------------------------------------------------


def test_a_failing_port_is_called_exactly_once_langgraph_never_retries_it():
    compiled = compiled_of({"a": "", "v": "a", "b": ""}, verify=("v",))
    work = ScriptedWork({"a": RuntimeError("down"), "b": RuntimeError("down")})
    verifier = ScriptedVerifier({"v": RuntimeError("down")})
    result = executor(work, verifier).run(compiled, context_for(compiled))
    assert sorted(work.calls) == ["a", "b"] and verifier.calls == []  # v is skipped behind a failed a
    assert statuses(result)["a"] == "failed" and statuses(result)["b"] == "failed"


def test_a_raising_verifier_and_guard_are_each_called_once_per_node():
    compiled = compiled_of({"a": "", "v": "a"}, verify=("v",))
    verifier = ScriptedVerifier({"v": RuntimeError("down")})
    executor(ScriptedWork(), verifier).run(compiled, context_for(compiled))
    assert verifier.calls == ["v"]
    guard = locked_halt_when(lambda r: r.step_id == "v", "stop")
    executor(guard=guard).run(compiled, context_for(compiled))
    assert sorted(r.step_id for r in guard.requests) == ["a", "v"]  # once each


def test_nothing_is_persisted_between_runs():
    compiled = compiled_of({"a": "", "b": "a"})
    ex = executor()
    first = ex.run(compiled, context_for(compiled))
    second = ex.run(compiled, context_for(compiled))
    assert first == second
    assert dataclasses.fields(ex) and [f.name for f in dataclasses.fields(ex)] == [
        "work_executor", "verifier", "admission_guard",
    ]


def test_a_run_makes_no_network_call(monkeypatch):
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append(args)
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    compiled = compiled_of({"a": "", "b": "a", "c": "a", "v": "b c"}, verify=("v",))
    result = executor(ScriptedWork({"b": WorkResult.failed("x")})).run(compiled, context_for(compiled))
    assert isinstance(result, RunResult) and attempts == []


def test_an_ambient_tracing_setting_never_sends_a_runs_data_anywhere():
    # With LANGSMITH_TRACING set in the environment, a bare LangGraph run exports every node's inputs and
    # outputs to a third party (spike S10). The backend forces tracing off, so a mission's outcomes,
    # artifacts and reasons never leave the process because of an environment variable.
    script = (
        "import socket, sys, time\n"
        "attempts = []\n"
        "def refuse(*a, **k):\n"
        "    attempts.append(str(a[:1]))\n"
        "    raise OSError('blocked')\n"
        "socket.socket.connect = refuse\n"
        "socket.create_connection = refuse\n"
        "socket.getaddrinfo = refuse\n"
        "sys.path[:0] = ['src', 'tests/support']\n"
        "from eidos.backends.langgraph import LangGraphExecutor\n"
        "from eidos_runtime_factories import *\n"
        "compiled = compiled_of({'a': '', 'b': 'a', 'c': '', 'd': 'b c'})\n"
        "result = LangGraphExecutor(work_executor=ScriptedWork(), verifier=ScriptedVerifier(), "
        "admission_guard=admit_all()).run(compiled, context_for(compiled))\n"
        "time.sleep(3)\n"
        "print(result.outcome.value, len(attempts))\n"
    )
    root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=root,
        env=dict(os.environ, LANGSMITH_TRACING="true", LANGSMITH_API_KEY="x",
                 LANGCHAIN_TRACING_V2="true", LANGCHAIN_API_KEY="x"),
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().splitlines()[-1] == "finished 0"
    assert "smith.langchain.com" not in completed.stderr  # nothing even tried


# --- the executor's shape and immutability --------------------------------------------------------------------------------------------


def test_there_is_no_default_guard_and_every_port_is_required_by_keyword():
    with pytest.raises(TypeError):
        LangGraphExecutor()
    ports = dict(work_executor=ScriptedWork(), verifier=ScriptedVerifier(), admission_guard=admit_all())
    for missing in ports:
        with pytest.raises(TypeError):
            LangGraphExecutor(**{k: v for k, v in ports.items() if k != missing})
    with pytest.raises(TypeError):
        LangGraphExecutor(*ports.values())


def test_the_executor_is_frozen():
    ex = executor()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ex.admission_guard = admit_all()


def test_the_signature_matches_the_reference_executors():
    from eidos.runtime import SequentialExecutor

    import inspect

    assert inspect.signature(LangGraphExecutor.run) == inspect.signature(SequentialExecutor.run)


def test_running_never_mutates_the_compiled_plan_the_context_or_the_prior():
    compiled = compiled_of({"a": "", "b": "a", "c": "b"})
    context = context_for(compiled)
    prior = PriorOutcomes(
        tenant_id=compiled.tenant_id, mission_id=compiled.mission_id, execution_id=context.execution_id,
        plan_id=compiled.plan_id, plan_version=compiled.plan_version, outcomes=(succeeded_result("a"),),
    )
    before = (compiled.model_dump_json(), context.model_dump_json(), prior.model_dump_json())
    executor(ScriptedWork({"b": WorkResult.failed("x")})).run(compiled, context, prior)
    assert (compiled.model_dump_json(), context.model_dump_json(), prior.model_dump_json()) == before


# --- determinism ----------------------------------------------------------------------------------------------------------------------------


def test_results_are_identical_across_hash_seeds_and_equal_to_the_reference():
    # String hashing is randomized per process; a result may not depend on it. In every process the
    # LangGraph result is also compared with the reference executor's.
    script = (
        "import sys\n"
        "sys.path[:0] = ['src', 'tests/support']\n"
        "from uuid import UUID\n"
        "from eidos.contracts import *\n"
        "from eidos.runtime import *\n"
        "from eidos_backend_factories import *\n"
        "from eidos_runtime_factories import compiled_of, context_for\n"
        "names = ['step_%d' % i for i in range(30)]\n"
        "spec = {n: ' '.join(m for m in names[:i] if (i * 5 + int(m[5:]) * 3) % 4 == 0) for i, n in enumerate(names)}\n"
        "verify = tuple(n for i, n in enumerate(names) if i % 7 == 6)\n"
        "ids = dict(tenant_id=TenantId(UUID(int=1)), mission_id=MissionId(UUID(int=2)), plan_id=PlanId(UUID(int=3)))\n"
        "compiled = compiled_of(dict(reversed(list(spec.items()))), verify=verify, **ids)\n"
        "ws = lambda: {'step_3': WorkResult.failed('x'), 'step_9': WorkResult.no_result('y')}\n"
        "vs = lambda: {'step_13': VerificationResult.inconclusive('z')}\n"
        "gd = lambda: locked_halt_when(lambda r: r.dispatched_before_level + r.rank_in_level >= 20)\n"
        "reference, backend, _ = conform(compiled, work_script=ws, verifier_script=vs, guard=gd)\n"
        "assert backend == reference\n"
        "print(backend.model_dump_json())\n"
    )
    root = Path(__file__).resolve().parents[3]
    outputs = set()
    for seed in ("0", "1", "4242", "random"):
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, cwd=root,
            env=dict(os.environ, PYTHONHASHSEED=seed),
        )
        assert completed.returncode == 0, completed.stderr
        outputs.add(completed.stdout)
    assert len(outputs) == 1
    document = json.loads(outputs.pop())
    assert {"succeeded", "failed", "skipped"} <= {r["status"] for r in document["results"]}
