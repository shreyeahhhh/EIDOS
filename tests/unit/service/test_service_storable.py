"""Text the durable store cannot keep (decisions.md D-230, D-234; V1.4-C acceptance audit).

PostgreSQL refuses a NUL in text and in jsonb (a lone surrogate, which it would refuse too, cannot exist here: every EIDOS model's strict ``str`` refuses it). Found by the audit, over a real PostgreSQL: a NUL in a request's goal or a supplied document was a 500, and a model that
answered with a NUL made the run end ``error`` with only a short prefix of its events stored, although the mission had finished in memory. What is held now: a request holding such text is refused with a 422
naming the field; a model's answer is made storable at the port, before anything is recorded, so the runtime sees, records and cites the same text the store holds; and text that is merely unusual
(U+FFFF, emoji, right-to-left marks, combining marks, control characters other than NUL) is left exactly as it was.

The in-memory storage has no such limit, so a store that refuses a NUL like PostgreSQL does is used here to keep the regression in the default suite. The same is proved on a real PostgreSQL with ``-m postgres``.
"""

import pytest

from eidos.agents import MeasuredFacts, ModelFailure, ModelFailureKind, ModelRequest, ModelResponse
from eidos.contracts import MissionStatus
from eidos.service import InMemoryStorage, InvalidSpec, RunStatus, StorageError, SuppliedDocument
from eidos.service.composition import StorableModel, storable
from eidos.service.spec import UNSTORABLE

from eidos_agents_factories import ScriptedModel
from eidos_search_fixture import cite_every_document
from eidos_service_fixture import TENANT_A, make_rig, make_spec

NUL, REPLACEMENT = chr(0), chr(0xFFFD)
UNUSUAL = "emoji " + chr(0x1F600) + " noncharacter " + chr(0xFFFF) + " private " + chr(0xE000) + " rtl " + chr(0x202E) + "abc combining e" + chr(0x301) + " tab\tline\nbreak\r\n bell" + chr(7) + " " + chr(0x7F)


class Refusing(InMemoryStorage):
    """An in-memory storage that refuses what PostgreSQL refuses: a NUL anywhere in an artifact, in an event's JSON or in a mission's text."""

    def commit(self, *, artifacts, events, **kwargs):
        if any(NUL in write.artifact.content or NUL in str(write.artifact.ref) or any(NUL in str(r) for r in write.artifact.source_refs) for write in artifacts):
            raise StorageError("DataError")
        if any(NUL in record.model_dump_json() or "\\u0000" in record.model_dump_json() for record in events):
            raise StorageError("DataError")
        return super().commit(artifacts=artifacts, events=events, **kwargs)


def request(**overrides):
    from eidos.agents import GenerationParameters, ModelSettings

    settings = ModelSettings(model="m", parameters=GenerationParameters(temperature=0.0, seed=1, max_output_tokens=64), timeout_seconds=5.0)
    return ModelRequest(settings=settings, prompt="p", **overrides)


# --- what counts as unstorable, and what does not ----------------------------------------------------------------------------------------------


def test_storable_replaces_a_nul_and_nothing_else():
    assert storable("a" + NUL + "b" + NUL + "c") == "a" + REPLACEMENT + "b" + REPLACEMENT + "c"
    assert storable(UNUSUAL) == UNUSUAL and storable("") == "" and storable("plain") == "plain"
    assert storable(storable(NUL)) == REPLACEMENT  # idempotent
    assert not UNSTORABLE.search(UNUSUAL) and UNSTORABLE.search(NUL) and not UNSTORABLE.search(chr(1)) and not UNSTORABLE.search(chr(0xFFFF))


# --- the door: a request that holds such text is a 422 naming the field -----------------------------------------------------------------------------


def problems(**spec):
    rig = make_rig()
    with pytest.raises(InvalidSpec) as raised:
        rig.service.create_mission(rig.context("alice"), make_spec(**spec))
    return {item["field"]: item["message"] for item in raised.value.details}


@pytest.mark.parametrize("bad", [NUL, "a" + NUL + "b"], ids=["nul", "embedded-nul"])
def test_a_goal_an_information_dependency_or_a_document_holding_unstorable_text_is_refused_field_by_field(bad):
    document = SuppliedDocument(ref="d1", content_type="text/plain", content="x" + bad + "y")
    found = problems(goal="g" + bad, information_dependencies=("ok", "dep" + bad), supplied_documents=(document,))
    assert {"goal", "information_dependencies[1]", "supplied_documents[0].content"} <= set(found)
    assert "information_dependencies[0]" not in found and all("cannot be stored" in found[name] for name in ("goal", "information_dependencies[1]", "supplied_documents[0].content"))


