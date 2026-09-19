"""The eidos.contracts public surface (decisions.md D-108)."""

import pytest
from pydantic import ValidationError

import eidos.contracts as contracts
from eidos.contracts import EidosModel


def test_eidos_model_is_exported():
    assert "EidosModel" in contracts.__all__
    assert contracts.EidosModel is EidosModel


def test_every_name_in_all_resolves():
    missing = [name for name in contracts.__all__ if not hasattr(contracts, name)]
    assert missing == []


def test_all_has_no_duplicates():
    assert len(contracts.__all__) == len(set(contracts.__all__))


def test_a_subclass_of_the_exported_base_is_frozen_strict_and_forbids_extras():
    # The reason V0.2 needs the export: its own models must carry the same
    # configuration as every V0.1 contract.
    class Probe(EidosModel):
        count: int

    probe = Probe(count=1)
    with pytest.raises(ValidationError):
        probe.count = 2
    with pytest.raises(ValidationError):
        Probe(count="1")
    with pytest.raises(ValidationError):
        Probe(count=1, extra_field=True)
