"""A mission that reads a web page, end to end through the real service on a scripted network (decisions.md D-238; invariants 12, 14, 16).

What is held: the page named in the goal is fetched through the existing gate and becomes evidence the answer cites and the verifier checks; a mission only does it if the server lists the action and the
mission names it and has a budget; without either, nothing is fetched and the mission says why it could not be researched; and a page that cannot be fetched is a failed run, never an invented answer.
"""

import pytest

from eidos.contracts import AutonomyLevel, MissionStatus, RiskLevel
from eidos.service import InvalidSpec, ReliabilitySpec, RunStatus, ToolProvision
from eidos.state import CitationKind
from eidos.tools import WEB_FETCH_ACTION, WEB_FETCH_TOOL_ID, WebFetchTool, web_fetch_registry
from eidos.tools.safe_https import FetchError, RawResponse

from eidos_service_fixture import TENANT_A, make_rig, make_spec

GOAL = "Review https://example.com/portfolio for faults"


class Network:
    def __init__(self, answer):
        self.answer, self.requests = answer, []

    def __call__(self, host, address, target, deadline, max_bytes):
        self.requests.append((host, address, target))
        if isinstance(self.answer, FetchError):
            raise self.answer
        return self.answer


def page(text: str = "<html><head><title>Portfolio</title></head><body><h1>Hello</h1><p>Projects and contact.</p></body></html>") -> RawResponse:
    return RawResponse(200, {"content-type": "text/html; charset=utf-8"}, text.encode("utf-8"))


def provision(network: Network) -> ToolProvision:
    return ToolProvision(registry=web_fetch_registry(), port=WebFetchTool(resolver=lambda host, deadline: ["93.184.216.34"], opener=network), tool_id=WEB_FETCH_TOOL_ID)


def web_spec(**overrides):
    fields = dict(
        goal=GOAL, allowed_actions=(WEB_FETCH_ACTION,), supplied_documents=(),
        reliability=ReliabilitySpec(min_quality=0.0, max_risk_level=RiskLevel.MEDIUM, min_independent_evidence=1, max_tool_calls=3),
    ) | overrides
    return make_spec(**fields)


def run(rig, spec):
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, spec)[0].mission_id
    rig.run_to_the_end(context, mission_id)
    return context, mission_id


def test_the_page_named_in_the_goal_is_fetched_cited_verified_and_kept_as_evidence():
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    context, mission_id = run(rig, web_spec())

    assert network.requests == [("example.com", "93.184.216.34", "/portfolio")]  # exactly the page the goal named, at the address that was checked
    summary = rig.service.get_mission(context, mission_id)
    assert summary.run_status is RunStatus.FINISHED and summary.mission_status is MissionStatus.COMPLETED
    result = rig.service.result(context, mission_id)
    assert result.verified is True
    view = rig.service.evidence(context, mission_id)
    refs = [str(item.ref) for item in view.evidence]
    assert len(refs) == 1 and refs[0].startswith(f"tool:{WEB_FETCH_TOOL_ID}:") and refs[0].split(":")[3].startswith("example.com-")
    assert {trace.kind for trace in view.audit.traces} == {CitationKind.NOT_EVIDENCE}  # the audit's meaning is unchanged: a fetched page is not knowledge-base evidence
    assert view.audit.cited == ()
    evidence = view.evidence[0]
    assert evidence.content.startswith("URL: https://example.com/portfolio\n\n") and "Hello" in evidence.content and "Projects and contact." in evidence.content
    assert any(refs[0] in str(artifact.source_refs) or refs[0] == str(artifact.ref) for artifact in result.artifacts)  # the answer cites the page (invariant 16)


def test_the_call_is_recorded_on_the_node_that_made_it():
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(Network(page())))
    context, mission_id = run(rig, web_spec())
    records = rig.storage.read(TENANT_A, mission_id)
    recorded = [record.model_dump_json() for record in records if WEB_FETCH_TOOL_ID in record.model_dump_json()]
    assert recorded and any('"result"' in text or "result" in text for text in recorded)


def test_a_mission_that_does_not_name_the_action_fetches_nothing_and_says_there_was_nothing_to_research():
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    context, mission_id = run(rig, web_spec(allowed_actions=()))
    assert network.requests == []
    summary = rig.service.get_mission(context, mission_id)
    assert summary.mission_status is not MissionStatus.COMPLETED  # no evidence, so no answer: it is not made up


