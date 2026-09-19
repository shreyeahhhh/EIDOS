"""Graph algorithms (decisions.md D-004, D-050, D-104): cycles, order, depth, width."""

import itertools
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest

from eidos.validation.graph import (
    find_cycles,
    longest_chain_length,
    max_antichain_width,
    topological_order,
)


def g(**edges: str) -> dict:
    """Build a mapping from ``name="dep1 dep2"`` keywords, in keyword order."""
    return {name: tuple(deps.split()) for name, deps in edges.items()}


# --- find_cycles ----------------------------------------------------------


def test_empty_graph_has_no_cycles():
    assert find_cycles({}) == ()


def test_dag_has_no_cycles():
    assert find_cycles(g(a="", b="a", c="a b")) == ()


def test_self_loop_is_a_cycle():
    # The plan V0.1 accepts (test_self_dependency_is_not_rejected_in_v01).
    assert find_cycles(g(a="a")) == (("a",),)


def test_two_cycle():
    assert find_cycles(g(a="b", b="a")) == (("a", "b"),)


def test_three_cycle_members_are_in_plan_order_not_traversal_order():
    assert find_cycles(g(a="c", b="a", c="b")) == (("a", "b", "c"),)


def test_disjoint_cycles_are_all_reported_not_just_the_first():
    graph = g(a="b", b="a", ok="", c="d", d="c", s="s")
    assert find_cycles(graph) == (("a", "b"), ("c", "d"), ("s",))


def test_a_cycle_with_a_downstream_tail_reports_only_the_cycle_members():
    # t depends on the cycle and u depends on t, but neither is on it.
    graph = g(a="b", b="a", t="a", u="t")
    assert find_cycles(graph) == (("a", "b"),)


def test_a_step_feeding_a_cycle_is_not_a_member():
    graph = g(feeder="", a="feeder b", b="a")
    assert find_cycles(graph) == (("a", "b"),)


def test_two_cycles_sharing_a_step_are_one_component():
    graph = g(a="b c", b="a", c="a")
    assert find_cycles(graph) == (("a", "b", "c"),)


def test_components_are_ordered_by_earliest_plan_position():
    graph = g(x="y", p="p", y="x")
    assert find_cycles(graph) == (("x", "y"), ("p",))


def test_repeated_dependency_entries_are_one_edge():
    assert find_cycles(g(a="", b="a a a")) == ()
    assert find_cycles(g(a="b b", b="a")) == (("a", "b"),)


def test_unknown_dependency_is_a_caller_error_not_a_plan_verdict():
    with pytest.raises(ValueError, match="unknown step"):
        find_cycles(g(a="ghost"))


# --- topological_order ----------------------------------------------------


def test_topological_order_of_empty_graph_is_empty():
    assert topological_order({}) == ()


def test_topological_order_is_none_for_any_cycle():
    assert topological_order(g(a="a")) is None
    assert topological_order(g(ok="", a="b", b="a")) is None


def test_topological_order_puts_dependencies_first():
    order = topological_order(g(c="a b", b="a", a=""))
    assert order == ("a", "b", "c")


def test_topological_order_breaks_ties_by_plan_order():
    # All three are ready at once: plan order decides, deterministically.
    assert topological_order(g(z="", m="", a="")) == ("z", "m", "a")
    assert topological_order(g(a="", m="", z="")) == ("a", "m", "z")


def test_topological_order_tie_break_is_by_position_not_by_name():
    graph = g(late="", early="", join="late early")
    assert topological_order(graph) == ("late", "early", "join")


# --- longest_chain_length (nodes, D-104) ----------------------------------


def test_empty_graph_has_depth_zero():
    assert longest_chain_length({}) == 0


def test_single_node_has_depth_one():
    assert longest_chain_length(g(a="")) == 1


def test_disconnected_nodes_have_depth_one():
    assert longest_chain_length(g(a="", b="", c="")) == 1


def test_chain_depth_is_its_node_count():
    assert longest_chain_length(g(a="", b="a", c="b", d="c")) == 4


