"""``agent_task_status_of`` (D-166: total over all nine wire states) and ``text_artifact_of`` (D-153: content and its
citations, never guessed at when nothing is usable)."""

from eidos.a2a.convert import agent_task_status_of, text_artifact_of
from eidos.a2a.wire import Artifact, Part, TaskStateWire
from eidos.contracts import AgentTaskStatus


def test_agent_task_status_of_is_total_and_a_name_lookup_for_every_wire_state():
    for wire_state in TaskStateWire:
        status = agent_task_status_of(wire_state)
        assert status.name == wire_state.name  # a lookup, not a hand-written table that could diverge
        assert isinstance(status, AgentTaskStatus)


def test_text_artifact_of_finds_the_first_usable_text_part():
    artifacts = (
        Artifact(artifact_id="a1", parts=(Part(url="https://example.com/x.png"),)),  # not text: skipped
        Artifact(artifact_id="a2", parts=(Part(text="Findings: [[doc:1]] and [[doc:2]] support this."),)),
    )
    converted = text_artifact_of(artifacts)
    assert converted is not None
    assert converted.content == "Findings: [[doc:1]] and [[doc:2]] support this."
    assert converted.content_type == "text/markdown"
    assert converted.source_refs == ("doc:1", "doc:2")


def test_text_artifact_of_honours_a_supported_declared_media_type():
    artifacts = (Artifact(artifact_id="a1", parts=(Part(text="plain text", media_type="text/plain"),)),)
    converted = text_artifact_of(artifacts)
    assert converted.content_type == "text/plain"


def test_text_artifact_of_skips_a_part_with_an_unsupported_media_type():
    artifacts = (
        Artifact(artifact_id="a1", parts=(Part(text='{"a": 1}', media_type="application/json"),)),
        Artifact(artifact_id="a2", parts=(Part(text="usable markdown"),)),
    )
    converted = text_artifact_of(artifacts)
    assert converted.content == "usable markdown"  # the unsupported part was skipped, not used


def test_text_artifact_of_returns_none_when_nothing_is_usable():
    assert text_artifact_of(()) is None
    assert text_artifact_of((Artifact(artifact_id="a1", parts=(Part(url="https://example.com/x.png"),)),)) is None
    assert text_artifact_of((Artifact(artifact_id="a1", parts=(Part(text="   "),)),)) is None  # blank text is not usable


def test_text_artifact_of_a_part_with_no_citations_has_an_empty_source_refs():
    converted = text_artifact_of((Artifact(artifact_id="a1", parts=(Part(text="no citations here"),)),))
    assert converted.source_refs == ()
