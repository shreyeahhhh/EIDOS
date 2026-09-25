"""``ToolDescriptor`` / ``ToolRegistry`` — the pinned tool allowlist (decisions.md D-203; V1.2 Step 2)."""

import pytest
from pydantic import ValidationError

from eidos.capabilities import RESEARCH, ToolArgumentKind, ToolArgumentSpec, ToolDescriptor, ToolRegistry
from eidos.contracts import ActionId, CapabilityId

from eidos_tool_factories import SCHEMA_DIGEST, limit_spec, make_search_descriptor, query_spec


def other_tool(**overrides) -> ToolDescriptor:
    return make_search_descriptor(**({"provider_id": "wiki", "tool_name": "lookup"} | overrides))


# --- the entry -------------------------------------------------------------------------------------------------------


def test_a_valid_entry_constructs_and_names_its_tool_id_from_provider_and_tool():
    descriptor = make_search_descriptor()
    assert descriptor.tool_id == "docs/search_documents"
    assert descriptor.capability == RESEARCH and descriptor.read_only is True


def test_the_entry_has_exactly_the_fields_eidos_states_and_none_a_provider_could_supply():
    # Read-only comes from the allowlist entry itself; there is no field a provider's own claim about a tool could be stored in.
    assert set(ToolDescriptor.model_fields) == {
        "provider_id", "tool_name", "capability", "action_id", "read_only", "arguments", "timeout_seconds", "max_result_bytes", "input_schema_digest",
    }
    assert not any("annot" in name or "hint" in name for name in ToolDescriptor.model_fields)


def test_an_entry_that_is_not_read_only_is_representable_it_is_admission_that_refuses_it():
    assert make_search_descriptor(read_only=False).read_only is False


def test_a_registry_holds_a_not_read_only_entry_as_it_is_and_neither_refuses_nor_filters_it():
    # D-205 ruling 2: representing a not-read-only entry is valid; refusing it is admission's job, not the allowlist's.
    entry = make_search_descriptor(read_only=False)
    registry = ToolRegistry(tools=(entry,))
    assert registry.resolve(entry.tool_id) == entry and registry.resolve(entry.tool_id).read_only is False
    assert registry.for_capability(RESEARCH) == (entry,)


@pytest.mark.parametrize("bad", ["", "a/b", "a b", "a" * 129, "café", "line\nbreak", "semi;colon"])
@pytest.mark.parametrize("field", ["provider_id", "tool_name"])
def test_a_provider_id_or_tool_name_outside_the_allowed_characters_or_length_is_refused(field, bad):
    with pytest.raises(ValidationError):
        make_search_descriptor(**{field: bad})


@pytest.mark.parametrize("good", ["a", "A_b-c.d", "x" * 128, "v1.2-beta_3"])
@pytest.mark.parametrize("field", ["provider_id", "tool_name"])
def test_the_allowed_characters_and_the_length_boundary_are_accepted(field, good):
    assert make_search_descriptor(**{field: good}).tool_id.count("/") == 1


@pytest.mark.parametrize("bad", ["", "AB" * 32, "ab" * 31, "ab" * 33, "zz" * 32, "0x" + "ab" * 31])
def test_the_schema_pin_must_be_a_lowercase_hex_sha256(bad):
    with pytest.raises(ValidationError):
        make_search_descriptor(input_schema_digest=bad)


def test_the_schema_pin_is_carried_verbatim():
    assert make_search_descriptor(input_schema_digest=SCHEMA_DIGEST).input_schema_digest == SCHEMA_DIGEST


@pytest.mark.parametrize("field, bad", [("timeout_seconds", 0), ("timeout_seconds", -1.5), ("max_result_bytes", 0), ("max_result_bytes", -1)])
def test_a_timeout_and_a_result_size_bound_must_be_positive(field, bad):
    with pytest.raises(ValidationError):
        make_search_descriptor(**{field: bad})


def test_the_action_may_not_be_blank():
    with pytest.raises(ValidationError):
        make_search_descriptor(action_id=ActionId(""))


def test_an_entry_lists_each_argument_at_most_once():
    with pytest.raises(ValidationError):
        make_search_descriptor(arguments=(query_spec(), query_spec(required=False)))


def test_an_entry_with_no_arguments_is_valid():
    assert make_search_descriptor(arguments=()).arguments == ()


def test_every_field_is_required_no_silent_default():
    fields = {name: getattr(make_search_descriptor(), name) for name in ToolDescriptor.model_fields}
    for name in fields:
        with pytest.raises(ValidationError):
            ToolDescriptor(**{key: value for key, value in fields.items() if key != name})


