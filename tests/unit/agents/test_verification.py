"""The deterministic Verification Agent (decisions.md D-133, D-138, D-146; invariants 12 and 13).

A PASS means the V0.4 verification rules passed. It never means the reliability contract was satisfied, and every
verdict names the clauses that were NOT_EVALUATED.
"""

import json
import threading
from pathlib import Path

import pytest

from eidos.agents import (
    NOT_EVALUATED_CLAUSES,
    InMemoryArtifactStore,
    Rule,
    RuleOutcome,
    VerificationAgent,
)
from eidos.contracts import StepId
from eidos.runtime import NodeResult, NodeStatus, VerificationVerdict
from eidos.contracts import PlanStepKind

from eidos_agents_factories import compiled_with, context_requiring, doc, node_of
from eidos_runtime_factories import succeeded_result

SPEC = {"gather": "", "analyse": "gather", "check": "analyse"}
CAPABILITIES = {"gather": "research", "analyse": "cost"}


def setup(evidence=3, analysis_sources=("artifact:gather", "doc:1"), analysis_content="Analysis.", **contract_overrides):
    """Three supplied documents; a research artifact citing all three; an analysis artifact citing ``analysis_sources``."""
    compiled = compiled_with(SPEC, CAPABILITIES, verify=("check",))
    context = context_requiring(compiled, evidence, **contract_overrides)
    store = InMemoryArtifactStore()
    for n in (1, 2, 3):
        store.put_supplied(context.execution_id, doc(f"doc:{n}", f"source {n}"))
    store.put_step_artifact(context.execution_id, StepId("gather"), doc("artifact:gather", "Findings.", sources=("doc:1", "doc:2", "doc:3")))
    store.put_step_artifact(context.execution_id, StepId("analyse"), doc("artifact:analyse", analysis_content, sources=analysis_sources))
    return VerificationAgent(store=store), store, context, compiled


def verify(agent, context, compiled, predecessors=("analyse",)):
    results = tuple(succeeded_result(step) for step in predecessors)
    return agent.verify(context, node_of(compiled, StepId("check")), results), agent.report(context, results)


def rule(report, which):
    return next(result for result in report.rules if result.rule is which)


# --- PASS, and what a PASS does not claim -----------------------------------------------------------------------------


def test_the_rules_pass_when_the_artifacts_are_well_formed_cited_and_enough_sources_are_reached():
    agent, _, context, compiled = setup()
    result, report = verify(agent, context, compiled)

    assert result.verdict is VerificationVerdict.PASS
    assert [(r.rule, r.outcome) for r in report.rules] == [
        (Rule.SCHEMA_VALIDITY, RuleOutcome.SATISFIED),
        (Rule.CITATION_COVERAGE, RuleOutcome.SATISFIED),
        (Rule.MINIMUM_DISTINCT_SOURCES, RuleOutcome.SATISFIED),
    ]
    assert "3 distinct supplied source(s) reached, 3 required" in rule(report, Rule.MINIMUM_DISTINCT_SOURCES).detail


def test_a_pass_names_what_was_not_evaluated_and_never_claims_the_contract_is_satisfied():
    agent, _, context, compiled = setup()
    result, _ = verify(agent, context, compiled)

    assert result.verdict is VerificationVerdict.PASS
    assert "NOT_EVALUATED: min_quality, max_risk_level" in result.reason
    assert "not a claim that the reliability contract is satisfied" in result.reason
    assert NOT_EVALUATED_CLAUSES == ("min_quality", "max_risk_level")


@pytest.mark.parametrize("min_quality", [0.0, 0.5, 1.0])
def test_min_quality_changes_nothing_because_no_quality_is_measured(min_quality):
    baseline_agent, _, context, compiled = setup()
    baseline, _ = verify(baseline_agent, context, compiled)
    agent, _, other_context, other_compiled = setup(min_quality=min_quality)
    result, _ = verify(agent, other_context, other_compiled)
    assert (result.verdict, result.reason) == (baseline.verdict, baseline.reason)


def test_every_verdict_pass_fail_or_inconclusive_states_what_was_not_evaluated():
    agent, store, context, compiled = setup(analysis_sources=("ghost",))
    failed, _ = verify(agent, context, compiled)
    inconclusive, _ = verify(agent, context, compiled, predecessors=())
    for result in (failed, inconclusive):
        assert "NOT_EVALUATED: min_quality, max_risk_level" in result.reason