def test_unusual_but_storable_text_is_accepted_untouched_and_read_back_exactly():
    document = SuppliedDocument(ref="d1", content_type="text/plain", content=UNUSUAL)
    rig = make_rig()
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, make_spec(goal=UNUSUAL, information_dependencies=(UNUSUAL,), supplied_documents=(document,)))[0].mission_id
    record = rig.storage.get(TENANT_A, mission_id)
    assert record.spec.goal == UNUSUAL and record.spec.information_dependencies == (UNUSUAL,)
    assert rig.storage.artifacts_for(TENANT_A).supplied(record.execution_id)[0].content == UNUSUAL


# --- the model port: what the runtime is handed is what the store can hold ----------------------------------------------------------------------


def test_the_model_port_replaces_unstorable_text_keeps_the_measured_facts_and_returns_clean_answers_untouched():
    facts = MeasuredFacts(prompt_tokens=3, output_tokens=4, elapsed_seconds=0.5)
    dirty = StorableModel(ScriptedModel(lambda r: ModelResponse(text="a" + NUL + "b", measured=facts)))
    answer = dirty.complete(request())
    assert answer.text == "a" + REPLACEMENT + "b" and answer.measured == facts
    clean_response = ModelResponse(text=UNUSUAL, measured=facts)
    assert StorableModel(ScriptedModel(lambda r: clean_response)).complete(request()) is clean_response  # the very object: nothing was rebuilt
    failure = StorableModel(ScriptedModel(lambda r: ModelFailure(kind=ModelFailureKind.UNAVAILABLE, message="down " + NUL + " and " + NUL))).complete(request())
    assert (failure.kind, failure.message) == (ModelFailureKind.UNAVAILABLE, "down " + REPLACEMENT + " and " + REPLACEMENT)
    untouched = ModelFailure(kind=ModelFailureKind.TIMEOUT, message="slow")
    assert StorableModel(ScriptedModel(lambda r: untouched)).complete(request()) is untouched


def nul_answer(request):
    reply = cite_every_document(request)
    return ModelResponse(text=reply.text + " tail" + NUL + " more", measured=reply.measured)


def test_a_model_that_answers_with_a_nul_no_longer_stops_the_run_being_stored():
    storage = Refusing()
    rig = make_rig(storage=storage, respond=nul_answer)
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, make_spec())[0].mission_id
    summary = rig.run_to_the_end(context, mission_id)
    assert (summary.run_status, summary.mission_status, summary.verified, summary.run_status_reason) == (RunStatus.FINISHED, MissionStatus.COMPLETED, True, None)
    records = storage.read(TENANT_A, mission_id)
    assert len(records) == summary.last_sequence > 6 and not any(NUL in r.model_dump_json() or "\\u0000" in r.model_dump_json() for r in records)
    result = rig.service.result(context, mission_id)
    assert result.artifacts and all(NUL not in a.content and REPLACEMENT in a.content for a in result.artifacts)  # the same text was recorded, cited and stored


def test_the_regression_is_real_the_refusing_store_would_have_ended_the_run_in_error_without_the_port():
    """Without ``StorableModel`` the same run ends in error with a short prefix: proof the store above is as strict as PostgreSQL and that the port is what makes the difference."""
    storage = Refusing()
    rig = make_rig(storage=storage, respond=nul_answer)
    import eidos.service.composition as composition_module

    original = composition_module.StorableModel
    composition_module.StorableModel = lambda inner: inner  # the port taken away
    try:
        context = rig.context("alice")
        mission_id = rig.service.create_mission(context, make_spec())[0].mission_id
        summary = rig.run_to_the_end(context, mission_id)
    finally:
        composition_module.StorableModel = original
    assert summary.run_status is RunStatus.ERROR and summary.run_status_reason.startswith("persistence:") and summary.last_sequence < 10


def test_a_citation_the_model_invents_with_a_nul_in_it_is_stored_too():
    """The bracket syntax of a citation takes any characters, so the text of a made-up reference reaches the events (as an unresolved citation). It passes through the same port."""

    def invents(request):
        reply = cite_every_document(request)
        return ModelResponse(text=reply.text + " [[made" + NUL + "up]]", measured=reply.measured)

    storage = Refusing()
    rig = make_rig(storage=storage, respond=invents)
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, make_spec())[0].mission_id
    summary = rig.run_to_the_end(context, mission_id)
    assert summary.run_status is RunStatus.FINISHED
    text = "".join(r.model_dump_json() for r in storage.read(TENANT_A, mission_id))
    assert NUL not in text and "\\u0000" not in text
