"""The ``search_documents`` fixture: the one approved tool, its allowlist entry, a mission that may use it, and a scripted port (decisions.md D-203, D-205
ruling 3, D-207; V1.2 Step 4).

**This is the concrete fixture location and its configuration**, established here as D-205 ruling 3 required. A domain tool is configuration, not
runtime (invariant 10), so the entry lives in test support and not in ``src``:

- tool id ``docs/search_documents`` (provider ``docs``, tool ``search_documents``), capability ``research``, action ``read_documents``, read-only
  *by EIDOS's own declaration* (nothing a server says about itself is read);
- arguments: ``query``, a string of 1 to 256 characters, required; ``limit``, an integer from 1 to 10, optional; no defaults;
- **timeout** ``5.0`` seconds and **result-size bound** ``4096`` bytes (the UTF-8 size of the documents' ids and texts), both taken from this entry by
  admission and never from a request;
- **schema digest** ``SEARCH_INPUT_SCHEMA_DIGEST``: the SHA-256 of the canonical JSON of the input schema the reference server declares
  (``search_documents_corpus.INPUT_SCHEMA``). It pins that schema, so a server whose declared schema changes is refused when it is contacted;
  admission never reads it. A test keeps this literal equal to the digest computed from the schema.

The values are a test fixture, not production configuration. Nothing here does I/O.
"""

import re
import threading
from uuid import UUID

from eidos.agents import ToolDocument, ToolFailure, ToolFailureKind, ToolRequest, ToolResult
from eidos.runtime import ExecutionContext
from eidos.capabilities import RESEARCH, ToolArgumentKind, ToolArgumentSpec, ToolDescriptor, ToolRegistry
from eidos.contracts import (
    ActionId,
    AutonomyLevel,
    CapabilityId,
    ExecutionId,
    MissionId,
    MissionState,
    Plan,
    PlanId,
    ReliabilityContractId,
    TenantId,
)

from eidos_factories import make_mission_state, make_reliability_contract, make_task_genome
from eidos_mission_factories import make_mission_plan
from search_documents_corpus import DEFAULT_LIMIT, MAX_LIMIT, keyword_search

PROVIDER_ID = "docs"
TOOL_NAME = "search_documents"
TOOL_ID = f"{PROVIDER_ID}/{TOOL_NAME}"
READ_ACTION = ActionId("read_documents")
FIXTURE_TIMEOUT_SECONDS = 5.0
FIXTURE_MAX_RESULT_BYTES = 4096
SEARCH_INPUT_SCHEMA_DIGEST = "298b120661e86f97c4cb09438c7d5dd7f441314386b76d4b679cae6ccc9a8f9f"
GOAL = "Explain how mission replay and verification work"
EXPECTED_DOCUMENT_IDS = ("doc-replay", "doc-budgets", "doc-events")  # what the goal finds, best first, at the server's default limit


def search_descriptor(**overrides) -> ToolDescriptor:
    fields = dict(
        provider_id=PROVIDER_ID,
        tool_name=TOOL_NAME,
        capability=RESEARCH,
        action_id=READ_ACTION,
        read_only=True,
        arguments=(
            ToolArgumentSpec(name="query", kind=ToolArgumentKind.STRING, required=True, minimum=1, maximum=256),
            ToolArgumentSpec(name="limit", kind=ToolArgumentKind.INTEGER, required=False, minimum=1, maximum=MAX_LIMIT),
        ),
        timeout_seconds=FIXTURE_TIMEOUT_SECONDS,
        max_result_bytes=FIXTURE_MAX_RESULT_BYTES,
        input_schema_digest=SEARCH_INPUT_SCHEMA_DIGEST,
    ) | overrides
    return ToolDescriptor(**fields)


def search_registry(**overrides) -> ToolRegistry:
    return ToolRegistry(tools=(search_descriptor(**overrides),))


