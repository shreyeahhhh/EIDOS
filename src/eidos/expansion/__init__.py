"""eidos.expansion — the deterministic Strategy-to-Plan boundary (decisions.md D-194, D-195; V0.9 Step 2).

A new core layer, joining ``eidos.contracts``, ``eidos.validation``, ``eidos.compiler``, ``eidos.runtime``,
``eidos.state`` and ``eidos.planning``: deterministic, no I/O, no clock, no hidden state, no model/vendor/tool
name. It cannot live inside ``eidos.planning`` itself — that package's own existing guard already forbids it from
ever importing ``StepId`` (D-179's exclusion of step ids and edges from ``Strategy``). Depends only on
``eidos.contracts`` (``Plan``, ``AgentStep``, ``ControlStep``, ``PlanId``, ``StepId``) and ``eidos.planning``
(``Strategy``, ``StrategyStage``, ``VerificationPosture``) — never ``eidos.validation``, ``eidos.compiler``,
``eidos.runtime``, ``eidos.agents`` or any adapter package.

    from eidos.expansion import PlanIdSource, expand_strategy

One capability occurrence becomes one ``AgentStep``, never deduplicated; a stage's steps depend on the whole of
the preceding stage (D-179's own definition, applied literally); ``FINAL`` verification appends exactly one
``VERIFY`` step depending exactly on the final stage's own step ids (D-195); ``NONE`` and an empty strategy
produce no ``VERIFY`` step. The output is an ordinary ``Plan`` — no shortcut around V0.2 validation or V0.3
compilation exists (D-178), and this module never calls ``check_feasibility`` (already decided, D-180/D-183).

``expand_strategy`` also accepts optional ``version``/``parent_plan_id``/``replan_reason`` keyword parameters
(D-199, V1.1 Step 1), defaulting to a fresh Plan's own values (``1``/``None``/``None``) — every existing caller
is unaffected. It only ever stamps whatever it is given onto the returned ``Plan``; deciding when a replan is
warranted, which candidate strategy comes next, and how the three values relate to each other and to prior
attempts is a caller's own job, not built here (V1.1's own orchestration layer, not yet built). D-129 (how a
work node receives its predecessors' outputs) stays Open.
"""

from .expand import PlanIdSource, expand_strategy

__all__ = ["PlanIdSource", "expand_strategy"]