# --- FAIL: a rule is violated --------------------------------------------------------------------------------------------


def test_a_citation_of_something_that_does_not_exist_fails_however_well_formed_the_output_is():
    agent, _, context, compiled = setup(analysis_sources=("artifact:gather", "ghost"))
    result, report = verify(agent, context, compiled)
    assert result.verdict is VerificationVerdict.FAIL
    assert rule(report, Rule.CITATION_COVERAGE).outcome is RuleOutcome.VIOLATED
    assert "'ghost', which does not exist" in result.reason


def test_an_artifact_that_cites_no_source_fails():
    agent, _, context, compiled = setup(analysis_sources=())
    result, report = verify(agent, context, compiled)
    assert result.verdict is VerificationVerdict.FAIL
    assert "cites no source" in rule(report, Rule.CITATION_COVERAGE).detail


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_an_artifact_with_no_content_fails_the_schema_rule(content):
    agent, _, context, compiled = setup(analysis_content=content)
    result, report = verify(agent, context, compiled)
    assert result.verdict is VerificationVerdict.FAIL
    assert rule(report, Rule.SCHEMA_VALIDITY).outcome is RuleOutcome.VIOLATED


def test_an_unsupported_content_type_fails_the_schema_rule():
    agent, store, context, compiled = setup()
    other = compiled_with({"gather": "", "analyse": "gather", "check": "analyse"}, CAPABILITIES, verify=("check",))
    store.put_step_artifact(context.execution_id, StepId("odd"), doc("artifact:odd", "x", content_type="application/x-thing", sources=("doc:1",)))
    results = (NodeResult(step_id=StepId("odd"), kind=PlanStepKind.AGENT, status=NodeStatus.SUCCEEDED, artifact="artifact:odd"),)
    report = agent.report(context, results)
    assert rule(report, Rule.SCHEMA_VALIDITY).outcome is RuleOutcome.VIOLATED
    assert "unsupported content type 'application/x-thing'" in rule(report, Rule.SCHEMA_VALIDITY).detail
    assert other is not None


def test_too_few_distinct_sources_fails():
    agent, _, context, compiled = setup(evidence=4)
    result, report = verify(agent, context, compiled)
    assert result.verdict is VerificationVerdict.FAIL
    assert rule(report, Rule.MINIMUM_DISTINCT_SOURCES).outcome is RuleOutcome.VIOLATED
    assert "3 distinct supplied source(s) reached, 4 required" in result.reason


def test_a_requirement_of_zero_sources_is_met_by_any_number():
    agent, _, context, compiled = setup(evidence=0)
    assert rule(verify(agent, context, compiled)[1], Rule.MINIMUM_DISTINCT_SOURCES).outcome is RuleOutcome.SATISFIED


# --- how sources are counted ---------------------------------------------------------------------------------------------


def test_sources_are_followed_through_produced_artifacts_to_the_supplied_documents_behind_them():
    agent, _, context, compiled = setup(analysis_sources=("artifact:gather",))  # cites only the research artifact
    report = verify(agent, context, compiled)[1]
    assert rule(report, Rule.MINIMUM_DISTINCT_SOURCES).outcome is RuleOutcome.SATISFIED  # reached doc:1..3 through it


def test_a_document_reached_by_two_paths_is_counted_once():
    agent, _, context, compiled = setup(evidence=4, analysis_sources=("artifact:gather", "doc:1", "doc:2", "doc:3"))
    assert "3 distinct supplied source(s) reached" in rule(verify(agent, context, compiled)[1], Rule.MINIMUM_DISTINCT_SOURCES).detail


def test_a_produced_artifact_is_not_itself_a_source_document():
    agent, store, context, compiled = setup(evidence=1, analysis_sources=("artifact:gather",))
    # replace the research artifact's citations with nothing reachable: only produced artifacts remain in the chain
    other_store = InMemoryArtifactStore()
    other_store.put_step_artifact(context.execution_id, StepId("gather"), doc("artifact:gather", "Findings.", sources=("artifact:analyse",)))
    other_store.put_step_artifact(context.execution_id, StepId("analyse"), doc("artifact:analyse", "Analysis.", sources=("artifact:gather",)))
    report = VerificationAgent(store=other_store).report(context, (succeeded_result("analyse"),))
    assert "0 distinct supplied source(s) reached, 1 required" in rule(report, Rule.MINIMUM_DISTINCT_SOURCES).detail  # and it terminates
    assert store is not other_store and agent is not None