def make_tool_mission(
    *,
    seed: int = 1,
    max_tool_calls: int | None = 3,
    max_replans: int | None = None,
    min_independent_evidence: int = 2,
    allowed_actions: tuple[ActionId, ...] = (READ_ACTION,),
    autonomy_level: AutonomyLevel = AutonomyLevel.SAFE_READ_ONLY,
    goal: str = GOAL,
    capabilities: tuple[str, ...] = ("research", "cost"),
) -> MissionState:
    """A real, valid mission that may use ``search_documents`` unless a parameter takes that away. Nothing is supplied: the documents come from the tool."""
    base = seed * 1000
    tenant_id = TenantId(UUID(int=base + 1))
    contract = make_reliability_contract(
        tenant_id=tenant_id, contract_id=ReliabilityContractId(UUID(int=base + 4)),
        max_tool_calls=max_tool_calls, max_replans=max_replans, min_independent_evidence=min_independent_evidence,
    )
    genome = make_task_genome(
        contract=contract, goal=goal, required_capabilities=tuple(CapabilityId(name) for name in capabilities),
        allowed_actions=allowed_actions, autonomy_level=autonomy_level,
    )
    return make_mission_state(
        tenant_id=tenant_id, mission_id=MissionId(UUID(int=base + 2)), execution_id=ExecutionId(UUID(int=base + 3)),
        reliability_contract=contract, task_genome=genome, plans=(), active_plan_id=None,
    )


def attempt_context(state: MissionState, plan_number: int = 1) -> ExecutionContext:
    """The context of plan attempt ``plan_number`` of ``state``'s execution: the same execution, a distinct plan (so a distinct budget scope)."""
    return ExecutionContext(
        tenant_id=state.tenant_id, mission_id=state.mission_id, execution_id=state.execution_id, plan_id=PlanId(UUID(int=800_000 + plan_number)),
        plan_version=plan_number, task_genome=state.task_genome, reliability_contract=state.reliability_contract,
    )


def tool_mission_plan(state: MissionState, *, version: int = 1, parent: Plan | None = None, reason: str | None = None, plan_number: int | None = None) -> Plan:
    """gather (research, which searches) -> analyse (cost) -> check (verify)."""
    prefix = "" if version == 1 else f"v{version}_"
    spec = {f"{prefix}gather": "", f"{prefix}analyse": f"{prefix}gather", "check": f"{prefix}analyse"}
    return make_mission_plan(
        state, spec, verify=("check",), capability_of={f"{prefix}gather": "research", f"{prefix}analyse": "cost"},
        version=version, parent=parent, reason=reason, plan_number=plan_number,
    )


class ScriptedToolPort:
    """A ``ToolPort`` that runs the fixture's keyword search and records every request it is given, so a test can prove what was and was not invoked.

    ``answer`` overrides the search: a callable taking the request and returning a ``ToolResult`` or ``ToolFailure``, or a single value returned for
    every call. Thread-safe.
    """

    def __init__(self, answer=None):
        self._answer = answer
        self._lock = threading.Lock()
        self.requests: list[ToolRequest] = []

    def call(self, request: ToolRequest):
        with self._lock:
            self.requests.append(request)
        if self._answer is not None:
            return self._answer(request) if callable(self._answer) else self._answer
        arguments = {argument.name: argument.value for argument in request.arguments}
        found = keyword_search(arguments["query"], arguments.get("limit", DEFAULT_LIMIT))
        return ToolResult(documents=tuple(ToolDocument(document_id=document_id, content=text) for document_id, text in found))

    @property
    def calls(self) -> int:
        with self._lock:
            return len(self.requests)


class CountingPort:
    """A port that counts what reaches it, whichever kind it wraps: ``calls`` is what was handed to the port; ``starts`` is how many times a real server
    process was launched (always zero for the scripted kind)."""

    def __init__(self, inner):
        self.inner, self._lock, self.calls = inner, threading.Lock(), 0

    def call(self, request):
        with self._lock:
            self.calls += 1
        return self.inner.call(request)

    @property
    def starts(self) -> int:
        return getattr(self.inner, "process_starts", 0)

    def close(self) -> None:
        getattr(self.inner, "close", lambda: None)()


def failing_port(kind: ToolFailureKind, message: str = "scripted failure") -> ScriptedToolPort:
    return ScriptedToolPort(ToolFailure(kind=kind, message=message))


_RENDERED_REFERENCE = re.compile(r"\[\[([^\[\]\n]+)\]\] \(")


def cite_every_document(request):
    """A scripted model that cites every reference the prompt shows, so its answer is supported by exactly what the agent read."""
    from eidos.agents import MeasuredFacts, ModelResponse

    refs = _RENDERED_REFERENCE.findall(request.prompt)
    heading = "Findings" if "Documents:" in request.prompt else "Analysis"
    return ModelResponse(text=f"{heading} " + " ".join(f"[[{ref}]]" for ref in refs) + ".", measured=MeasuredFacts(prompt_tokens=100, output_tokens=50, elapsed_seconds=0.5))
