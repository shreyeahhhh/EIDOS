"""Factories for V0.2 validation tests.

The numbers below are **arbitrary, explicitly labelled test fixtures**
(decisions.md D-103, point 4). They are not defaults, not proposals for
production values, and not measurements; D-046 (Open) owns the real values.
They are deliberately distinct from one another so a test that mixes up two
limits fails instead of passing by coincidence.
"""

from eidos.validation.limits import SystemLimits

# ARBITRARY TEST FIXTURE VALUES — see module docstring.
FIXTURE_LIMIT_VALUES: dict[str, int] = dict(
    max_nodes=50,
    max_depth=10,
    max_parallel_branches=8,
    max_retries=3,
    max_replans=2,
    max_agent_calls=20,
    max_tool_calls=40,
    max_execution_time=60_000,
    max_tokens=5_000,
)


def make_system_limits(**overrides) -> SystemLimits:
    fields = dict(FIXTURE_LIMIT_VALUES)
    fields.update(overrides)
    return SystemLimits(**fields)
