"""Characterization of LangGraph itself — the V0.3 Step 4 spike, S1 to S7 (decisions.md D-113, D-116, D-117, D-127).

These tests do not test EIDOS. They pin the behaviours of the installed LangGraph that the adapter's design
*relies on*, so that an upgrade which changes one fails here first, by name, before it can corrupt a run. They
were written after probing the real library; where the documentation and the installed version disagreed (the
default recursion limit), the tests record what the installed version does.

    S1  a list-form join fires after all predecessors, however they finished; an empty update still triggers
    S2  same-super-step nodes read a start-of-step snapshot; a disjoint-key reducer is order-independent
    S3  several entry edges and terminal nodes compile without END; an empty graph is refused; names are limited
    S4  the recursion limit is set per invocation and its accounting is depth + 1
    S5  a graph runs with no checkpointer and no thread id, and keeps nothing between runs
    S6  the dependency footprint, supported Python and the pyproject declaration
    S7  a level's nodes run concurrently on worker threads; a blocking synchronous port is fine
    S8  a raising node is not retried and its error propagates unchanged
    S9  a run makes no network call
"""

import importlib.metadata as metadata
import socket
import threading
import time
import tomllib
from pathlib import Path
from typing import Annotated, TypedDict

import pytest
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, StateGraph


def merge(current: dict, update: dict) -> dict:
    """The disjoint-key reducer the adapter uses: a key written twice is a fault."""
    clash = current.keys() & update.keys()
    if clash:
        raise ValueError(f"key collision: {sorted(clash)}")
    return {**current, **update}


class State(TypedDict):
    outcomes: Annotated[dict, merge]


def writes(name, value=None):
    return lambda state: {"outcomes": {name: name if value is None else value}}


def graph_of(nodes: dict, edges: list):
    """``nodes`` maps name -> function; ``edges`` are (source, target) pairs, a list source being a join."""
    builder = StateGraph(State)
    for name, fn in nodes.items():
        builder.add_node(name, fn)
    for source, target in edges:
        builder.add_edge(source, target)
    return builder.compile()


def chain(n: int):
    nodes = {f"n{i}": writes(f"n{i}", i) for i in range(n)}
    edges = [(START, "n0")] + [(f"n{i - 1}", f"n{i}") for i in range(1, n)]
    return graph_of(nodes, edges)


# --- S1: joins and empty updates ---------------------------------------------------------------------------


def test_s1_a_list_form_join_fires_once_after_all_predecessors_and_sees_their_outcomes():
    seen = []

    def join(state):
        seen.append(sorted(state["outcomes"]))
        return {"outcomes": {"c": "joined"}}

    graph = graph_of(
        {"a": writes("a"), "b": writes("b"), "c": join},
        [(START, "a"), (START, "b"), (["a", "b"], "c")],
    )
    result = graph.invoke({"outcomes": {}})
    assert seen == [["a", "b"]]  # exactly once, and both predecessors' outcomes were visible
    assert result["outcomes"] == {"a": "a", "b": "b", "c": "joined"}


def test_s1_a_predecessor_that_recorded_a_failure_does_not_stop_the_join():
    # In EIDOS a failed node *returns* a FAILED outcome; it does not raise into LangGraph.
    graph = graph_of(
        {"a": writes("a", "FAILED"), "b": writes("b", "ok"), "c": writes("c", "ran")},
        [(START, "a"), (START, "b"), (["a", "b"], "c")],
    )
    assert graph.invoke({"outcomes": {}})["outcomes"]["c"] == "ran"


def test_s1_a_join_across_predecessors_of_different_depth_waits_for_the_deepest():
    order = []

    def track(name):
        def fn(state):
            order.append(name)
            return {"outcomes": {name: 1}}

        return fn

    graph = graph_of(
        {n: track(n) for n in ("a1", "a2", "a3", "b", "join")},
        [(START, "a1"), ("a1", "a2"), ("a2", "a3"), (START, "b"), (["a3", "b"], "join")],
    )
    graph.invoke({"outcomes": {}})
    assert order.count("join") == 1 and order[-1] == "join"  # level 4 = 1 + max(3, 1)


@pytest.mark.parametrize("update", [None, {}], ids=["None", "empty dict"])
def test_s1_a_node_that_returns_no_update_still_triggers_its_successors(update):
    # A node carried over from prior outcomes returns no update, and must still release its successors.
    graph = graph_of(
        {"a": lambda state: update, "b": writes("b")},
        [(START, "a"), ("a", "b")],
    )
    assert graph.invoke({"outcomes": {}})["outcomes"] == {"b": "b"}


