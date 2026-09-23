"""``ExperienceStore``/``JsonlExperienceStore`` (decisions.md D-198; V1.0 Step 3).

``_experience(**overrides)`` mirrors ``test_memory_relevance.py``'s own local factory — a fresh, minimal, valid
``ExecutionExperience`` per test, overriding only the field(s) under test. Every filesystem test uses pytest's
own ``tmp_path`` (a fresh, unique temporary directory per test) — nothing here touches a real project path.
"""

from uuid import UUID

import pytest

from eidos.contracts import CapabilityId, ExecutionId, MissionId, MissionStatus, StrategyId, TenantId
from eidos.memory import (
    ExecutionExperience,
    ExperienceLoadRejection,
    ExperienceLoadRejectionCode,
    JsonlExperienceStore,
    dump_experience_jsonl,
    load_experience_jsonl,
)
from eidos.planning import VerificationPosture
from eidos_state_factories import T0

_TENANT, _MISSION = TenantId(UUID(int=1)), MissionId(UUID(int=2))


def _experience(**overrides) -> ExecutionExperience:
    from eidos.contracts import AutonomyLevel, RiskLevel

    fields = dict(
        tenant_id=_TENANT, mission_id=_MISSION, execution_id=ExecutionId(UUID(int=3)),
        strategy_id=StrategyId(UUID(int=4)), recorded_at=T0,
        strategy_stage_shapes=((CapabilityId("research"),),), strategy_verification=VerificationPosture.FINAL,
        task_required_capabilities=(CapabilityId("research"),), task_risk_level=RiskLevel.MEDIUM,
        task_autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
        mission_status=MissionStatus.COMPLETED, verified=True,
        execution_time_used_ms=0, mission_wall_clock_ms=0, model_call_count=0, tokens_used=0,
        responses_missing_token_counts=0, agent_calls_used=0, tool_calls_used=0, retries_used=0, replans_used=0,
    )
    fields.update(overrides)
    return ExecutionExperience(**fields)


# --- opening: empty/missing store ---------------------------------------------------------------------------------


def test_opening_a_missing_file_is_an_empty_history(tmp_path):
    store = JsonlExperienceStore.open(tmp_path / "does_not_exist.jsonl")
    assert isinstance(store, JsonlExperienceStore)
    assert store.all() == ()


