"""Execution backends — adapters that run a compiled plan on an external execution engine.

decisions.md D-115: a backend is an adapter over the backend-neutral runtime, never the
architectural authority. It depends on ``eidos.runtime``; nothing in the core depends on it,
and the compiler, the runtime and every other core layer must not import an execution engine.

Each engine lives in its own subpackage, and only that subpackage may import the engine.
Backends are held to the sequential reference executor (D-128): for the same compiled plan,
context, prior outcomes and deterministic ports they must return the same ``RunResult`` or
``RunRejection``.
"""
