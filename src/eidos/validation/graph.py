"""Pure graph algorithms over an ID-addressed dependency mapping.

decisions.md: D-004 (the canonical plan is an ID-addressed DAG), D-050
(``max_depth`` = longest path, ``max_parallel_branches`` = maximum antichain
width), D-104 (path length is counted in nodes).

Input everywhere is a mapping ``step_id -> depends_on`` whose **insertion
order is the plan's step order**. Edges run from a dependency to its
dependent. Nothing here knows about ``Plan``, ``MissionState`` or limits.

Rules this module holds itself to (CLAUDE.md §8):

- Deterministic. Every returned ordering derives from the mapping's insertion
  order, never from set or hash iteration (string hashing is randomized per
  process). Ties in the topological order break toward the earlier step.
- Iterative. No recursion anywhere, so a very long chain cannot raise
  ``RecursionError``.
- No I/O, no clock, no randomness, no hidden state, no third-party graph
  library.

A dependency naming a step absent from the mapping raises ``ValueError``: the
V0.1 ``Plan`` contract rules that out, so it signals a caller bug, not an
invalid plan. Repeated entries in one ``depends_on`` are the same edge and
are collapsed.
"""

from collections import deque
from collections.abc import Mapping, Sequence
from heapq import heapify, heappop, heappush

from eidos.contracts import StepId

Dependencies = Mapping[StepId, Sequence[StepId]]


def _adjacency(deps: Dependencies) -> tuple[list[StepId], list[list[int]]]:
    """Node ids in mapping order, and each node's deduplicated dependency indices."""
    ids = list(deps)
    index = {step_id: i for i, step_id in enumerate(ids)}
    adjacency: list[list[int]] = []
    for step_id in ids:
        indices: dict[int, None] = {}  # insertion-ordered set
        for dep in deps[step_id]:
            if dep not in index:
                raise ValueError(f"step {step_id!r} depends on unknown step {dep!r}")
            indices[index[dep]] = None
        adjacency.append(list(indices))
    return ids, adjacency


