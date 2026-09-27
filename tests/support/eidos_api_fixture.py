"""Fixtures for the V1.4 API tests (decisions.md D-233, D-234): a real FastAPI app over the in-memory service rig, real JWT verification, no network and no credential.

Tokens are signed with keys generated here. The HS256 secret and the asymmetric key pairs exist only in these tests.
"""

import time
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from eidos.api import JwtSettings, JwtVerifier, StaticKey, create_app

from eidos_service_fixture import ALICE, BOB, CAROL, DAVE, TENANT_A, TENANT_B, ServiceRig, make_rig

AUDIENCE = "authenticated"
SECRET = "test-only-hs256-secret-that-is-comfortably-longer-than-32-bytes"


def token_for(user, *, secret=SECRET, algorithm="HS256", audience=AUDIENCE, expires_in=3600, extra=None, subject=None, omit=()):
    now = int(time.time())
    claims = {"sub": str(user) if subject is None else subject, "aud": audience, "exp": now + expires_in, "iat": now}
    claims.update(extra or {})
    for name in omit:
        claims.pop(name, None)
    return jwt.encode(claims, secret, algorithm=algorithm)


def bearer(user, **kwargs) -> dict:
    return {"Authorization": f"Bearer {token_for(user, **kwargs)}"}


def rsa_pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def ec_pair():
    private = ec.generate_private_key(ec.SECP256R1())
    return private, private.public_key()


@dataclass
class ApiRig:
    rig: ServiceRig
    client: TestClient
    verifier: JwtVerifier

    def headers(self, user=ALICE, tenant=None, **kwargs) -> dict:
        headers = bearer(user, **kwargs)
        if tenant is not None:
            headers["X-Tenant-Id"] = str(tenant)
        return headers


def make_api(*, rig: ServiceRig | None = None, verifier: JwtVerifier | None = None, raise_server_exceptions=False, **rig_kwargs) -> ApiRig:
    rig = rig or make_rig(**rig_kwargs)
    verifier = verifier or JwtVerifier(keys=StaticKey(SECRET), settings=JwtSettings(audience=AUDIENCE, algorithms=("HS256",)))
    app = create_app(service=rig.service, verifier=verifier, max_body_bytes=rig.config.ceilings.max_request_body_bytes)
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    client.__enter__()  # runs the lifespan: startup recovery
    return ApiRig(rig=rig, client=client, verifier=verifier)


def spec_json(**overrides) -> str:
    from eidos_service_fixture import make_spec

    return make_spec(**overrides).model_dump_json()


__all__ = ["ALICE", "AUDIENCE", "BOB", "CAROL", "DAVE", "SECRET", "TENANT_A", "TENANT_B", "ApiRig", "bearer", "ec_pair", "make_api", "rsa_pair", "spec_json", "token_for"]
