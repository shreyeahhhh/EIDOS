"""The Verification Agent: a deterministic rule set behind the ``Verifier`` port (decisions.md D-133, D-138, D-146).

It is reached by ``VERIFY`` node kind, not by capability (D-133, D-144). **No model is consulted for a verdict** (D-138): the
verdict is a pure function of the artifacts under verification, the artifact store and the frozen ``ReliabilityContract``.

The rules (D-146 names them; their exact definition is here). Over the artifacts the ``VERIFY`` node's predecessors produced:

- ``schema_validity``: each artifact is in the store, has a supported content type, and has non-blank content;
- ``citation_coverage``: each artifact cites at least one source, and every source it cites exists in the store;
- ``minimum_distinct_sources``: following citations through produced artifacts, the number of distinct *supplied* documents
  reached is at least the contract's ``min_independent_evidence``.

Each rule is ``SATISFIED``, ``VIOLATED`` or ``UNPERFORMABLE`` (it could not be checked: nothing to verify, or an artifact could
not be read). Any ``VIOLATED`` gives ``FAIL``; otherwise any ``UNPERFORMABLE`` gives ``INCONCLUSIVE`` (never a pass, invariant
13); otherwise ``PASS``.

**A ``PASS`` means these rules passed. It never means the reliability contract was satisfied** (D-146). Clauses with no defined
deterministic measurement are ``NOT_EVALUATED`` and are named in every verdict's reason: ``min_quality`` (no quality metric is
invented) and ``max_risk_level`` (how a run's risk is determined is D-057, Open). The six budget clauses are runtime accounting
(D-127), not verification clauses. No scalar is produced (D-121).

The ``Verifier`` port carries only a verdict and a reason (D-121), so the typed ``VerificationReport`` kept here is rendered into
the reason; nothing in the runtime changes.
"""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field

from eidos.compiler import VerifyNode
from eidos.contracts import ArtifactRef, EidosModel
from eidos.runtime import ExecutionContext, NodeResult, VerificationResult, VerificationVerdict

from .artifacts import Artifact, ArtifactStore
from .base import SUPPORTED_CONTENT_TYPES

NOT_EVALUATED_CLAUSES: tuple[str, ...] = ("min_quality", "max_risk_level")


class Rule(StrEnum):
    SCHEMA_VALIDITY = "schema_validity"
    CITATION_COVERAGE = "citation_coverage"
    MINIMUM_DISTINCT_SOURCES = "minimum_distinct_sources"


