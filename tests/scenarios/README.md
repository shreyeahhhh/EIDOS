# tests/scenarios

**Layer definition (handoff §62):** full missions, replanning, verification failures, budget
exhaustion, policy violations.

Scenario tests run a whole mission and assert on its outcome and its recorded history. They are the
tests that prove the *product* behaves as specified, not just that the parts work.

## What belongs here

| Scenario | Asserts | Milestone |
|---|---|---|
| Baseline mission completes end-to-end | The §49 MVP chain: task → genome → candidates → validation → execution → evaluation → history | V0.4 |
| Verification fails, replan, retrieve more, verify again | Invariant 12; plan v2 with recorded lineage and reason (§15, §43) | V0.4+ |
| Reliability contract cannot be met | Invariant 13 — reports "cannot satisfy", does **not** return a confident-looking answer (§30, §47) | V1.2 |
| Retry budget exhausted | Invariant 7 — `MISSION PAUSED`, human review required (§32) | V1.2 |
| Replan budget exhausted | Invariant 7 | V1.2 |
| Token budget exhausted | Invariant 7 | V1.2 |
| Tool budget exhausted | Invariant 7 | V1.2 |
| Policy violation | Invariant 14 — deterministic refusal, not a prompt-level refusal (§29) | V1.2 |
| Bad retrieval / conflicting evidence | §63; evidence rejected rather than used | V0.8 |
| Replay from recorded events | Invariant 15 — the mission timeline reconstructs with **no agent invoked** (§73) | V0.5 |
| Evidence lineage | Invariant 16 — conclusion walks back to source and retrieval query (§74) | V0.8 |

## Rules

- A scenario test asserts on the recorded event history, not only the final answer. "It returned
  something" is not a passing condition (invariant 12).
- No fabricated fixtures presented as measurements. A scenario may use fixed inputs; it may not
  bake in a quality score and call it measured (CLAUDE.md §7).

Currently empty. The first scenario tests arrive with V0.4.
