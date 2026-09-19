"""SystemLimits — the ceilings a plan and a reliability contract are checked against.

decisions.md: D-009 (bounds split: the three shape limits are system-only;
the six mission budgets live in ReliabilityContract and are tightened, never
exceeded, by the system ceiling — rejected, never clamped), D-042 (the
six-field budget group), D-078 (units: integer milliseconds, integer token
counts), D-103 (**no built-in numeric defaults**: every field is required, so
a caller that does not explicitly supply limits cannot construct one),
D-104 (``max_depth`` counts nodes), D-046 (the actual values — Open).

Numeric range: every field is an integer >= 0, matching the non-negative
range ReliabilityContract already imposes on its budgets. No field has an
upper bound, and none has a default.
"""

from enum import StrEnum

from pydantic import Field

from eidos.contracts import EidosModel


class LimitName(StrEnum):
    """The bounded dimensions of invariant 7 that V0.2 can name.

    Values equal the corresponding ``SystemLimits`` field names and, for the
    budgets, the corresponding ``ReliabilityContract`` field names.
    """

    MAX_NODES = "max_nodes"
    MAX_DEPTH = "max_depth"
    MAX_PARALLEL_BRANCHES = "max_parallel_branches"
    MAX_RETRIES = "max_retries"
    MAX_REPLANS = "max_replans"
    MAX_AGENT_CALLS = "max_agent_calls"
    MAX_TOOL_CALLS = "max_tool_calls"
    MAX_EXECUTION_TIME = "max_execution_time"
    MAX_TOKENS = "max_tokens"


# System-only limits on a plan's shape (D-009).
SHAPE_LIMITS: tuple[LimitName, ...] = (
    LimitName.MAX_NODES,
    LimitName.MAX_DEPTH,
    LimitName.MAX_PARALLEL_BRANCHES,
)

# The six mission budgets a ReliabilityContract may carry (D-042). Fixed order:
# violations are reported in this order, so reports are deterministic.
MISSION_BUDGETS: tuple[LimitName, ...] = (
    LimitName.MAX_RETRIES,
    LimitName.MAX_REPLANS,
    LimitName.MAX_AGENT_CALLS,
    LimitName.MAX_TOOL_CALLS,
    LimitName.MAX_EXECUTION_TIME,
    LimitName.MAX_TOKENS,
)


class SystemLimits(EidosModel):
    """System-level ceilings. Every field is required; there are no defaults (D-103)."""

    max_nodes: int = Field(ge=0)
    max_depth: int = Field(ge=0)  # longest dependency path, counted in nodes (D-104)
    max_parallel_branches: int = Field(ge=0)  # maximum antichain width (D-050)

    max_retries: int = Field(ge=0)
    max_replans: int = Field(ge=0)
    max_agent_calls: int = Field(ge=0)
    max_tool_calls: int = Field(ge=0)
    max_execution_time: int = Field(ge=0)  # milliseconds (D-078)
    max_tokens: int = Field(ge=0)

    def ceiling(self, name: LimitName) -> int:
        """The system ceiling for one named dimension."""
        return getattr(self, name.value)