def test_the_entry_is_immutable_and_closed():
    descriptor = make_search_descriptor()
    with pytest.raises(ValidationError):
        descriptor.read_only = False
    with pytest.raises(ValidationError):
        ToolDescriptor(**{**descriptor.model_dump(), "readOnlyHint": True})


def test_the_entry_round_trips_through_json():
    descriptor = make_search_descriptor()
    assert ToolDescriptor.model_validate_json(descriptor.model_dump_json()) == descriptor


# --- an argument spec ------------------------------------------------------------------------------------------------


def test_a_minimum_above_the_maximum_is_refused():
    with pytest.raises(ValidationError):
        query_spec(minimum=5, maximum=4)


@pytest.mark.parametrize("bounds", [dict(minimum=-1, maximum=5), dict(minimum=0, maximum=0)])
def test_a_string_length_bound_must_be_a_sensible_length(bounds):
    with pytest.raises(ValidationError):
        query_spec(**bounds)


def test_an_integer_may_have_negative_and_zero_bounds_but_still_ordered():
    assert limit_spec(minimum=-5, maximum=0).minimum == -5
    with pytest.raises(ValidationError):
        limit_spec(minimum=0, maximum=-5)


@pytest.mark.parametrize("bad", ["", "has space", "a/b", "x" * 129])
def test_an_argument_name_uses_the_identifier_characters(bad):
    with pytest.raises(ValidationError):
        query_spec(name=bad)


def test_the_kind_is_a_closed_pair_and_required_is_a_real_boolean():
    assert {kind.value for kind in ToolArgumentKind} == {"string", "integer"}
    with pytest.raises(ValidationError):
        query_spec(kind="float")
    with pytest.raises(ValidationError):
        query_spec(required="yes")


# --- the registry ----------------------------------------------------------------------------------------------------


def test_the_registry_resolves_by_exact_string_and_never_by_the_nearest_match():
    registry = ToolRegistry(tools=(make_search_descriptor(),))
    assert registry.resolve("docs/search_documents") == make_search_descriptor()
    for near in ("Docs/search_documents", "docs/Search_documents", " docs/search_documents", "docs/search_documents ", "docs/search", "search_documents", "docs", "", "docs//search_documents"):
        assert registry.resolve(near) is None


def test_a_tool_registered_twice_is_refused():
    with pytest.raises(ValidationError):
        ToolRegistry(tools=(make_search_descriptor(), make_search_descriptor(read_only=False)))


def test_the_same_tool_name_under_two_providers_is_two_tools():
    registry = ToolRegistry(tools=(make_search_descriptor(provider_id="a"), make_search_descriptor(provider_id="b")))
    assert registry.resolve("a/search_documents") is not None and registry.resolve("b/search_documents") is not None


def test_a_tool_may_only_serve_a_capability_that_already_exists():
    # D-203 ruling 7: no new capability; the V0.4 set is closed (D-132).
    with pytest.raises(ValidationError):
        ToolRegistry(tools=(make_search_descriptor(capability=CapabilityId("retrieval")),))


def test_for_capability_is_ordered_by_tool_id_whatever_order_the_tools_were_listed_in():
    tools = (other_tool(), make_search_descriptor(provider_id="zeta"), make_search_descriptor(provider_id="alpha"))
    forward = ToolRegistry(tools=tools).for_capability(RESEARCH)
    backward = ToolRegistry(tools=tuple(reversed(tools))).for_capability(RESEARCH)
    assert [tool.tool_id for tool in forward] == ["alpha/search_documents", "wiki/lookup", "zeta/search_documents"]
    assert forward == backward


def test_for_capability_returns_only_that_capabilitys_tools_and_an_empty_tuple_when_none():
    registry = ToolRegistry(tools=(make_search_descriptor(), other_tool(capability=CapabilityId("cost"))))
    assert [tool.tool_id for tool in registry.for_capability(RESEARCH)] == ["docs/search_documents"]
    assert registry.for_capability(CapabilityId("security")) == ()


def test_an_empty_registry_is_valid_and_resolves_nothing():
    assert ToolRegistry(tools=()).resolve("docs/search_documents") is None


def test_the_registry_round_trips_and_is_immutable():
    registry = ToolRegistry(tools=(make_search_descriptor(), other_tool()))
    assert ToolRegistry.model_validate_json(registry.model_dump_json()) == registry
    with pytest.raises(ValidationError):
        registry.tools = ()