def test_a_mission_that_gave_nothing_to_read_and_never_asked_for_the_web_is_told_exactly_that_and_no_tool_is_tried():
    """The owner's own mission (D-247): a general question, no documents, web reading not ticked. It used to end "...and the tool call was denied (budget_unresolved)", a true refusal about a
    budget the mission never needed. It now says only what is so, and no tool call is made, so none is recorded."""
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    unticked = ReliabilitySpec(min_quality=0.0, max_risk_level=RiskLevel.MEDIUM, min_independent_evidence=1)  # no tool budget, as the form sends when the box is unticked
    context, mission_id = run(rig, web_spec(goal="Which is the best time for a beginner to buy and sell stocks?", allowed_actions=(), reliability=unticked))
    assert network.requests == []
    failure = rig.service.result(context, mission_id).failure
    assert failure is not None
    assert "no documents were supplied, so there is nothing to research" in failure.reason
    assert "budget" not in failure.reason and "denied" not in failure.reason and "tool" not in failure.reason
    recorded = " ".join(record.model_dump_json() for record in rig.storage.read(TENANT_A, mission_id))
    assert "budget_unresolved" not in recorded and WEB_FETCH_TOOL_ID not in recorded  # no call was made, so no refusal was recorded either


def test_a_mission_that_names_the_action_but_has_no_budget_is_still_refused_by_the_gate_and_the_refusal_is_recorded():
    """The gate is unchanged: a mission that did ask for the tool still gets every check, and a refusal is still said in its own words."""
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    no_budget = ReliabilitySpec(min_quality=0.0, max_risk_level=RiskLevel.MEDIUM, min_independent_evidence=1)
    context, mission_id = run(rig, web_spec(reliability=no_budget))
    assert network.requests == []
    failure = rig.service.result(context, mission_id).failure
    assert failure is not None and "budget_unresolved" in failure.reason


def test_a_mission_with_no_tool_budget_fetches_nothing():
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    reliability = ReliabilitySpec(min_quality=0.0, max_risk_level=RiskLevel.MEDIUM, min_independent_evidence=1)  # max_tool_calls unset
    context, mission_id = run(rig, web_spec(reliability=reliability))
    assert network.requests == []
    assert rig.service.get_mission(context, mission_id).mission_status is not MissionStatus.COMPLETED


def test_a_mission_below_the_read_only_autonomy_level_fetches_nothing():
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    context, mission_id = run(rig, web_spec(autonomy_level=AutonomyLevel.RECOMMEND_ONLY))
    assert network.requests == []


def test_a_server_that_does_not_list_the_action_refuses_a_mission_that_asks_for_it():
    rig = make_rig()  # the default rig's server lists only read_documents, and wires no tool
    with pytest.raises(InvalidSpec) as caught:
        rig.service.create_mission(rig.context("alice"), web_spec())
    assert any(WEB_FETCH_ACTION in detail["message"] for detail in caught.value.details)


def test_a_page_that_cannot_be_fetched_is_a_failed_run_not_an_answer():
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(Network(RawResponse(404, {}, b""))))
    context, mission_id = run(rig, web_spec())
    summary = rig.service.get_mission(context, mission_id)
    assert summary.mission_status is not MissionStatus.COMPLETED
    result = rig.service.result(context, mission_id)
    assert result.verified is not True and rig.service.evidence(context, mission_id).evidence == ()


def test_an_address_that_would_reach_this_network_is_never_requested_and_the_mission_cannot_complete():
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    for goal in ("Read https://169.254.169.254/latest/meta-data/ please", "Read https://localhost:8000/v1/healthz", "Read http://example.com/insecure"):
        context, mission_id = run(rig, web_spec(goal=goal))
        assert rig.service.get_mission(context, mission_id).mission_status is not MissionStatus.COMPLETED
    assert network.requests == []


def test_the_same_page_named_twice_in_a_goal_is_fetched_once():
    network = Network(page())
    rig = make_rig(allowed_actions=frozenset({WEB_FETCH_ACTION}), tools=provision(network))
    run(rig, web_spec(goal="Compare https://example.com/portfolio with https://example.com/portfolio again"))
    assert len(network.requests) == 1
