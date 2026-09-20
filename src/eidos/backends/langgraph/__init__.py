"""The LangGraph execution backend — milestone V0.3, Step 4.

    from eidos.backends.langgraph import LangGraphExecutor
    executor = LangGraphExecutor(work_executor=..., verifier=..., admission_guard=...)
    result = executor.run(compiled_plan, context)     # a RunResult, or a RunRejection

Same signature and same contract as ``eidos.runtime.SequentialExecutor``, which is the semantic oracle
this backend is held to (D-128). This is the **only** package in EIDOS that imports LangGraph (D-115), and
LangGraph is an optional extra (D-116): ``pip install 'eidos[langgraph]'``. Importing this package without
it raises an ``ImportError`` that says so; the compiler and the runtime never depend on it.

LangGraph supplies mechanics, not semantics. The graph state is ``outcomes`` and nothing else, MissionState
never enters it (D-113), and no checkpointing, interrupt or LangGraph retry is used (D-127).
"""

from .errors import BackendError
from .executor import LangGraphExecutor

__all__ = ["BackendError", "LangGraphExecutor"]