# --- S2: snapshots and the reducer ---------------------------------------------------------------------------


def test_s2_nodes_of_one_super_step_read_a_start_of_step_snapshot():
    seen = {}

    def observer(name):
        def fn(state):
            seen[name] = sorted(state["outcomes"])
            return {"outcomes": {name: 1}}

        return fn

    graph = graph_of(
        {n: observer(n) for n in "xyz"} | {"after": observer("after")},
        [(START, "x"), (START, "y"), (START, "z"), (["x", "y", "z"], "after")],
    )
    graph.invoke({"outcomes": {}})
    assert seen["x"] == seen["y"] == seen["z"] == []  # no sibling's write was visible
    assert seen["after"] == ["x", "y", "z"]  # all of them were, one step later


def test_s2_prior_outcomes_in_the_initial_state_are_visible_to_every_node():
    seen = {}

    def fn(state):
        seen["a"] = dict(state["outcomes"])
        return {"outcomes": {"a": 1}}

    graph_of({"a": fn}, [(START, "a")]).invoke({"outcomes": {"prior": "ok"}})
    assert seen["a"] == {"prior": "ok"}


@pytest.mark.parametrize("delays", [(0.06, 0.03, 0.0), (0.0, 0.03, 0.06), (0.03, 0.0, 0.06)])
def test_s2_the_merged_state_does_not_depend_on_which_parallel_node_finishes_first(delays):
    def slow(name, delay):
        def fn(state):
            time.sleep(delay)
            return {"outcomes": {name: f"value-{name}"}}

        return fn

    nodes = {n: slow(n, d) for n, d in zip("xyz", delays)}
    result = graph_of(nodes, [(START, n) for n in nodes]).invoke({"outcomes": {}})
    assert result["outcomes"] == {"x": "value-x", "y": "value-y", "z": "value-z"}


def test_s2_two_parallel_nodes_writing_the_same_key_is_a_fault_that_propagates():
    graph = graph_of(
        {"p": writes("k", 1), "q": writes("k", 2)}, [(START, "p"), (START, "q")]
    )
    with pytest.raises(ValueError, match="key collision"):
        graph.invoke({"outcomes": {}})


# --- S3: entries, terminals, the empty graph and node names ------------------------------------------------------


def test_s3_several_entry_edges_and_terminal_nodes_need_no_end_wiring():
    graph = graph_of({"x": writes("x"), "y": writes("y")}, [(START, "x"), (START, "y")])
    assert graph.invoke({"outcomes": {}})["outcomes"] == {"x": "x", "y": "y"}


def test_s3_a_graph_with_no_node_is_refused_so_the_adapter_must_short_circuit_an_empty_plan():
    with pytest.raises(ValueError, match="entrypoint"):
        StateGraph(State).compile()


@pytest.mark.parametrize("name", ["__start__", "__end__", "a:b", "a|b"])
def test_s3_some_names_are_reserved_so_step_ids_cannot_be_used_as_node_names(name):
    # LLM-authored step ids are arbitrary strings; the adapter names nodes by plan position instead.
    builder = StateGraph(State)
    with pytest.raises(ValueError, match="reserved"):
        builder.add_node(name, writes("x"))
        builder.add_edge(START, name)
        builder.compile()


@pytest.mark.parametrize("name", ["n0", "n17", "a b", "D-092"])
def test_s3_ordinary_names_and_positional_names_are_accepted(name):
    assert graph_of({name: writes("x")}, [(START, name)]).invoke({"outcomes": {}})["outcomes"] == {"x": "x"}


def test_s3_the_drawable_graph_shows_a_join_as_one_edge_per_predecessor():
    graph = graph_of(
        {n: writes(n) for n in ("n0", "n1", "n2", "n3")},
        [(START, "n0"), (START, "n1"), ("n0", "n2"), (["n1", "n2"], "n3")],
    )
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert {("n0", "n2"), ("n1", "n3"), ("n2", "n3")} <= edges


# --- S4: the recursion limit ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 2, 5, 30])
def test_s4_the_minimum_recursion_limit_for_a_chain_of_n_nodes_is_n_plus_one(n):
    graph = chain(n)
    with pytest.raises(GraphRecursionError):
        graph.invoke({"outcomes": {}}, {"recursion_limit": n})
    assert len(graph.invoke({"outcomes": {}}, {"recursion_limit": n + 1})["outcomes"]) == n