def test_depth_of_a_diamond_is_three_nodes():
    assert longest_chain_length(g(a="", b="a", c="a", d="b c")) == 3


def test_depth_takes_the_longest_of_several_disconnected_components():
    graph = g(a="", b="a", c="b", x="", y="x")
    assert longest_chain_length(graph) == 3


def test_depth_is_the_longer_branch_not_the_sum():
    assert longest_chain_length(g(a="", short="a", l1="a", l2="l1", join="short l2")) == 4


def test_depth_is_none_for_a_cyclic_graph():
    assert longest_chain_length(g(a="b", b="a")) is None
    assert longest_chain_length(g(a="a")) is None


# --- max_antichain_width --------------------------------------------------


def test_width_of_empty_graph_is_zero_and_of_single_node_one():
    assert max_antichain_width({}) == 0
    assert max_antichain_width(g(a="")) == 1


def test_width_of_a_chain_is_one():
    assert max_antichain_width(g(a="", b="a", c="b", d="c")) == 1


def test_width_of_independent_steps_is_their_count():
    assert max_antichain_width(g(a="", b="", c="", d="")) == 4


def test_width_of_a_diamond_is_two():
    assert max_antichain_width(g(a="", b="a", c="a", d="b c")) == 2


def test_width_of_a_fan_out_is_the_number_of_leaves():
    assert max_antichain_width(g(root="", l1="root", l2="root", l3="root", l4="root")) == 4


def test_width_counts_indirect_incomparability_not_only_levels():
    # decisions.md D-050: the widest *level* here is 2, but {p, q, t} is an
    # antichain of 3. A level-count shortcut would wrongly report 2.
    graph = g(s="", q="s", t="s", r="t", p="")
    levels = {"s": 0, "p": 0, "q": 1, "t": 1, "r": 2}
    widest_level = max(list(levels.values()).count(i) for i in range(3))
    assert widest_level == 2
    assert max_antichain_width(graph) == 3


def test_width_is_none_for_a_cyclic_graph():
    assert max_antichain_width(g(a="b", b="a")) is None


def test_width_ignores_repeated_dependency_entries():
    assert max_antichain_width(g(a="", b="a a", c="a a")) == 2


def test_width_of_300_nodes_completes_promptly_and_correctly():
    # 100 independent chains of 3: width 100, 300 nodes, 300 comparable pairs
    # per chain-triple plus closure work — a real matching workload.
    graph: dict = {}
    for i in range(100):
        graph[f"a{i}"] = ()
        graph[f"b{i}"] = (f"a{i}",)
        graph[f"c{i}"] = (f"b{i}",)
    started = time.perf_counter()
    assert max_antichain_width(graph) == 100
    assert time.perf_counter() - started < 10.0


def test_width_of_a_dense_300_node_dag_completes_promptly():
    # Layered: 30 layers of 10; every node depends on the full previous layer.
    graph: dict = {}
    for layer in range(30):
        for k in range(10):
            deps = tuple(f"n{layer - 1}_{j}" for j in range(10)) if layer else ()
            graph[f"n{layer}_{k}"] = deps
    started = time.perf_counter()
    assert max_antichain_width(graph) == 10
    assert time.perf_counter() - started < 10.0


# --- brute-force cross-checks on random small graphs ----------------------


def _random_dag(rng: random.Random, n: int, p: float) -> dict:
    names = [f"n{i}" for i in range(n)]
    graph = {name: tuple(names[j] for j in range(i) if rng.random() < p) for i, name in enumerate(names)}
    order = names[:]
    rng.shuffle(order)  # plan order need not be topological
    return {name: graph[name] for name in order}


def _reach(graph: dict) -> dict:
    """Transitive dependency closure by Floyd-Warshall, independent of the code under test."""
    names = list(graph)
    reach = {(a, b): b in graph[a] for a in names for b in names}
    for k in names:
        for a in names:
            for b in names:
                if reach[(a, k)] and reach[(k, b)]:
                    reach[(a, b)] = True
    return reach


