"""Typed contracts — the shared vocabulary every other EIDOS layer is written against.

Milestone V0.1. Empty by design: no contract is implemented yet.

Planned members, with their specification documents:

- ``TaskGenome``          docs/04_task_genome.md
- ``ReliabilityContract`` docs/10_reliability.md
- ``MissionState``        docs/06_mission_state.md
- ``MissionEvent``        docs/06_mission_state.md
- ``Plan`` / ``PlanStep`` docs/05_plan_dsl.md  (ID-addressed DAG, decision D-004)
- ``AgentTask``           docs/07_a2a_contract.md

Constraints on anything added here:

- Pydantic v2. Typed and validated; no untyped dict crosses this boundary.
- This package depends on nothing else inside ``eidos``.
- No model, vendor or SDK reference (invariant 9).
- No I/O, no network, no LLM calls. V0.1 is in-memory only (decision D-005).

V0.1 is partially blocked. See the "Blocked on human owner" table in ``progress.md``.
"""
