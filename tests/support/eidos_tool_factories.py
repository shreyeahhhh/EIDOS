"""Test-support fixtures for the tool allowlist and tool admission (decisions.md D-203; V1.2 Step 2).

The ``search_documents`` entry here is a **test instance only**, in test support and not in ``src``: a domain tool is configuration, and the
runtime is domain-agnostic (invariant 10). Its argument bounds, its timeout (5.0 s), its result-size bound (4,096 bytes) and its schema digest
(a fixed placeholder, not any server's real schema) are test values, not decisions and not production configuration (D-205 ruling 3). Step 4
establishes the concrete production and test fixture location and documents the timeout, the result-size bound and how the schema digest is
treated. Nothing here does I/O.
"""

from uuid import UUID

from eidos.capabilities import RESEARCH, ToolArgumentKind, ToolArgumentSpec, ToolDescriptor, ToolRegistry
from eidos.contracts import ActionId, AutonomyLevel, ExecutionId, PlanId
from eidos.policy import ToolInvocationRecord, admit_tool_call, args_digest

SEARCH_TOOL_ID = "docs/search_documents"
READ_ACTION = ActionId("read_documents")
DEFAULT_ARGUMENTS = {"query": "evidence"}
SCHEMA_DIGEST = "ab" * 32


def make_execution_id(number: int = 1) -> ExecutionId:
    return ExecutionId(UUID(int=number))


def make_attempt_plan_id(number: int = 1) -> PlanId:
    return PlanId(UUID(int=700_000 + number))


def query_spec(**overrides) -> ToolArgumentSpec:
    fields = dict(name="query", kind=ToolArgumentKind.STRING, required=True, minimum=1, maximum=256) | overrides
    return ToolArgumentSpec(**fields)


def limit_spec(**overrides) -> ToolArgumentSpec:
    fields = dict(name="limit", kind=ToolArgumentKind.INTEGER, required=False, minimum=1, maximum=10) | overrides
    return ToolArgumentSpec(**fields)


def make_search_descriptor(**overrides) -> ToolDescriptor:
    fields = dict(
        provider_id="docs", tool_name="search_documents", capability=RESEARCH, action_id=READ_ACTION, read_only=True,
        arguments=(query_spec(), limit_spec()), timeout_seconds=5.0, max_result_bytes=4096, input_schema_digest=SCHEMA_DIGEST,
    ) | overrides
    return ToolDescriptor(**fields)


def make_tool_registry(*tools: ToolDescriptor) -> ToolRegistry:
    return ToolRegistry(tools=tools or (make_search_descriptor(),))


def invocation(
    *, execution: int = 1, plan: int = 1, tool_id: str = SEARCH_TOOL_ID, arguments=None, stored: bool = True,
) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        execution_id=make_execution_id(execution), plan_id=make_attempt_plan_id(plan), tool_id=tool_id,
        args_digest=args_digest(DEFAULT_ARGUMENTS if arguments is None else arguments), result_stored=stored,
    )


def admit(**overrides):
    """One admission with every input a test does not care about supplied by a valid default."""
    fields = dict(
        registry=make_tool_registry(), tool_id=SEARCH_TOOL_ID, arguments=dict(DEFAULT_ARGUMENTS),
        execution_id=make_execution_id(1), plan_id=make_attempt_plan_id(1), allowed_actions=(READ_ACTION,),
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY, max_tool_calls=3, prior_invocations=(),
    ) | overrides
    return admit_tool_call(**fields)