def _brute_width(graph: dict) -> int:
    names = list(graph)
    reach = _reach(graph)
    best = 0
    for size in range(len(names), 0, -1):
        for subset in itertools.combinations(names, size):
            if all(
                not reach[(a, b)] and not reach[(b, a)]
                for a, b in itertools.combinations(subset, 2)
            ):
                return size
    return best


def _brute_depth(graph: dict) -> int:
    memo: dict = {}

    def depth(name):
        if name not in memo:
            memo[name] = 1 + max((depth(d) for d in graph[name]), default=0)
        return memo[name]

    return max((depth(n) for n in graph), default=0)


@pytest.mark.parametrize("seed", range(40))
def test_width_and_depth_match_brute_force_on_random_dags(seed):
    rng = random.Random(seed)
    graph = _random_dag(rng, rng.randint(1, 9), rng.choice([0.1, 0.25, 0.5, 0.8]))
    assert max_antichain_width(graph) == _brute_width(graph)
    assert longest_chain_length(graph) == _brute_depth(graph)
    assert find_cycles(graph) == ()
    order = topological_order(graph)
    position = {name: i for i, name in enumerate(order)}
    assert sorted(order) == sorted(graph)
    assert all(position[d] < position[n] for n, deps in graph.items() for d in deps)


@pytest.mark.parametrize("seed", range(40))
def test_cycle_detection_matches_reachability_on_random_cyclic_graphs(seed):
    rng = random.Random(1000 + seed)
    n = rng.randint(1, 8)
    names = [f"n{i}" for i in range(n)]
    graph = {a: tuple(b for b in names if rng.random() < 0.2) for a in names}
    reach = _reach(graph)
    expected_members = {a for a in names if reach[(a, a)]}
    found = find_cycles(graph)
    assert {m for component in found for m in component} == expected_members
    assert (topological_order(graph) is None) == bool(expected_members)
    assert (longest_chain_length(graph) is None) == bool(expected_members)
    assert (max_antichain_width(graph) is None) == bool(expected_members)
    for component in found:  # every member reaches every other member
        assert all(reach[(a, b)] for a in component for b in component)


# --- iterative, not recursive ---------------------------------------------


def _chain(n: int) -> dict:
    graph = {"s0": ()}
    for i in range(1, n):
        graph[f"s{i}"] = (f"s{i - 1}",)
    return graph


def test_a_20000_step_chain_does_not_hit_the_recursion_limit():
    assert sys.getrecursionlimit() < 20_000
    graph = _chain(20_000)
    assert find_cycles(graph) == ()
    assert topological_order(graph) == tuple(graph)
    assert longest_chain_length(graph) == 20_000


def test_a_20000_step_cycle_does_not_hit_the_recursion_limit():
    graph = _chain(20_000)
    graph["s0"] = ("s19999",)
    (component,) = find_cycles(graph)
    assert len(component) == 20_000
    assert component[0] == "s0"


# --- determinism ----------------------------------------------------------


def test_outputs_follow_mapping_order_only():
    a = g(x="", y="x", z="", w="z")
    b = g(z="", w="z", x="", y="x")
    assert topological_order(a) == ("x", "y", "z", "w")
    assert topological_order(b) == ("z", "w", "x", "y")
    assert longest_chain_length(a) == longest_chain_length(b) == 2
    assert max_antichain_width(a) == max_antichain_width(b) == 2


def test_results_are_identical_across_hash_seeds():
    # String hashing is randomized per process; nothing here may depend on it.
    script = (
        "import sys; sys.path.insert(0, 'src')\n"
        "from eidos.validation.graph import *\n"
        "g = {'k%d' % i: tuple('k%d' % j for j in range(i) if (i * 7 + j * 3) % 4 == 0) for i in range(40)}\n"
        "g['k1'] = ('k5',)\n"  # k5 -> k3 -> k1 -> k5 is a cycle
        "h = dict(g); h['k1'] = ()\n"
        "print(find_cycles(g), topological_order(h), longest_chain_length(h), max_antichain_width(h))\n"
    )
    root = Path(__file__).resolve().parents[3]
    outputs = set()
    for seed in ("0", "1", "12345", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, cwd=root, env=env
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1, outputs
