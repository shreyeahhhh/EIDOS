"""``RuleBasedCandidateGenerator`` — the deterministic reference ``CandidateGenerator`` (decisions.md D-178 to
D-182; V0.7 Step 3). ``generate_candidate_strategies`` (dedup, capability re-check, identity, capping) is tested
separately in ``test_planning_pipeline.py``; these tests are about the generator's own raw output only.
"""

from eidos.contracts import CapabilityId
from eidos.planning import RuleBasedCandidateGenerator, StrategyStage, VerificationPosture

from eidos_planning_factories import genome_with

GENERATOR = RuleBasedCandidateGenerator()


def shapes_for(*capabilities: str):
    return GENERATOR.generate(genome_with(*capabilities))


def _stage(*capabilities: str) -> StrategyStage:
    return StrategyStage(capabilities=tuple(CapabilityId(c) for c in capabilities))


# --- 1. empty required-capability input ---------------------------------------------------------------------------


def test_no_required_capabilities_produces_exactly_one_empty_shape():
    shapes = shapes_for()
    assert len(shapes) == 1
    shape = shapes[0]
    assert shape.stages == ()
    assert shape.verification is VerificationPosture.NONE


# --- 2. one capability ------------------------------------------------------------------------------------------


def test_one_capability_produces_exactly_one_shape():
    # parallel/staged both degenerate to the same content as linear for a single capability; neither is produced.
    shapes = shapes_for("research")
    assert len(shapes) == 1
    shape = shapes[0]
    assert shape.stages == (_stage("research"),)
    assert shape.verification is VerificationPosture.FINAL


# --- 3. multiple capabilities -----------------------------------------------------------------------------------


def test_two_capabilities_produce_linear_and_parallel_only():
    shapes = shapes_for("research", "cost")
    assert len(shapes) == 2
    shapes_by_stage_count = sorted((len(shape.stages) for shape in shapes))
    assert shapes_by_stage_count == [1, 2]  # parallel (1 stage) and linear (2 stages); staged degenerates away


def test_three_capabilities_produce_all_three_shapes():
    shapes = shapes_for("research", "cost", "security")
    assert len(shapes) == 3
    stage_shapes = sorted(tuple(len(stage.capabilities) for stage in shape.stages) for shape in shapes)
    assert stage_shapes == [(1, 1, 1), (1, 2), (3,)]  # linear, staged, parallel


def test_linear_shape_preserves_genome_order():
    shapes = shapes_for("cost", "research", "security")
    linear = next(shape for shape in shapes if len(shape.stages) == 3)
    assert [stage.capabilities[0] for stage in linear.stages] == [
        CapabilityId("cost"), CapabilityId("research"), CapabilityId("security"),
    ]


def test_staged_shape_puts_only_the_first_capability_alone():
    shapes = shapes_for("research", "cost", "security")
    staged = next(shape for shape in shapes if len(shape.stages) == 2)
    assert staged.stages[0].capabilities == (CapabilityId("research"),)
    assert staged.stages[1].capabilities == (CapabilityId("cost"), CapabilityId("security"))


def test_parallel_shape_puts_every_capability_in_one_stage():
    shapes = shapes_for("research", "cost", "security")
    parallel = next(shape for shape in shapes if len(shape.stages) == 1)
    assert parallel.stages[0].capabilities == (CapabilityId("research"), CapabilityId("cost"), CapabilityId("security"))


def test_four_capabilities_still_produce_exactly_three_distinct_shapes():
    shapes = shapes_for("research", "cost", "security", "architecture")
    assert len(shapes) == 3


# --- 4. deterministic output for identical input ------------------------------------------------------------------


def test_identical_input_produces_identical_output():
    first = shapes_for("research", "cost", "security")
    second = shapes_for("research", "cost", "security")
    assert first == second


def test_a_fresh_generator_instance_produces_the_same_output():
    genome = genome_with("research", "cost")
    assert RuleBasedCandidateGenerator().generate(genome) == RuleBasedCandidateGenerator().generate(genome)


# --- 5. structurally distinct candidates / 6. no duplicate candidates ----------------------------------------------


def test_no_two_generated_shapes_share_the_same_structure():
    for capabilities in [(), ("research",), ("research", "cost"), ("research", "cost", "security")]:
        shapes = shapes_for(*capabilities)
        keys = [(shape.stages, shape.verification) for shape in shapes]
        assert len(keys) == len(set(keys))


def test_a_repeated_capability_in_the_genome_does_not_duplicate_a_role():
    # required_capabilities=("research", "research", "cost") allocates research and cost, not research twice.
    shapes = shapes_for("research", "research", "cost")
    linear = next(shape for shape in shapes if len(shape.stages) == 2)
    assert [stage.capabilities for stage in linear.stages] == [(CapabilityId("research"),), (CapabilityId("cost"),)]


def test_repeated_capabilities_produce_the_same_shapes_as_the_deduplicated_list():
    assert shapes_for("research", "research", "cost") == shapes_for("research", "cost")


# --- 7. no capability outside TaskGenome.required_capabilities -----------------------------------------------------


def test_every_generated_capability_is_one_of_the_required_ones():
    required = {"research", "cost", "security"}
    for shape in shapes_for("research", "cost", "security"):
        for stage in shape.stages:
            for capability in stage.capabilities:
                assert str(capability) in required


def test_the_generator_never_introduces_a_capability_the_genome_did_not_require():
    # A generator with only "research" required can never mention "cost" anywhere in its output.
    for shape in shapes_for("research"):
        for stage in shape.stages:
            assert CapabilityId("cost") not in stage.capabilities


# --- rationale is non-empty and deterministic ------------------------------------------------------------------------


def test_every_shape_carries_a_non_empty_deterministic_rationale():
    shapes = shapes_for("research", "cost")
    for shape in shapes:
        assert shape.rationale
    assert [s.rationale for s in shapes] == [s.rationale for s in shapes_for("research", "cost")]
