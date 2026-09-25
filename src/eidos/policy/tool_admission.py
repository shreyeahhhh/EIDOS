"""Deterministic tool admission (decisions.md D-203, invariant 14; V1.2 Step 2).

"Can perform" and "is allowed to perform" are separate checks, enforced in code and never by a prompt. This module is the
second one for a tool call, and the whole of it: a pure function from an allowlist, a request and a handful of explicit
facts to one typed decision. It reads no clock, opens no file, calls no model and holds no state; everything it needs is a
parameter, so the same inputs always give the same decision, whatever the process, the hash seed or the order the inputs
were built in. **It is not a general policy engine** (D-203 ruling 2).

**A precondition, decided before every rule below (D-205 ruling 1).** Admission needs an explicit, finite, non-negative integer budget. An unset
``max_tool_calls`` (``None``, the contract's default) is unresolved configuration: it is neither unlimited nor zero and it is never replaced by an
invented default, so the call is denied ``BUDGET_UNRESOLVED``. A value that is set but not a non-negative integer (a negative number, a ``bool``, a
float such as infinity) is a programming error and raises. The denial comes before any duplicate lookup, so a stored duplicate is not served when the
budget is unset and the history is not even read (D-205 item 2); it is a configuration refusal, neither a tool invocation nor a consumed budget.

The rules, applied **in this fixed order**, the first that fails deciding the denial:

1. ``UNKNOWN_TOOL``: the tool is not in the pinned allowlist (exact string; never the nearest match).
2. ``NOT_READ_ONLY``: the allowlist entry does not declare the tool read-only. Read-only is EIDOS's own declaration on the entry;
   nothing a provider says about a tool is an input here, and there is no parameter for it.
3. ``ACTION_NOT_ALLOWED``: the entry's ``action_id`` is not exactly one of the mission's ``allowed_actions``.
4. ``AUTONOMY_TOO_LOW``: the mission's ``autonomy_level`` is below ``SAFE_READ_ONLY`` (handoff §29: level 1, safe read-only actions).
5. ``INVALID_ARGUMENTS``: the arguments do not match the entry's argument schema (unknown, missing, wrong type, out of bounds).
6. **Duplicate**: an earlier invocation *in this execution* (any plan attempt) of the same tool with the same arguments stored its result.
   The decision is ``SERVE_STORED``: no tool is invoked and **no invocation budget is consumed**, so an exact duplicate is served even when
   the attempt's budget is spent.
7. ``BUDGET_EXHAUSTED``: this plan attempt has already made ``max_tool_calls`` invocations.
8. Otherwise ``INVOKE``, carrying the entry's own timeout and result-size bound for the caller to apply.

**Budget scope (D-203 ruling 5).** The budget is per plan attempt, scoped by ``(execution_id, plan_id)``: only invocations recorded for
that pair count, so each replan starts with a fresh budget. **Duplicate detection is execution-wide**, keyed by ``(execution_id, tool_id,
args_digest)``. There is no mission-wide cumulative enforcement, which stays deferred under D-043. Every invocation that reached the tool
counts against its attempt's budget, whether or not it produced a stored result; only an invocation whose result was stored can serve a
later duplicate. ``max_tool_calls`` must be an explicit finite integer: an absent contract value is denied, not resolved, here or anywhere
in this module.

Nothing here spawns a process, speaks a protocol or imports an adapter; the transport lives elsewhere and this layer is unaware of it.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from enum import StrEnum

from pydantic import Field, model_validator

from eidos.capabilities import ToolArgumentKind, ToolDescriptor, ToolRegistry
from eidos.contracts import ActionId, AutonomyLevel, EidosModel, ExecutionId, PlanId

_SHA256_HEX = r"^[0-9a-f]{64}$"


class ToolDenialCode(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    NOT_READ_ONLY = "not_read_only"
    ACTION_NOT_ALLOWED = "action_not_allowed"
    AUTONOMY_TOO_LOW = "autonomy_too_low"
    INVALID_ARGUMENTS = "invalid_arguments"
    BUDGET_EXHAUSTED = "budget_exhausted"
    BUDGET_UNRESOLVED = "budget_unresolved"


class ArgumentViolationCode(StrEnum):
    UNKNOWN_ARGUMENT = "unknown_argument"
    MISSING_ARGUMENT = "missing_argument"
    WRONG_TYPE = "wrong_type"
    OUT_OF_BOUNDS = "out_of_bounds"


class ArgumentViolation(EidosModel):
    name: str
    code: ArgumentViolationCode
    message: str = Field(min_length=1)


class ToolDenial(EidosModel):
    """Why a call was refused. ``violations`` is non-empty exactly for ``INVALID_ARGUMENTS``."""

    code: ToolDenialCode
    message: str = Field(min_length=1)
    violations: tuple[ArgumentViolation, ...] = ()

    @model_validator(mode="after")
    def _check_violations_belong_to_invalid_arguments(self) -> "ToolDenial":
        if (self.code is ToolDenialCode.INVALID_ARGUMENTS) != bool(self.violations):
            raise ValueError("exactly an invalid_arguments denial lists the argument violations")
        return self


class ToolDecision(StrEnum):
    INVOKE = "invoke"
    SERVE_STORED = "serve_stored"
    DENY = "deny"


class ToolAdmission(EidosModel):
    """The one decision. A mislabelled decision is unconstructible: each kind carries exactly what it needs and nothing else.

    ``tool_id`` is echoed exactly as the caller supplied it, so it is unconstrained: a request naming nothing is denied ``UNKNOWN_TOOL``
    like any other stranger, and the denial must still be returnable."""

    decision: ToolDecision
    tool_id: str
    args_digest: str | None = Field(default=None, pattern=_SHA256_HEX)
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_result_bytes: int | None = Field(default=None, gt=0)
    denial: ToolDenial | None = None

    @model_validator(mode="after")
    def _check_the_fields_match_the_decision(self) -> "ToolAdmission":
        bounds = (self.timeout_seconds is not None, self.max_result_bytes is not None)
        if self.decision is ToolDecision.DENY:
            if self.denial is None or self.args_digest is not None or any(bounds):
                raise ValueError("a denial carries its reason and nothing else")
        elif self.denial is not None:
            raise ValueError("only a denial carries a denial")
        elif self.decision is ToolDecision.SERVE_STORED:
            if self.args_digest is None or any(bounds):
                raise ValueError("serving a stored result carries the argument digest and no bounds: nothing is invoked")
        elif self.args_digest is None or not all(bounds):
            raise ValueError("an admitted invocation carries the argument digest, the timeout and the result-size bound")
        return self


class ToolInvocationRecord(EidosModel):
    """One earlier invocation that reached a tool. ``result_stored`` says whether it produced a stored result a duplicate can be served from."""

    execution_id: ExecutionId
    plan_id: PlanId
    tool_id: str = Field(min_length=1)
    args_digest: str = Field(pattern=_SHA256_HEX)
    result_stored: bool


def args_digest(arguments: Mapping[str, str | int]) -> str:
    """A canonical SHA-256 (lowercase hex) of a call's arguments: independent of the order they were given in, and of the hash seed.

    Names are sorted, non-ASCII text is escaped, and there is no incidental whitespace, so the same arguments always give the same
    digest. A string and an integer never collide (``"1"`` is not ``1``).
    """
    canonical = json.dumps(dict(arguments), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _argument_violations(descriptor: ToolDescriptor, arguments: Mapping[str, object]) -> tuple[ArgumentViolation, ...]:
    found: list[ArgumentViolation] = []
    known = {spec.name for spec in descriptor.arguments}
    for name in arguments:
        if name not in known:
            found.append(ArgumentViolation(name=str(name), code=ArgumentViolationCode.UNKNOWN_ARGUMENT, message=f"{str(name)!r} is not an argument of this tool"))
    for spec in descriptor.arguments:
        if spec.name not in arguments:
            if spec.required:
                found.append(ArgumentViolation(name=spec.name, code=ArgumentViolationCode.MISSING_ARGUMENT, message=f"{spec.name!r} is required"))
            continue
        value = arguments[spec.name]
        if spec.kind is ToolArgumentKind.STRING:
            if not isinstance(value, str):
                found.append(ArgumentViolation(name=spec.name, code=ArgumentViolationCode.WRONG_TYPE, message=f"{spec.name!r} must be a string"))
            elif not spec.minimum <= len(value) <= spec.maximum:
                found.append(
                    ArgumentViolation(
                        name=spec.name, code=ArgumentViolationCode.OUT_OF_BOUNDS,
                        message=f"{spec.name!r} must be between {spec.minimum} and {spec.maximum} characters long",
                    )
                )
        else:
            if not _is_int(value):
                found.append(ArgumentViolation(name=spec.name, code=ArgumentViolationCode.WRONG_TYPE, message=f"{spec.name!r} must be an integer"))
            elif not spec.minimum <= value <= spec.maximum:
                found.append(
                    ArgumentViolation(
                        name=spec.name, code=ArgumentViolationCode.OUT_OF_BOUNDS,
                        message=f"{spec.name!r} must be between {spec.minimum} and {spec.maximum}",
                    )
                )
    return tuple(sorted(found, key=lambda violation: (violation.name, violation.code.value)))


def _deny(tool_id: str, code: ToolDenialCode, message: str, violations: tuple[ArgumentViolation, ...] = ()) -> ToolAdmission:
    return ToolAdmission(decision=ToolDecision.DENY, tool_id=tool_id, denial=ToolDenial(code=code, message=message, violations=violations))


def admit_tool_call(
    *,
    registry: ToolRegistry,
    tool_id: str,
    arguments: Mapping[str, object],
    execution_id: ExecutionId,
    plan_id: PlanId,
    allowed_actions: Iterable[ActionId],
    autonomy_level: AutonomyLevel,
    max_tool_calls: int | None,
    prior_invocations: Iterable[ToolInvocationRecord],
) -> ToolAdmission:
    """Decide one tool call. Pure and total: every outcome, including a refusal, is a returned ``ToolAdmission``.

    ``arguments`` is whatever the caller wants to send and is deliberately untyped: validating it is the point. ``max_tool_calls`` is the bound
    for this plan attempt, passed through exactly as the contract has it: ``None`` is unresolved configuration and is denied ``BUDGET_UNRESOLVED``
    (never unlimited, never zero, never a default), while any other value that is not a non-negative integer is a programming error, not an
    outcome. ``prior_invocations`` is the execution's history of invocations that reached a tool; it is read, never changed.
    """
    if max_tool_calls is None:
        return _deny(
            tool_id, ToolDenialCode.BUDGET_UNRESOLVED,
            "no tool-call budget is configured for this plan attempt (max_tool_calls is unset), and an unset budget is neither unlimited nor zero",
        )
    if not _is_int(max_tool_calls) or max_tool_calls < 0:
        raise ValueError("max_tool_calls must be None or a non-negative integer")

    descriptor = registry.resolve(tool_id)
    if descriptor is None:
        return _deny(tool_id, ToolDenialCode.UNKNOWN_TOOL, f"{tool_id!r} is not in the tool allowlist")
    if not descriptor.read_only:
        return _deny(tool_id, ToolDenialCode.NOT_READ_ONLY, f"{tool_id!r} is not declared read-only by the allowlist")
    if descriptor.action_id not in frozenset(allowed_actions):
        return _deny(tool_id, ToolDenialCode.ACTION_NOT_ALLOWED, f"the action {str(descriptor.action_id)!r} is not among the mission's allowed actions")
    if autonomy_level < AutonomyLevel.SAFE_READ_ONLY:
        return _deny(tool_id, ToolDenialCode.AUTONOMY_TOO_LOW, f"autonomy level {int(autonomy_level)} is below the level a read-only action needs ({int(AutonomyLevel.SAFE_READ_ONLY)})")
    violations = _argument_violations(descriptor, arguments)
    if violations:
        return _deny(tool_id, ToolDenialCode.INVALID_ARGUMENTS, f"the arguments do not match the schema of {tool_id!r}", violations)

    digest = args_digest(arguments)  # type: ignore[arg-type]  # validated above: every value is a str or an int
    history = tuple(prior_invocations)
    if any(
        prior.execution_id == execution_id and prior.tool_id == tool_id and prior.args_digest == digest and prior.result_stored
        for prior in history
    ):
        return ToolAdmission(decision=ToolDecision.SERVE_STORED, tool_id=tool_id, args_digest=digest)

    made = sum(1 for prior in history if prior.execution_id == execution_id and prior.plan_id == plan_id)
    if made >= max_tool_calls:
        return _deny(tool_id, ToolDenialCode.BUDGET_EXHAUSTED, f"this plan attempt has made {made} tool invocations, the most it may make is {max_tool_calls}")

    return ToolAdmission(
        decision=ToolDecision.INVOKE, tool_id=tool_id, args_digest=digest,
        timeout_seconds=descriptor.timeout_seconds, max_result_bytes=descriptor.max_result_bytes,
    )
