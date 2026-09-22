"""``CandidateGenerator`` and the deterministic reference implementation (decisions.md D-178 to D-182; V0.7 Step 3).

**The Jev principle, translated.** EIDOS constructs the feasible decision space; a future model may choose from it,
but never defines what is valid (V0.7 Step 1's own translation of the Jev lesson). This module is where that
boundary actually lives for strategies: ``CandidateGenerator.generate`` is a pure function of
``task_genome.required_capabilities`` — the mission-scoped capability set D-102 already established, not
``CapabilityRegistry`` (which resolves capability to *agent*, a later, separate concern, D-134) — so there is no
code path through which it could ever construct a ``StrategyStage`` naming a capability the mission does not
declare. Identity (``strategy_id``) is not drawn here at all: ``generate`` returns ``StrategyShape``, not
``Strategy`` — see ``pipeline.py`` for where identity is stamped on, and ``strategy.py``'s module docstring for why.

**Exactly three rule-based shapes, gated so a guaranteed duplicate is never even constructed** (not left to
deduplication to clean up, though ``pipeline.py``'s own dedup is still the defense-in-depth backstop for any
generator, this one included):

- **linear** — one stage per distinct required capability, in the genome's own order. The only shape produced when
  there are 0 or 1 capabilities.
- **parallel** — every distinct capability in one single stage. Identical to *linear* when there are fewer than 2
  capabilities (a "stage of one" is the same content either way), so it is not produced then.
- **staged** — the first capability alone, then every remaining one together in a second stage. Identical to
  *linear* when there are fewer than 3 capabilities (with only one "remaining" capability, "staged" and "linear"
  produce the same single-item second stage), so it is not produced then.

**Verification is not an independent axis to permute.** D-179 approves verification posture as one of three
dimensions a `Strategy` may express, but multiplying every topology by every posture would inflate candidate count
without adding a meaningfully different execution approach — exactly what item "do not generate meaningless
permutations" warns against. Instead it is *determined* by whether there is anything to verify: `FINAL` whenever
at least one capability is allocated, `NONE` for the empty case. A future generator (LLM-assisted or otherwise)
may treat it as an independent axis once there is a second real posture to choose between (D-179's own limit:
only one deterministic ``Verifier`` exists today, D-133).

**``required_capabilities`` is deduplicated before any shape is built** (first-occurrence order preserved): nothing
in ``TaskGenome`` forbids a repeated entry, and a strategy built from raw duplicates would misrepresent capability
*allocation* (D-179 item 3) — two list entries for the same capability is not two roles.
"""

from typing import Protocol

from eidos.contracts import CapabilityId, TaskGenome

from .strategy import StrategyShape, StrategyStage, VerificationPosture


class CandidateGenerator(Protocol):
    """A pure function of ``TaskGenome`` (`required_capabilities` only) to a tuple of identity-free strategy shapes.

    No I/O, no clock, no randomness, no model call for the reference implementation below; nothing in this
    Protocol requires that of a future adapter, but ``pipeline.generate_candidate_strategies`` never trusts one to
    have kept the capability rule regardless (see its own module docstring).
    """

    def generate(self, task_genome: TaskGenome) -> tuple[StrategyShape, ...]: ...


def _distinct_capabilities(task_genome: TaskGenome) -> tuple[CapabilityId, ...]:
    """``required_capabilities``, deduplicated, first-occurrence order preserved."""
    seen: dict[CapabilityId, None] = {}  # insertion-ordered; membership only, iterated only for its keys' order
    for capability in task_genome.required_capabilities:
        seen[capability] = None
    return tuple(seen)


def _empty_shape() -> StrategyShape:
    return StrategyShape(
        stages=(), verification=VerificationPosture.NONE, rationale="no required capabilities: nothing to allocate"
    )


def _linear_shape(capabilities: tuple[CapabilityId, ...]) -> StrategyShape:
    stages = tuple(StrategyStage(capabilities=(capability,)) for capability in capabilities)
    listed = ", ".join(capabilities)
    return StrategyShape(
        stages=stages,
        verification=VerificationPosture.FINAL,
        rationale=f"sequential: {listed}, one capability at a time — minimizes concurrent agent calls",
    )


def _parallel_shape(capabilities: tuple[CapabilityId, ...]) -> StrategyShape | None:
    if len(capabilities) < 2:
        return None  # identical content to the linear shape
    listed = ", ".join(capabilities)
    return StrategyShape(
        stages=(StrategyStage(capabilities=capabilities),),
        verification=VerificationPosture.FINAL,
        rationale=f"parallel: {listed} run concurrently in one stage — minimizes latency, maximizes peak concurrency",
    )


def _staged_shape(capabilities: tuple[CapabilityId, ...]) -> StrategyShape | None:
    if len(capabilities) < 3:
        return None  # identical content to the linear shape
    first, rest = capabilities[0], capabilities[1:]
    listed = ", ".join(rest)
    return StrategyShape(
        stages=(StrategyStage(capabilities=(first,)), StrategyStage(capabilities=rest)),
        verification=VerificationPosture.FINAL,
        rationale=f"staged: {first} first, then {listed} together — targets {first}'s output before broadening",
    )


class RuleBasedCandidateGenerator:
    """The deterministic reference ``CandidateGenerator``. See the module docstring for the three shapes."""

    def generate(self, task_genome: TaskGenome) -> tuple[StrategyShape, ...]:
        capabilities = _distinct_capabilities(task_genome)
        if not capabilities:
            return (_empty_shape(),)
        shapes = (_linear_shape(capabilities), _parallel_shape(capabilities), _staged_shape(capabilities))
        return tuple(shape for shape in shapes if shape is not None)
