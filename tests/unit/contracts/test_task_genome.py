"""TaskGenome (decisions.md D-013, D-014, D-031, D-045, D-056, D-068, D-077, D-080, D-089, D-099)."""

import pytest
from pydantic import ValidationError

from eidos.contracts import ActionId, AutonomyLevel, CapabilityId, DEFAULT_TENANT_ID, TaskGenome

from eidos_factories import make_reliability_contract, make_task_genome


def test_valid_construction_with_only_required_fields():
    genome = make_task_genome()
    assert genome.information_dependencies == ()


def test_required_capabilities_may_be_empty():
    genome = make_task_genome(required_capabilities=())
    assert genome.required_capabilities == ()


def test_allowed_actions_may_be_empty():
    genome = make_task_genome(allowed_actions=())
    assert genome.allowed_actions == ()


def test_allowed_actions_accepts_action_ids():
    genome = make_task_genome(allowed_actions=(ActionId("read_documents"), ActionId("read_repository")))
    assert genome.allowed_actions == ("read_documents", "read_repository")


def test_information_dependencies_defaults_to_empty_tuple_when_omitted():
    genome = make_task_genome()
    assert genome.information_dependencies == ()
    assert isinstance(genome.information_dependencies, tuple)


def test_information_dependencies_accepts_opaque_strings():
    genome = make_task_genome(information_dependencies=("prior_incident_report",))
    assert genome.information_dependencies == ("prior_incident_report",)


def test_tenant_id_defaults_when_omitted():
    contract = make_reliability_contract()
    genome = TaskGenome(
        goal="Assess migration readiness",
        required_capabilities=(CapabilityId("research"),),
        risk_level=contract.max_risk_level,
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
        allowed_actions=(),
        reliability_contract_id=contract.contract_id,
    )
    assert genome.tenant_id == DEFAULT_TENANT_ID


def test_empty_goal_is_rejected():
    with pytest.raises(ValidationError):
        make_task_genome(goal="")


def _valid_task_genome_kwargs() -> dict:
    contract = make_reliability_contract()
    return dict(
        tenant_id=contract.tenant_id,
        goal="Assess migration readiness",
        required_capabilities=(CapabilityId("research"),),
        risk_level=contract.max_risk_level,
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
        allowed_actions=(),
        reliability_contract_id=contract.contract_id,
    )


@pytest.mark.parametrize(
    "omitted_field",
    ["goal", "required_capabilities", "risk_level", "autonomy_level", "allowed_actions", "reliability_contract_id"],
)
def test_omitting_a_required_field_is_rejected(omitted_field):
    kwargs = _valid_task_genome_kwargs()
    del kwargs[omitted_field]
    with pytest.raises(ValidationError):
        TaskGenome(**kwargs)


def test_required_capabilities_rejects_none():
    with pytest.raises(ValidationError):
        make_task_genome(required_capabilities=None)


def test_allowed_actions_rejects_none():
    with pytest.raises(ValidationError):
        make_task_genome(allowed_actions=None)


def test_risk_level_rejects_none():
    with pytest.raises(ValidationError):
        make_task_genome(risk_level=None)


def test_invalid_autonomy_level_value_is_rejected():
    with pytest.raises(ValidationError):
        make_task_genome(autonomy_level=5)


def test_reliability_contract_id_rejects_none():
    # decisions.md D-045: every TaskGenome must reference a ReliabilityContract.
    with pytest.raises(ValidationError):
        make_task_genome(reliability_contract_id=None)


def test_genome_does_not_carry_mission_id():
    # decisions.md D-068: mission ownership is by containment, not a field.
    with pytest.raises(ValidationError):
        make_task_genome(mission_id="anything")


def test_genome_does_not_carry_evidence_requirements():
    # decisions.md D-031: no replacement representation is defined in V0.1.
    with pytest.raises(ValidationError):
        make_task_genome(evidence_requirements=("must cite the architecture docs",))


def test_genome_does_not_duplicate_contract_thresholds():
    # decisions.md D-013: constraint thresholds are not duplicated in the genome.
    with pytest.raises(ValidationError):
        make_task_genome(quality_threshold=0.9)


def test_model_is_immutable():
    genome = make_task_genome()
    with pytest.raises(ValidationError):
        genome.goal = "something else"


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_task_genome(unexpected_field=123)