def test_opening_an_existing_empty_file_is_an_empty_history(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    store = JsonlExperienceStore.open(path)
    assert isinstance(store, JsonlExperienceStore)
    assert store.all() == ()


# --- append + all() --------------------------------------------------------------------------------------------


def test_append_then_all_returns_the_appended_record(tmp_path):
    store = JsonlExperienceStore.open(tmp_path / "store.jsonl")
    assert isinstance(store, JsonlExperienceStore)
    experience = _experience()
    store.append(experience)
    assert store.all() == (experience,)


def test_append_immediately_updates_the_cache_without_rereading(tmp_path):
    path = tmp_path / "store.jsonl"
    store = JsonlExperienceStore.open(path)
    assert isinstance(store, JsonlExperienceStore)
    experience = _experience()
    store.append(experience)
    # Deleting the file after append proves all() reads the in-memory cache, never the filesystem again.
    path.unlink()
    assert store.all() == (experience,)


def test_multiple_appends_preserve_insertion_order(tmp_path):
    store = JsonlExperienceStore.open(tmp_path / "store.jsonl")
    assert isinstance(store, JsonlExperienceStore)
    first = _experience(execution_id=ExecutionId(UUID(int=10)))
    second = _experience(execution_id=ExecutionId(UUID(int=11)))
    third = _experience(execution_id=ExecutionId(UUID(int=12)))
    store.append(first)
    store.append(second)
    store.append(third)
    assert store.all() == (first, second, third)


def test_duplicate_experiences_are_both_preserved(tmp_path):
    # Nothing here deduplicates — two structurally identical records (a legitimate outcome: the same strategy
    # shape genuinely run twice with the same result) are both kept, in order.
    store = JsonlExperienceStore.open(tmp_path / "store.jsonl")
    assert isinstance(store, JsonlExperienceStore)
    experience = _experience()
    store.append(experience)
    store.append(experience)
    assert store.all() == (experience, experience)


# --- persistence across reopening -------------------------------------------------------------------------------


def test_persistence_across_reopening(tmp_path):
    path = tmp_path / "store.jsonl"
    first_session = JsonlExperienceStore.open(path)
    assert isinstance(first_session, JsonlExperienceStore)
    a, b = _experience(execution_id=ExecutionId(UUID(int=20))), _experience(execution_id=ExecutionId(UUID(int=21)))
    first_session.append(a)
    first_session.append(b)

    second_session = JsonlExperienceStore.open(path)
    assert isinstance(second_session, JsonlExperienceStore)
    assert second_session.all() == (a, b)


def test_load_append_reopen_produce_the_same_ordered_sequence(tmp_path):
    path = tmp_path / "store.jsonl"
    a, b, c = (
        _experience(execution_id=ExecutionId(UUID(int=30))),
        _experience(execution_id=ExecutionId(UUID(int=31))),
        _experience(execution_id=ExecutionId(UUID(int=32))),
    )

    session = JsonlExperienceStore.open(path)  # load
    assert isinstance(session, JsonlExperienceStore)
    assert session.all() == ()

    session.append(a)  # append(x) -> all()
    assert session.all() == (a,)
    session.append(b)
    session.append(c)
    assert session.all() == (a, b, c)

    reopened = JsonlExperienceStore.open(path)  # reopen -> all()
    assert isinstance(reopened, JsonlExperienceStore)
    assert reopened.all() == (a, b, c)


# --- exact round-trip / serialization format ----------------------------------------------------------------------


def test_exact_execution_experience_round_trip_through_the_store(tmp_path):
    experience = _experience(
        strategy_stage_shapes=((CapabilityId("research"), CapabilityId("cost")), (CapabilityId("security"),)),
        strategy_verification=VerificationPosture.FINAL,
        execution_time_used_ms=1234, mission_wall_clock_ms=-7, tokens_used=999,
    )
    path = tmp_path / "store.jsonl"
    JsonlExperienceStore.open(path).append(experience)  # type: ignore[union-attr]
    reopened = JsonlExperienceStore.open(path)
    assert isinstance(reopened, JsonlExperienceStore)
    (round_tripped,) = reopened.all()
    assert round_tripped == experience
    assert round_tripped.model_dump_json() == experience.model_dump_json()


def test_one_json_object_per_line(tmp_path):
    path = tmp_path / "store.jsonl"
    store = JsonlExperienceStore.open(path)
    assert isinstance(store, JsonlExperienceStore)
    store.append(_experience(execution_id=ExecutionId(UUID(int=40))))
    store.append(_experience(execution_id=ExecutionId(UUID(int=41))))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        assert ExecutionExperience.model_validate_json(line) is not None  # each line alone is a complete, valid record


def test_dump_experience_jsonl_matches_what_the_store_writes(tmp_path):
    a, b = _experience(execution_id=ExecutionId(UUID(int=50))), _experience(execution_id=ExecutionId(UUID(int=51)))
    path = tmp_path / "store.jsonl"
    store = JsonlExperienceStore.open(path)
    assert isinstance(store, JsonlExperienceStore)
    store.append(a)
    store.append(b)
    assert path.read_text(encoding="utf-8") == dump_experience_jsonl((a, b))


def test_dump_of_empty_history_is_the_empty_string():
    assert dump_experience_jsonl(()) == ""


def test_serialization_is_deterministic_across_calls():
    experience = _experience()
    assert experience.model_dump_json() == experience.model_dump_json()
    assert dump_experience_jsonl((experience,)) == dump_experience_jsonl((experience,))


# --- malformed records ---------------------------------------------------------------------------------------


def test_a_malformed_line_is_a_typed_rejection_naming_its_line_number(tmp_path):
    path = tmp_path / "store.jsonl"
    good = _experience()
    path.write_text(good.model_dump_json() + "\n" + "not valid json at all {{{\n", encoding="utf-8")
    result = JsonlExperienceStore.open(path)
    assert isinstance(result, ExperienceLoadRejection)
    assert result.code is ExperienceLoadRejectionCode.MALFORMED_LINE
    assert result.line == 2


def test_a_malformed_line_never_silently_drops_the_good_records_around_it(tmp_path):
    # The whole load fails explicitly rather than returning a filtered, incomplete history — matching
    # eidos.state.replay.load_jsonl's own established convention exactly.
    path = tmp_path / "store.jsonl"
    path.write_text('{"not": "a valid ExecutionExperience"}\n', encoding="utf-8")
    result = JsonlExperienceStore.open(path)
    assert isinstance(result, ExperienceLoadRejection)
    # No JsonlExperienceStore is ever constructed from a rejected load — there is no partial `.all()` to call.
    assert not hasattr(result, "all")


def test_load_experience_jsonl_rejects_a_blank_line_in_the_middle():
    good = _experience().model_dump_json()
    text = f"{good}\n\n{good}\n"
    result = load_experience_jsonl(text)
    assert isinstance(result, ExperienceLoadRejection)
    assert result.line == 2


# --- returned history cannot mutate store state -----------------------------------------------------------------


def test_the_returned_history_cannot_mutate_the_store(tmp_path):
    store = JsonlExperienceStore.open(tmp_path / "store.jsonl")
    assert isinstance(store, JsonlExperienceStore)
    store.append(_experience())
    history = store.all()
    assert isinstance(history, tuple)  # a tuple is itself immutable: nothing a caller does to it can reach the store
    with pytest.raises(AttributeError):
        history.append(_experience())  # type: ignore[attr-defined]


# --- filesystem failure behavior --------------------------------------------------------------------------------


def test_appending_when_the_parent_directory_is_gone_raises_rather_than_swallowing(tmp_path):
    path = tmp_path / "missing_subdir" / "store.jsonl"
    store = JsonlExperienceStore.open(path)  # the file itself does not exist yet: an ordinary empty-history open
    assert isinstance(store, JsonlExperienceStore)
    with pytest.raises(OSError):
        store.append(_experience())


def test_opening_a_directory_as_though_it_were_the_store_file_raises(tmp_path):
    directory = tmp_path / "a_directory"
    directory.mkdir()
    with pytest.raises(OSError):
        JsonlExperienceStore.open(directory)


# --- architecture -----------------------------------------------------------------------------------------------


def test_jsonl_experience_store_satisfies_the_experience_store_shape(tmp_path):
    # eidos.recording.ports.Clock/IdSource are plain (non-runtime-checkable) Protocols in this codebase; mirrored
    # here rather than adding @runtime_checkable — checked by callable shape, matching that established precedent.
    store = JsonlExperienceStore.open(tmp_path / "store.jsonl")
    assert isinstance(store, JsonlExperienceStore)
    assert callable(store.append) and callable(store.all)
