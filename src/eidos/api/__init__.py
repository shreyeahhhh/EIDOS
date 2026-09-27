"""The V1.4 HTTP boundary (decisions.md D-233, D-234; ``docs/13_product_backend.md``).

FastAPI, Supabase-JWT verification and error mapping over ``eidos.service``. **It is the only package that imports FastAPI and the JWT library, and it never mutates ``MissionState``:** a route
authenticates, resolves the tenant and calls the service, and this package imports nothing of the runtime, the event log or the reducer. ``main`` is the composition root: it alone wires the
service to ``eidos.persistence`` and a model provider from the environment. No core layer imports this package.

    uvicorn eidos.api.main:create_app_from_environment --factory
"""

from .app import create_app
from .auth import AuthUnavailable, JwksKeys, JwtSettings, JwtVerifier, StaticKey, Unauthenticated

__all__ = ["AuthUnavailable", "JwksKeys", "JwtSettings", "JwtVerifier", "StaticKey", "Unauthenticated", "create_app"]
