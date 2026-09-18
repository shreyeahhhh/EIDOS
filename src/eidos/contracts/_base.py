"""Shared base model for every EIDOS V0.1 contract.

Every contract is immutable, rejects unknown fields, and disables silent
type coercion. See CLAUDE.md §8 (typed, validated, versioned contracts) and
decisions.md D-005 (V0.1 is in-memory only; construction and validation
only, no behaviour).
"""

from pydantic import BaseModel, ConfigDict


class EidosModel(BaseModel):
    """Frozen, strict, closed-schema base for every EIDOS contract model."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
    )