def test_s4_the_recursion_limit_can_be_set_per_invocation():
    graph = chain(40)
    with pytest.raises(GraphRecursionError):
        graph.invoke({"outcomes": {}}, {"recursion_limit": 10})
    assert len(graph.invoke({"outcomes": {}}, {"recursion_limit": 100})["outcomes"]) == 40


def test_s4_the_installed_default_limit_is_not_the_documented_one_so_the_adapter_sets_its_own():
    # The documentation says 1000; the installed version runs 1,200 steps without a limit (its default is
    # 10,007, and it is read from the LANGGRAPH_DEFAULT_RECURSION_LIMIT environment variable — ambient
    # configuration). The adapter never relies on the default: it passes depth + overhead explicitly, so a
    # plan behaves the same whatever the environment says. A 10,000-step run is quadratic and not repeated here.
    assert len(chain(1_200).invoke({"outcomes": {}})["outcomes"]) == 1_200


# --- S5: no checkpointer ---------------------------------------------------------------------------------------------


def test_s5_a_graph_compiles_without_a_checkpointer_and_runs_without_a_thread_id():
    graph = chain(3)
    assert graph.checkpointer is None
    assert len(graph.invoke({"outcomes": {}})["outcomes"]) == 3  # no configurable, no thread_id


def test_s5_nothing_persists_between_runs():
    graph = chain(2)
    first = graph.invoke({"outcomes": {"seed": 1}})
    second = graph.invoke({"outcomes": {}})
    assert "seed" in first["outcomes"] and "seed" not in second["outcomes"]


# --- S6: footprint, supported Python and the declaration ----------------------------------------------------------------


def test_s6_langgraphs_direct_requirements_are_these_six():
    requirements = {
        r.split(";")[0].strip().replace(">", " ").replace("<", " ").replace("=", " ").replace("~", " ").split()[0]
        for r in metadata.requires("langgraph")
        if "extra ==" not in r
    }
    assert requirements == {
        "langchain-core", "langgraph-checkpoint", "langgraph-prebuilt", "langgraph-sdk", "pydantic", "xxhash",
    }


def test_s6_the_installed_langgraph_supports_our_python_floor():
    requires_python = metadata.metadata("langgraph")["Requires-Python"]
    assert requires_python == ">=3.10"  # covers the project's >=3.11; only this interpreter was exercised here


def test_s6_the_installed_version_is_inside_the_range_pyproject_declares():
    installed = tuple(int(part) for part in metadata.version("langgraph").split(".")[:3])
    assert (1, 2, 11) <= installed < (2, 0, 0)


def test_s6_pyproject_declares_langgraph_as_an_optional_extra_also_in_dev_and_not_in_the_base_dependencies():
    project = tomllib.loads((Path(__file__).resolve().parents[3] / "pyproject.toml").read_text("utf-8"))["project"]
    assert project["dependencies"] == ["pydantic>=2"]  # the core install never needs LangGraph (D-116)
    assert project["optional-dependencies"]["langgraph"] == ["langgraph>=1.2.11,<2"]
    assert "eidos[langgraph]" in project["optional-dependencies"]["dev"]


# --- S7: concurrency and blocking ports -------------------------------------------------------------------------------


def test_s7_the_nodes_of_one_level_run_concurrently_on_worker_threads():
    barrier = threading.Barrier(3, timeout=10)  # a serial scheduler would never release it
    threads = {}

    def waits(name):
        def fn(state):
            threads[name] = threading.current_thread().name
            barrier.wait()
            return {"outcomes": {name: 1}}

        return fn

    graph = graph_of({n: waits(n) for n in "xyz"}, [(START, n) for n in "xyz"])
    assert len(graph.invoke({"outcomes": {}})["outcomes"]) == 3
    assert len(set(threads.values())) == 3  # three distinct threads, so ports must be thread-safe


def test_s7_nodes_of_different_levels_never_overlap():
    active, overlaps = [], []
    lock = threading.Lock()

    def fn(name):
        def run(state):
            with lock:
                active.append(name)
                if len(active) > 1:
                    overlaps.append(tuple(active))
            time.sleep(0.01)
            with lock:
                active.remove(name)
            return {"outcomes": {name: 1}}

        return run

    graph = graph_of({n: fn(n) for n in ("a", "b", "c")}, [(START, "a"), ("a", "b"), ("b", "c")])
    graph.invoke({"outcomes": {}})
    assert overlaps == []  # the level barrier: b starts only after a has finished


