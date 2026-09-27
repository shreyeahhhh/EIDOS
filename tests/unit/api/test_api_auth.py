"""Supabase-issued JWT verification at the boundary (decisions.md D-233; V1.4-B).

What is held: a token is accepted only if its signature, expiry and audience are right and its ``sub`` is a UUID; the algorithm list is fixed by configuration and never read from the token, so
``none`` and algorithm-confusion tokens are refused; every rejection is one ``Unauthenticated`` whose reason is never told; and key material that cannot be fetched is ``AuthUnavailable`` (the
token was not judged), never a rejection. Keys are generated here; nothing touches the network.
"""

import base64
import hashlib
import hmac
import json
import time
from uuid import UUID

import pytest
from cryptography.hazmat.primitives import serialization
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from eidos.api import AuthUnavailable, JwksKeys, JwtSettings, JwtVerifier, StaticKey, Unauthenticated
from eidos.api.auth import ASYMMETRIC_ALGORITHMS, SYMMETRIC_ALGORITHMS

from eidos_api_fixture import AUDIENCE, SECRET, ec_pair, rsa_pair, token_for
from eidos_service_fixture import ALICE


def hs256(**settings):
    return JwtVerifier(keys=StaticKey(SECRET), settings=JwtSettings(audience=AUDIENCE, algorithms=("HS256",), **settings))


def rejected(verifier, token):
    with pytest.raises(Unauthenticated) as raised:
        verifier.verify(token)
    return raised.value


def test_a_valid_token_is_the_user_its_subject_names():
    assert hs256().verify(token_for(ALICE)) == ALICE


def test_the_extra_claims_a_provider_adds_are_ignored_and_never_make_a_user():
    token = token_for(ALICE, extra={"role": "authenticated", "email": "someone@example.test", "app_metadata": {"tenant_id": "00000000-0000-0000-0000-000000000000"}})
    assert hs256().verify(token) == ALICE  # the identity is the subject and nothing else in the token


@pytest.mark.parametrize("expires_in", [-1, -3600])
def test_an_expired_token_is_refused(expires_in):
    rejected(hs256(), token_for(ALICE, expires_in=expires_in))


def test_a_little_leeway_is_a_setting_and_not_the_default():
    token = token_for(ALICE, expires_in=-5)
    rejected(hs256(), token)
    assert hs256(leeway_seconds=30).verify(token) == ALICE


def test_a_token_for_another_audience_is_refused():
    rejected(hs256(), token_for(ALICE, audience="anon"))
    rejected(hs256(), token_for(ALICE, audience="service_role"))
    assert JwtVerifier(keys=StaticKey(SECRET), settings=JwtSettings(audience="anon", algorithms=("HS256",))).verify(token_for(ALICE, audience="anon")) == ALICE


@pytest.mark.parametrize("missing", ["sub", "aud", "exp"])
def test_a_token_without_a_required_claim_is_refused(missing):
    rejected(hs256(), token_for(ALICE, omit=(missing,)))


@pytest.mark.parametrize("subject", ["not-a-uuid", "", "1234", "00000000-0000-0000-0000-00000000000g"])
def test_a_subject_that_is_not_a_uuid_is_refused(subject):
    rejected(hs256(), token_for(ALICE, subject=subject))


def test_a_token_signed_with_another_secret_or_altered_is_refused():
    rejected(hs256(), token_for(ALICE, secret="another-secret-that-is-also-comfortably-longer-than-32-bytes"))
    header, payload, signature = token_for(ALICE).split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"sub": str(UUID(int=0x22)), "aud": AUDIENCE, "exp": int(time.time()) + 3600}).encode()).rstrip(b"=").decode()
    rejected(hs256(), ".".join((header, forged, signature)))  # a different subject under the same signature


def test_an_unsigned_token_with_alg_none_is_refused():
    def part(document):
        return base64.urlsafe_b64encode(json.dumps(document).encode()).rstrip(b"=").decode()

    unsigned = f"{part({'alg': 'none', 'typ': 'JWT'})}.{part({'sub': str(ALICE), 'aud': AUDIENCE, 'exp': int(time.time()) + 3600})}."
    rejected(hs256(), unsigned)
    rejected(JwtVerifier(keys=StaticKey(rsa_pair()[1]), settings=JwtSettings(audience=AUDIENCE, algorithms=ASYMMETRIC_ALGORITHMS)), unsigned)


def test_the_algorithm_comes_from_the_configuration_and_never_from_the_token():
    private, public = rsa_pair()
    verifier = JwtVerifier(keys=StaticKey(public), settings=JwtSettings(audience=AUDIENCE, algorithms=ASYMMETRIC_ALGORITHMS))
    assert verifier.verify(token_for(ALICE, secret=private, algorithm="RS256")) == ALICE
    # algorithm confusion: an HS256 token MACed with the public key's own bytes, built by hand because PyJWT itself refuses to use a PEM key as an HMAC secret
    public_pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def part(document):
        return base64.urlsafe_b64encode(json.dumps(document).encode()).rstrip(b"=")

    signing_input = part({"alg": "HS256", "typ": "JWT"}) + b"." + part({"sub": str(ALICE), "aud": AUDIENCE, "exp": int(time.time()) + 3600})
    mac = base64.urlsafe_b64encode(hmac.new(public_pem, signing_input, hashlib.sha256).digest()).rstrip(b"=")
    rejected(verifier, (signing_input + b"." + mac).decode())
    rejected(verifier, token_for(ALICE))  # an HS256 token, whatever it is signed with, is not in this verifier's list
    rejected(hs256(), token_for(ALICE, secret=private, algorithm="RS256"))  # and an asymmetric token is not in the HS256 verifier's list