# --- INCONCLUSIVE: a rule could not be performed (never a pass) ------------------------------------------------------------


def test_nothing_to_verify_is_inconclusive_never_a_pass():
    agent, _, context, compiled = setup()
    result, report = verify(agent, context, compiled, predecessors=())
    assert result.verdict is VerificationVerdict.INCONCLUSIVE
    assert all(r.outcome is RuleOutcome.UNPERFORMABLE for r in report.rules)
    assert "nothing to verify" in result.reason


def test_a_predecessor_that_produced_no_artifact_leaves_nothing_to_verify():
    agent, _, context, compiled = setup()
    no_artifact = NodeResult(step_id=StepId("other"), kind=PlanStepKind.VERIFY, status=NodeStatus.SUCCEEDED, reason="verified")
    assert agent.verify(context, node_of(compiled, StepId("check")), (no_artifact,)).verdict is VerificationVerdict.INCONCLUSIVE


def test_an_artifact_the_store_cannot_produce_makes_every_rule_unperformable():
    agent, _, context, compiled = setup()
    result, report = verify(agent, context, compiled, predecessors=("analyse", "missing_step"))
    assert result.verdict is VerificationVerdict.INCONCLUSIVE
    assert {r.outcome for r in report.rules} == {RuleOutcome.UNPERFORMABLE}
    assert "could not be read from the store" in result.reason


def test_an_artifact_of_another_execution_is_not_visible():
    agent, store, context, compiled = setup()
    from uuid import UUID
    from eidos.contracts import ExecutionId

    elsewhere = context.model_copy(update={"execution_id": ExecutionId(UUID(int=4242))})
    assert agent.verify(elsewhere, node_of(compiled, StepId("check")), (succeeded_result("analyse"),)).verdict is VerificationVerdict.INCONCLUSIVE


def test_a_violation_outranks_a_rule_that_could_not_be_performed():
    agent, store, context, compiled = setup(analysis_content="")
    result, _ = verify(agent, context, compiled, predecessors=("analyse", "missing_step"))
    assert result.verdict is VerificationVerdict.FAIL


# --- no model, no scalar, deterministic --------------------------------------------------------------------------------------


def test_the_verifier_holds_only_the_store_so_it_has_no_model_to_ask():
    assert [f for f in VerificationAgent.__dataclass_fields__] == ["store"]
    source = (Path(__file__).resolve().parents[3] / "src" / "eidos" / "agents" / "verification.py").read_text(encoding="utf-8")
    for forbidden in ("ModelPort", "ModelRequest", "complete(", ".model"):
        assert forbidden not in source.replace("from .base import", ""), forbidden


def test_the_verdict_is_a_word_and_a_reason_never_a_number():
    agent, _, context, compiled = setup()
    result, _ = verify(agent, context, compiled)
    assert sorted(json.loads(result.model_dump_json())) == ["reason", "verdict"]


def test_the_same_inputs_give_the_same_verdict_and_reason_every_time_and_on_every_thread():
    agent, _, context, compiled = setup(analysis_sources=("artifact:gather", "ghost"))
    first, _ = verify(agent, context, compiled)
    seen = []
    lock = threading.Lock()

    def work():
        found, _ = verify(agent, context, compiled)
        with lock:
            seen.append(found)

    threads = [threading.Thread(target=work) for _ in range(32)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(found == first for found in seen)
    assert [r.rule for r in agent.report(context, (succeeded_result("analyse"),)).rules] == list(Rule)  # a fixed order


def test_verification_reads_the_store_and_never_writes_it():
    agent, store, context, compiled = setup()
    before = (store.get_step_artifact(context.execution_id, StepId("analyse")), store.supplied(context.execution_id))
    verify(agent, context, compiled)
    assert (store.get_step_artifact(context.execution_id, StepId("analyse")), store.supplied(context.execution_id)) == before
