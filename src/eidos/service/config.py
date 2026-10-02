"""The service's configuration (decisions.md D-232, D-234; ``docs/13`` section 9).

**Every number here is PROVISIONAL: a round starting value, not tuned, not measured and not derived from any run** (the D-046 precedent: a provisional bound is never presented
as a tuned one). Changing one is configuration and not an architecture change.

**The API safety ceilings are not EIDOS budget enforcement.** They bound what the service accepts. A request over a ceiling is rejected, never clamped. EIDOS still records the six
contract budgets and enforces none of them beyond what D-205 and ``max_replans`` already do (D-127, D-156), and the admission guard the service supplies is a trivial always-admit
guard that enforces no budget.
"""

from dataclasses import dataclass, field
from uuid import UUID, uuid5

from eidos.agents import ModelSettings
from eidos.contracts import AgentId
from eidos.validation import SystemLimits

_NAMESPACE = UUID("6f3c2a7e-0d64-4a3e-9d0f-5b1d0a7f2c11")  # a fixed namespace: the agent identifiers below are stable across restarts, so a recorded log names the same agents forever


def _agent_id(name: str) -> AgentId:
    return AgentId(uuid5(_NAMESPACE, name))


RESEARCH_AGENT_ID = _agent_id("eidos.agents.research")
ANALYSIS_AGENT_ID = _agent_id("eidos.agents.analysis")


@dataclass(frozen=True, slots=True, kw_only=True)
class ApiCeilings:
    """PROVISIONAL ceilings on what one request may carry (``docs/13`` section 9)."""

    max_request_body_bytes: int = 262_144
    max_goal_chars: int = 2_000
    max_information_dependencies: int = 16
    max_allowed_actions: int = 16
    max_autonomy_level: int = 1  # SAFE_READ_ONLY
    max_supplied_documents: int = 8
    max_document_bytes: int = 32_768
    max_total_document_bytes: int = 131_072
    events_page_default: int = 100
    events_page_max: int = 500


@dataclass(frozen=True, slots=True, kw_only=True)
class RunnerConfig:
    """PROVISIONAL bounds on the in-process runner and on the write-through flush."""

    worker_pool_size: int = 2
    max_queued_runs: int = 8
    max_active_runs_per_tenant: int = 1  # queued plus running
    flush_attempts: int = 3
    flush_backoff_seconds: float = 0.5


def provisional_system_limits() -> SystemLimits:
    """A PROVISIONAL ``SystemLimits`` (D-103: EIDOS has no defaults, so the service must supply one; D-046: the values are Open)."""
    return SystemLimits(
        max_nodes=32, max_depth=16, max_parallel_branches=4,
        max_retries=3, max_replans=3, max_agent_calls=64, max_tool_calls=16, max_execution_time=600_000, max_tokens=200_000,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceConfig:
    """Everything the service is configured with. ``model_settings`` has no default (D-135); ``limits`` has none either (D-103)."""

    limits: SystemLimits
    model_settings: ModelSettings
    allowed_actions: frozenset[str] = frozenset()  # the server's allowlist: a mission may name only these
    ceilings: ApiCeilings = field(default_factory=ApiCeilings)
    runner: RunnerConfig = field(default_factory=RunnerConfig)
    max_candidates: int = 3
    auto_provision_workspaces: bool = False  # D-237: a signed-in user with no tenant is given one of their own instead of ``no_tenant_membership``; off unless the deployer turns it on
