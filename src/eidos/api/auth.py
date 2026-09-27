"""Supabase-issued JWT verification at the FastAPI boundary (decisions.md D-233; ``docs/13`` section 5).

**Verified: signature, expiry and audience.** ``exp``, ``sub`` and ``aud`` are required; the audience must equal the configured one (Supabase's own value for a signed-in user is
``authenticated``); an issuer is checked only if one is configured. The token's ``sub`` must be a UUID and is the user's identity. Any failure is one ``Unauthenticated``; the reason is never
told to the caller.

**Key material comes from one of two places, each with its own algorithm allowlist** (Supabase documents both; verified against its current documentation on 2026-09-26): its asymmetric signing
keys, fetched from the project's JWKS endpoint (``https://<project>.supabase.co/auth/v1/.well-known/jwks.json``) and cached for at most ten minutes so a key rotation is picked up, or the legacy
shared HS256 secret, which Supabase discourages. The algorithm list is fixed by configuration and never read from the token, and ``none`` is refused at construction. A JWKS endpoint that cannot
be reached is ``AuthUnavailable`` (a 503), not a 401: the request was not judged.

Nothing here knows a user database: who a user is comes from the token alone, and what they may see comes from tenant membership in the service.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from eidos.service import UserId

ASYMMETRIC_ALGORITHMS = ("RS256", "ES256")
SYMMETRIC_ALGORITHMS = ("HS256",)


class Unauthenticated(Exception):
    """The token is missing, malformed, unsigned, expired, for another audience or otherwise not acceptable."""


class AuthUnavailable(Exception):
    """The key material could not be fetched, so the token could not be judged."""


@dataclass(frozen=True, slots=True)
class JwtSettings:
    audience: str
    algorithms: tuple[str, ...]
    issuer: str | None = None
    leeway_seconds: int = 0


class KeyResolver(Protocol):
    def key_for(self, token: str) -> object:
        """The verification key for this token. Raises ``Unauthenticated`` or ``AuthUnavailable``."""


class StaticKey:
    """One fixed key: the legacy HS256 secret, or a public key. Also what the tests use."""

    def __init__(self, key: object) -> None:
        self._key = key

    def key_for(self, token: str) -> object:
        return self._key


class JwksKeys:
    """Keys fetched from a JWKS endpoint, cached for ``lifespan_seconds`` (at most ten minutes, so a rotation is picked up)."""

    def __init__(self, url: str, *, lifespan_seconds: int = 600, timeout_seconds: int = 10) -> None:
        if not 0 < lifespan_seconds <= 600:
            raise ValueError("the JWKS cache lifespan is 1 to 600 seconds")
        if not url.startswith("https://"):
            raise ValueError("a JWKS endpoint is an https URL")
        self._client = PyJWKClient(url, cache_keys=True, lifespan=lifespan_seconds, timeout=timeout_seconds)

    def key_for(self, token: str) -> object:
        try:
            return self._client.get_signing_key_from_jwt(token).key
        except PyJWKClientConnectionError as error:
            raise AuthUnavailable("the signing keys could not be fetched") from error
        except jwt.PyJWTError as error:
            raise Unauthenticated("no signing key for this token") from error


class JwtVerifier:
    def __init__(self, *, keys: KeyResolver, settings: JwtSettings) -> None:
        algorithms = tuple(settings.algorithms)
        if not algorithms or any(name.lower() == "none" for name in algorithms):
            raise ValueError("a verifier names its algorithms and never accepts none")
        if not settings.audience:
            raise ValueError("a verifier names its audience")
        self._keys, self._settings, self._algorithms = keys, settings, algorithms

    def verify(self, token: str) -> UserId:
        """The user the token identifies. Raises ``Unauthenticated`` for any token that is not acceptable, ``AuthUnavailable`` if the keys cannot be had."""
        if not token or len(token) > 8192:
            raise Unauthenticated("no usable token")
        try:
            claims = jwt.decode(
                token, self._keys.key_for(token), algorithms=list(self._algorithms), audience=self._settings.audience, issuer=self._settings.issuer,
                leeway=self._settings.leeway_seconds, options={"require": ["exp", "sub", "aud"]},
            )
            subject = UUID(str(claims["sub"]))
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as error:
            raise Unauthenticated("the token is not acceptable") from error
        return UserId(subject)