def test_es256_and_rs256_are_the_asymmetric_algorithms_and_hs256_the_only_symmetric_one():
    assert ASYMMETRIC_ALGORITHMS == ("RS256", "ES256") and SYMMETRIC_ALGORITHMS == ("HS256",)
    ec_private, ec_public = ec_pair()
    verifier = JwtVerifier(keys=StaticKey(ec_public), settings=JwtSettings(audience=AUDIENCE, algorithms=ASYMMETRIC_ALGORITHMS))
    assert verifier.verify(token_for(ALICE, secret=ec_private, algorithm="ES256")) == ALICE
    rejected(verifier, token_for(ALICE, secret=ec_private, algorithm="ES256", audience="anon"))


def test_an_issuer_is_checked_only_when_one_is_configured():
    with_issuer = hs256(issuer="https://project.example.test/auth/v1")
    assert with_issuer.verify(token_for(ALICE, extra={"iss": "https://project.example.test/auth/v1"})) == ALICE
    rejected(with_issuer, token_for(ALICE, extra={"iss": "https://elsewhere.example.test/auth/v1"}))
    rejected(with_issuer, token_for(ALICE))  # an issuer was asked for and the token names none
    assert hs256().verify(token_for(ALICE, extra={"iss": "anything"})) == ALICE


@pytest.mark.parametrize("token", ["", "x", "a.b", "a.b.c", "Bearer x", "\x00", "é.é.é", "x" * 8193])
def test_a_malformed_or_oversized_token_is_refused(token):
    rejected(hs256(), token)


def test_a_rejection_never_tells_the_reason():
    reasons = {str(rejected(hs256(), token).args) for token in (token_for(ALICE, expires_in=-1), token_for(ALICE, audience="x"), token_for(ALICE, subject="nope"), "garbage")}
    assert len(reasons) <= 2 and not any(word in " ".join(reasons).lower() for word in ("expired", "audience", "signature", "subject"))


def test_a_verifier_names_its_algorithms_and_its_audience_and_never_accepts_none():
    for algorithms in ((), ("none",), ("None",), ("HS256", "none")):
        with pytest.raises(ValueError):
            JwtVerifier(keys=StaticKey(SECRET), settings=JwtSettings(audience=AUDIENCE, algorithms=algorithms))
    with pytest.raises(ValueError):
        JwtVerifier(keys=StaticKey(SECRET), settings=JwtSettings(audience="", algorithms=("HS256",)))


# --- the JWKS key source -------------------------------------------------------------------------------------------------------------


def test_a_jwks_endpoint_is_https_and_its_cache_is_at_most_ten_minutes():
    for url in ("http://project.example.test/auth/v1/.well-known/jwks.json", "", "file:///keys.json"):
        with pytest.raises(ValueError):
            JwksKeys(url)
    for lifespan in (0, -1, 601):
        with pytest.raises(ValueError):
            JwksKeys("https://project.example.test/auth/v1/.well-known/jwks.json", lifespan_seconds=lifespan)
    JwksKeys("https://project.example.test/auth/v1/.well-known/jwks.json", lifespan_seconds=600)


def test_jwks_keys_that_cannot_be_fetched_are_an_unavailable_service_and_not_a_rejection(monkeypatch):
    keys = JwksKeys("https://project.example.test/auth/v1/.well-known/jwks.json")

    def down(token):
        raise PyJWKClientConnectionError("no route to the keys")

    monkeypatch.setattr(keys._client, "get_signing_key_from_jwt", down)
    verifier = JwtVerifier(keys=keys, settings=JwtSettings(audience=AUDIENCE, algorithms=ASYMMETRIC_ALGORITHMS))
    private, _ = rsa_pair()
    with pytest.raises(AuthUnavailable):
        verifier.verify(token_for(ALICE, secret=private, algorithm="RS256"))


def test_a_token_whose_key_the_jwks_does_not_hold_is_a_rejection(monkeypatch):
    keys = JwksKeys("https://project.example.test/auth/v1/.well-known/jwks.json")

    def unknown(token):
        raise PyJWKClientError("no key with this kid")

    monkeypatch.setattr(keys._client, "get_signing_key_from_jwt", unknown)
    verifier = JwtVerifier(keys=keys, settings=JwtSettings(audience=AUDIENCE, algorithms=ASYMMETRIC_ALGORITHMS))
    private, _ = rsa_pair()
    rejected(verifier, token_for(ALICE, secret=private, algorithm="RS256"))


def test_jwks_keys_resolve_a_signing_key_through_the_client_and_verify_the_signature(monkeypatch):
    keys = JwksKeys("https://project.example.test/auth/v1/.well-known/jwks.json")
    private, public = rsa_pair()

    class Signing:
        key = public

    monkeypatch.setattr(keys._client, "get_signing_key_from_jwt", lambda token: Signing())
    verifier = JwtVerifier(keys=keys, settings=JwtSettings(audience=AUDIENCE, algorithms=ASYMMETRIC_ALGORITHMS))
    assert verifier.verify(token_for(ALICE, secret=private, algorithm="RS256")) == ALICE
    other_private, _ = rsa_pair()
    rejected(verifier, token_for(ALICE, secret=other_private, algorithm="RS256"))  # signed by a key the endpoint does not publish