def test_s7_a_blocking_synchronous_port_inside_a_node_is_fine():
    def blocking(state):
        time.sleep(0.05)  # what a synchronous port does
        return {"outcomes": {"a": "done"}}

    assert graph_of({"a": blocking}, [(START, "a")]).invoke({"outcomes": {}})["outcomes"] == {"a": "done"}


# --- S8: failures ------------------------------------------------------------------------------------------------------


def test_s8_a_raising_node_is_called_once_not_retried_and_its_error_propagates_unchanged():
    calls = []

    def boom(state):
        calls.append(1)
        raise RuntimeError("boom")

    graph = graph_of({"a": boom}, [(START, "a")])
    with pytest.raises(RuntimeError) as raised:
        graph.invoke({"outcomes": {}})
    assert type(raised.value) is RuntimeError and raised.value.args == ("boom",)  # LangGraph only adds a note
    assert len(calls) == 1  # LangGraph applies no retry unless a policy is configured, and EIDOS configures none


# --- S9: no network ------------------------------------------------------------------------------------------------------


def test_s9_running_a_graph_makes_no_network_call(monkeypatch):
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append(args)
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    graph = graph_of(
        {"a": writes("a"), "b": writes("b"), "c": writes("c")},
        [(START, "a"), (START, "b"), (["a", "b"], "c")],
    )
    assert len(graph.invoke({"outcomes": {}})["outcomes"]) == 3
    assert attempts == []


# --- S10: ambient tracing would export run data; tracing_context switches it off --------------------------------------
#
# LangGraph is configured partly through the environment. With LANGSMITH_TRACING set, a bare run POSTs every
# node's inputs and outputs to api.smith.langchain.com. The variable must be set before the process starts (the
# library caches it), so these run in a subprocess with the network refused and count the attempts.

TRACING_PROBE = """
import socket, sys, time
attempts = []
def refuse(*a, **k):
    attempts.append(str(a[:1]))
    raise OSError("blocked")
socket.socket.connect = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse

import threading
from typing import Annotated, TypedDict
from langgraph.graph import START, StateGraph
from langsmith import tracing_context
from langsmith.utils import tracing_is_enabled

def merge(a, b):
    return {**a, **b}

class State(TypedDict):
    outcomes: Annotated[dict, merge]

seen = {}
def node(name):
    def fn(state):
        seen[name] = tracing_is_enabled()
        return {"outcomes": {name: 1}}
    return fn

builder = StateGraph(State)
for name in "xyz":
    builder.add_node(name, node(name))
    builder.add_edge(START, name)
graph = builder.compile()

if sys.argv[1] == "guarded":
    with tracing_context(enabled=False):
        graph.invoke({"outcomes": {}})
    time.sleep(3)
else:
    graph.invoke({"outcomes": {}})
    deadline = time.time() + 12
    while not attempts and time.time() < deadline:
        time.sleep(0.25)
print(len(attempts), sorted(set(seen.values())), "api.smith.langchain.com" in " ".join(attempts))
"""


def run_tracing_probe(mode: str) -> tuple[int, str, str]:
    import os
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-c", TRACING_PROBE, mode],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[3],
        env=dict(os.environ, LANGSMITH_TRACING="true", LANGSMITH_API_KEY="x",
                 LANGCHAIN_TRACING_V2="true", LANGCHAIN_API_KEY="x"),
    )
    assert completed.returncode == 0, completed.stderr
    attempts, seen, to_langsmith = completed.stdout.strip().splitlines()[-1].split(" ", 2)
    return int(attempts), seen, to_langsmith


def test_s10_an_ambient_tracing_setting_makes_a_bare_langgraph_run_call_out_to_langsmith():
    attempts, seen, to_langsmith = run_tracing_probe("bare")
    assert attempts > 0 and to_langsmith == "True"  # the risk the adapter must not inherit
    assert seen == "[True]"


def test_s10_tracing_context_switches_tracing_off_in_every_worker_thread_and_nothing_leaves():
    attempts, seen, _ = run_tracing_probe("guarded")
    assert attempts == 0
    assert seen == "[False]"  # x, y and z ran on three worker threads, and all of them saw tracing off
