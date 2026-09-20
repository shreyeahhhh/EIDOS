"""BackendError — a fault in the LangGraph backend, never an outcome of a run."""


class BackendError(Exception):
    """The LangGraph backend, or the library beneath it, failed.

    This is deliberately an *exception*, not a typed result. Everything that can legitimately
    happen in a run has a typed representation and is never raised: a port that fails or
    misbehaves is a ``FAILED`` node, a guard that faults halts the run, and a plan, context or
    prior that may not run is a ``RunRejection``. What is left when something is raised is a
    defect — in this adapter, or in the engine — and must not be dressed up as a mission
    outcome (invariant 13: never manufacture an answer).

    The original exception, if any, is chained as ``__cause__``.
    """
