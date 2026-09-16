"""Shared pytest configuration for the EIDOS test suite.

Intentionally empty. ``src`` is placed on the import path by ``pythonpath`` in
``pyproject.toml``, so no path manipulation is needed here.

Fixtures are added when the tests that need them are written. Keep this file free of
anything that hides a failure: no global error suppression, no autouse fixtures that
patch over real behaviour. See CLAUDE.md §6.
"""