def _strongly_connected_components(adjacency: list[list[int]]) -> list[list[int]]:
    """Iterative Tarjan. Returns every component; membership is order-independent."""
    n = len(adjacency)
    discovery = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    stack: list[int] = []
    components: list[list[int]] = []
    counter = 0

    for root in range(n):
        if discovery[root] != -1:
            continue
        discovery[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack[root] = True
        work: list[tuple[int, int]] = [(root, 0)]
        while work:
            node, cursor = work[-1]
            if cursor < len(adjacency[node]):
                work[-1] = (node, cursor + 1)
                neighbour = adjacency[node][cursor]
                if discovery[neighbour] == -1:
                    discovery[neighbour] = low[neighbour] = counter
                    counter += 1
                    stack.append(neighbour)
                    on_stack[neighbour] = True
                    work.append((neighbour, 0))
                elif on_stack[neighbour]:
                    low[node] = min(low[node], discovery[neighbour])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == discovery[node]:
                    component: list[int] = []
                    while True:
                        member = stack.pop()
                        on_stack[member] = False
                        component.append(member)
                        if member == node:
                            break
                    components.append(component)
    return components


def find_cycles(deps: Dependencies) -> tuple[tuple[StepId, ...], ...]:
    """Every dependency cycle, reported as its strongly connected component.

    A component is a cycle if it has two or more steps or a step that depends
    on itself. Steps that merely depend on a cycle, or are depended on by one,
    are not members. Members are listed in plan order; components are ordered
    by their earliest member's plan position. Empty tuple means acyclic.
    """
    ids, adjacency = _adjacency(deps)
    cyclic = [
        sorted(component)
        for component in _strongly_connected_components(adjacency)
        if len(component) > 1 or component[0] in adjacency[component[0]]
    ]
    cyclic.sort(key=lambda component: component[0])
    return tuple(tuple(ids[i] for i in component) for component in cyclic)


def _topological_indices(adjacency: list[list[int]]) -> list[int] | None:
    """Kahn's algorithm with earliest-plan-position tie-breaking; None if cyclic."""
    n = len(adjacency)
    remaining = [len(dependencies) for dependencies in adjacency]
    dependents: list[list[int]] = [[] for _ in range(n)]
    for node, dependencies in enumerate(adjacency):
        for dep in dependencies:
            dependents[dep].append(node)
    ready = [node for node in range(n) if remaining[node] == 0]
    heapify(ready)
    order: list[int] = []
    while ready:
        node = heappop(ready)
        order.append(node)
        for dependent in dependents[node]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                heappush(ready, dependent)
    return order if len(order) == n else None


def topological_order(deps: Dependencies) -> tuple[StepId, ...] | None:
    """A dependencies-first order, ties broken by plan order; None if there is a cycle."""
    ids, adjacency = _adjacency(deps)
    order = _topological_indices(adjacency)
    return None if order is None else tuple(ids[i] for i in order)


def longest_chain_length(deps: Dependencies) -> int | None:
    """Number of **nodes** on the longest dependency path (D-104); None if cyclic.

    0 for an empty graph, 1 for a single step (or any set of steps with no
    edges), regardless of how many disconnected components there are.
    """
    _, adjacency = _adjacency(deps)
    order = _topological_indices(adjacency)
    if order is None:
        return None
    depth = [0] * len(adjacency)
    for node in order:
        depth[node] = 1 + max((depth[dep] for dep in adjacency[node]), default=0)
    return max(depth, default=0)


def _maximum_bipartite_matching(adjacency: list[list[int]]) -> int:
    """Hopcroft–Karp, iterative. Left and right sides are both ``range(len(adjacency))``."""
    n = len(adjacency)
    match_left = [-1] * n
    match_right = [-1] * n
    matched = 0
    while True:
        # BFS: layer the left vertices by alternating-path distance from free ones.
        distance = [-1] * n
        queue: deque[int] = deque()
        for left in range(n):
            if match_left[left] == -1:
                distance[left] = 0
                queue.append(left)
        reaches_free_right = False
        while queue:
            left = queue.popleft()
            for right in adjacency[left]:
                partner = match_right[right]
                if partner == -1:
                    reaches_free_right = True
                elif distance[partner] == -1:
                    distance[partner] = distance[left] + 1
                    queue.append(partner)
        if not reaches_free_right:
            return matched

        # DFS: augment along shortest alternating paths, one root at a time.
        cursor = [0] * n
        for root in range(n):
            if match_left[root] != -1:
                continue
            lefts = [root]
            rights: list[int] = []  # rights[i] is the edge from lefts[i] to lefts[i + 1]
            while lefts:
                left = lefts[-1]
                if cursor[left] < len(adjacency[left]):
                    right = adjacency[left][cursor[left]]
                    cursor[left] += 1
                    partner = match_right[right]
                    if partner == -1:
                        rights.append(right)
                        for path_left, path_right in zip(lefts, rights):
                            match_left[path_left] = path_right
                            match_right[path_right] = path_left
                        matched += 1
                        break
                    if distance[partner] == distance[left] + 1:
                        rights.append(right)
                        lefts.append(partner)
                else:
                    distance[left] = -1  # dead end for the rest of this phase
                    lefts.pop()
                    if rights:
                        rights.pop()


def max_antichain_width(deps: Dependencies) -> int | None:
    """Size of the largest set of steps no two of which are ordered by a path (D-050).

    Exact, by Dilworth's theorem: width = steps - maximum matching on the
    transitive closure. The widest *level* of the graph is only a lower bound
    (steps ``s->q, s->t, t->r`` plus an isolated ``p`` have widest level 2 but
    the antichain ``{p, q, t}`` has 3), so it is deliberately not used.

    None if the graph is cyclic (the order is undefined); 0 if empty.

    Cost grows with the number of comparable pairs, up to quadratic in the
    step count in both time and memory. Callers must bound the step count
    first (``max_nodes``) and not call this on an unbounded plan.
    """
    _, adjacency = _adjacency(deps)
    order = _topological_indices(adjacency)
    if order is None:
        return None
    n = len(adjacency)

    # ancestors[v] is a bitset of every step v transitively depends on.
    ancestors = [0] * n
    for node in order:
        bits = 0
        for dep in adjacency[node]:
            bits |= ancestors[dep] | (1 << dep)
        ancestors[node] = bits

    # Bipartite graph: left u -> right v whenever u is an ancestor of v.
    comparable: list[list[int]] = [[] for _ in range(n)]
    for node in range(n):
        bits = ancestors[node]
        while bits:
            lowest = bits & -bits
            comparable[lowest.bit_length() - 1].append(node)
            bits ^= lowest
    return n - _maximum_bipartite_matching(comparable)
