# tests/unit

**Layer definition (handoff §62):** schemas, validators, reducers, scoring, policy.

Unit tests cover a single component in isolation, with no I/O, no network and no external service.
The deterministic parts of EIDOS — contracts, the plan validator, the compiler, the state reducer,
scoring and policy evaluation — are all verified here.

## What belongs here

| Component | Milestone |
|---|---|
| Contract construction, field validation, **rejection of invalid input** | V0.1 |
| Plan DSL validator: valid plans, dependency errors, cycles, max depth, max nodes, max parallel branches, unknown capabilities, invalid operations, policy violations, resource violations (§58) | V0.2 — `tests/unit/validation/` (policy is `NOT_APPLICABLE`, D-110) |
| Compiler determinism | V0.3 — `tests/unit/compiler/` (Step 2: the compiled form and `compile_plan`) |
| Runtime execution semantics: level-synchronous runs, node statuses, ports, admission, prior outcomes | V0.3 — `tests/unit/runtime/` (Step 3: the sequential reference executor) |
| Static guards on the LangGraph backend package: who may import LangGraph, and which of its features are ruled out | V0.3 — `tests/unit/backends/` (Step 4; runs without LangGraph installed) |
| State reducer, including duplicate and out-of-order event handling | V0.5 |
| Scoring and quality proxies | V1.0 |
| Policy and autonomy evaluation | V1.2 |

## Rules

- Write failure-path tests, not only happy paths (CLAUDE.md §6).
- Never weaken a test, delete a failing test, skip it, or suppress an error to get green.
- Deterministic components must be tested as deterministic: same input, same output, no clock, no
  randomness, no hidden state.

The unit suites are listed above by milestone; each subdirectory holds one component's tests.
