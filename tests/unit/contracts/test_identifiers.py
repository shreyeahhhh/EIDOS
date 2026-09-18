"""Identifier types (decisions.md D-053, D-079, D-080, D-092, D-095, D-098).

typing.NewType performs no runtime check by itself, so these tests exercise
each identifier through a minimal strict pydantic model — the same
mechanism every real contract uses — to confirm the underlying type is
actually enforced.
"""

from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from eidos.contracts import (
    ActionId,
    ArtifactRef,
    CapabilityId,
    DEFAULT_TENANT_ID,
    StepId,
    TenantId,
)


class _UuidHolder(BaseModel):
    model_config = ConfigDict(strict=True)
    value: TenantId


class _StrHolder(BaseModel):
    model_config = ConfigDict(strict=True)
    value: StepId


def test_uuid_backed_identifier_accepts_uuid():
    holder = _UuidHolder(value=TenantId(uuid4()))
    assert isinstance(holder.value, UUID)


def test_uuid_backed_identifier_rejects_string():
    with pytest.raises(ValidationError):
        _UuidHolder(value=str(uuid4()))


def test_string_backed_identifier_accepts_str():
    holder = _StrHolder(value=StepId("research_1"))
    assert holder.value == "research_1"


def test_string_backed_identifier_rejects_uuid():
    with pytest.raises(ValidationError):
        _StrHolder(value=uuid4())


def test_string_backed_identifier_allows_llm_authored_style_ids():
    # decisions.md D-092: LLM-authored ids such as "research_1" remain valid.
    assert StepId("research_1") == "research_1"
    assert CapabilityId("research") == "research"
    assert ActionId("read_documents") == "read_documents"
    assert ArtifactRef("artifact-abc123") == "artifact-abc123"


def test_default_tenant_id_is_a_valid_tenant_id():
    assert isinstance(DEFAULT_TENANT_ID, UUID)


def test_default_tenant_id_is_the_nil_uuid_placeholder():
    # decisions.md D-032 is still Open; this is a documented placeholder
    # sentinel, not a meaningful value. This test pins the current constant
    # so a future change to it is a visible, deliberate diff.
    assert DEFAULT_TENANT_ID == UUID(int=0)