class RuleOutcome(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNPERFORMABLE = "unperformable"  # the rule could not be checked; never read as satisfied


class RuleResult(EidosModel):
    rule: Rule
    outcome: RuleOutcome
    detail: str = Field(min_length=1)


class VerificationReport(EidosModel):
    """Every rule's result, in a fixed order, and the clauses that were not evaluated."""

    rules: tuple[RuleResult, ...]
    not_evaluated: tuple[str, ...] = NOT_EVALUATED_CLAUSES

    @property
    def verdict(self) -> VerificationVerdict:
        outcomes = {result.outcome for result in self.rules}
        if RuleOutcome.VIOLATED in outcomes:
            return VerificationVerdict.FAIL
        if RuleOutcome.UNPERFORMABLE in outcomes or not self.rules:
            return VerificationVerdict.INCONCLUSIVE
        return VerificationVerdict.PASS

    def reason(self) -> str:
        parts = "; ".join(f"{r.rule.value} {r.outcome.value} ({r.detail})" for r in self.rules)
        clauses = ", ".join(self.not_evaluated)
        return (
            f"{parts}. NOT_EVALUATED: {clauses} (no defined deterministic measurement). "
            "This verdict covers the V0.4 verification rules only; it is not a claim that the reliability contract is satisfied."
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class VerificationAgent:
    store: ArtifactStore

    def verify(self, context: ExecutionContext, node: VerifyNode, predecessors: tuple[NodeResult, ...]) -> VerificationResult:
        report = self.report(context, predecessors)
        reason = report.reason()
        if report.verdict is VerificationVerdict.PASS:
            return VerificationResult.passed(reason)
        if report.verdict is VerificationVerdict.FAIL:
            return VerificationResult.failed(reason)
        return VerificationResult.inconclusive(reason)

    def report(self, context: ExecutionContext, predecessors: tuple[NodeResult, ...]) -> VerificationReport:
        execution_id = context.execution_id
        refs = tuple(result.artifact for result in predecessors if result.artifact is not None)
        if not refs:
            nothing = "no predecessor produced an artifact, so there is nothing to verify"
            return VerificationReport(rules=tuple(RuleResult(rule=rule, outcome=RuleOutcome.UNPERFORMABLE, detail=nothing) for rule in Rule))

        fetched = tuple(self.store.get(execution_id, ref) for ref in refs)
        missing = tuple(ref for ref, artifact in zip(refs, fetched) if artifact is None)
        artifacts = tuple(artifact for artifact in fetched if artifact is not None)

        schema = self._schema(artifacts, missing)
        if missing:
            unreadable = f"artifact(s) {', '.join(repr(str(m)) for m in missing)} could not be read from the store"
            others = tuple(RuleResult(rule=rule, outcome=RuleOutcome.UNPERFORMABLE, detail=unreadable)
                           for rule in (Rule.CITATION_COVERAGE, Rule.MINIMUM_DISTINCT_SOURCES))
            return VerificationReport(rules=(schema, *others))
        citation = self._citations(execution_id, artifacts)
        distinct = self._distinct_sources(context, artifacts)
        return VerificationReport(rules=(schema, citation, distinct))

    # --- the rules ----------------------------------------------------------------------------------------------------

    @staticmethod
    def _schema(artifacts: tuple[Artifact, ...], missing: tuple[ArtifactRef, ...]) -> RuleResult:
        problems = []
        for artifact in artifacts:
            if artifact.content_type not in SUPPORTED_CONTENT_TYPES:
                problems.append(f"{str(artifact.ref)!r} has unsupported content type {artifact.content_type!r}")
            if not artifact.content.strip():
                problems.append(f"{str(artifact.ref)!r} has no content")
        if problems:
            return RuleResult(rule=Rule.SCHEMA_VALIDITY, outcome=RuleOutcome.VIOLATED, detail="; ".join(problems))
        if missing:
            return RuleResult(rule=Rule.SCHEMA_VALIDITY, outcome=RuleOutcome.UNPERFORMABLE,
                              detail=f"{len(missing)} artifact(s) could not be read from the store")
        return RuleResult(rule=Rule.SCHEMA_VALIDITY, outcome=RuleOutcome.SATISFIED, detail=f"{len(artifacts)} artifact(s) well-formed")

    def _citations(self, execution_id, artifacts: tuple[Artifact, ...]) -> RuleResult:
        problems = []
        for artifact in artifacts:
            if not artifact.source_refs:
                problems.append(f"{str(artifact.ref)!r} cites no source")
            for source in artifact.source_refs:
                if self.store.get(execution_id, source) is None:
                    problems.append(f"{str(artifact.ref)!r} cites {str(source)!r}, which does not exist")
        if problems:
            return RuleResult(rule=Rule.CITATION_COVERAGE, outcome=RuleOutcome.VIOLATED, detail="; ".join(problems))
        return RuleResult(rule=Rule.CITATION_COVERAGE, outcome=RuleOutcome.SATISFIED, detail="every artifact cites sources that exist")

    def _distinct_sources(self, context: ExecutionContext, artifacts: tuple[Artifact, ...]) -> RuleResult:
        execution_id = context.execution_id
        required = context.reliability_contract.min_independent_evidence
        supplied = {artifact.ref for artifact in self.store.supplied(execution_id)}  # membership only
        reached: dict[ArtifactRef, None] = {}  # distinct supplied documents, membership only
        visited: dict[ArtifactRef, None] = {}
        pending = [source for artifact in artifacts for source in artifact.source_refs]
        while pending:
            ref = pending.pop()
            if ref in visited:
                continue
            visited[ref] = None
            if ref in supplied:
                reached[ref] = None
            cited = self.store.get(execution_id, ref)
            if cited is not None:
                pending.extend(cited.source_refs)
        found = len(reached)
        detail = f"{found} distinct supplied source(s) reached, {required} required"
        outcome = RuleOutcome.SATISFIED if found >= required else RuleOutcome.VIOLATED
        return RuleResult(rule=Rule.MINIMUM_DISTINCT_SOURCES, outcome=outcome, detail=detail)
