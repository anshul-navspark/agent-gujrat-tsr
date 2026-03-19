"""Tests for the type configuration registry."""

import pytest
from tsr_generator.extractors.type_configs import TYPE_CONFIGS, get_config_for_types


# All 19 canonical types that must be present
ALL_TYPES = [
    "SALE", "INHERITANCE", "PARTITION", "RELINQUISHMENT", "EXCHANGE",
    "LIFETIME_DISTRIBUTION", "GIFT", "LOAN", "RELEASE", "SEIZURE",
    "ORDER", "ALLOTMENT", "TENURE_CHANGE", "LAND_ACQUISITION", "LEASE",
    "PROMULGATION", "CORRECTION", "NOT_RELATED", "UNAVAILABLE",
]

FIXED_TEXT_TYPES = {"NOT_RELATED", "UNAVAILABLE"}


class TestTypeConfigsCompleteness:
    """All 19 types must have configs."""

    def test_all_19_types_present(self):
        for t in ALL_TYPES:
            assert t in TYPE_CONFIGS, f"Missing config for type: {t}"

    def test_exactly_19_types(self):
        assert len(TYPE_CONFIGS) == 19


class TestConfigStructure:
    """Each config has required keys: fields, template, examples."""

    @pytest.mark.parametrize("type_name", ALL_TYPES)
    def test_required_keys(self, type_name):
        config = TYPE_CONFIGS[type_name]
        assert "fields" in config, f"{type_name} missing 'fields'"
        assert "template" in config, f"{type_name} missing 'template'"
        assert "examples" in config, f"{type_name} missing 'examples'"

    @pytest.mark.parametrize("type_name", ALL_TYPES)
    def test_fields_is_dict(self, type_name):
        assert isinstance(TYPE_CONFIGS[type_name]["fields"], dict)

    @pytest.mark.parametrize("type_name", ALL_TYPES)
    def test_template_is_string(self, type_name):
        assert isinstance(TYPE_CONFIGS[type_name]["template"], str)
        assert len(TYPE_CONFIGS[type_name]["template"]) > 0

    @pytest.mark.parametrize("type_name", ALL_TYPES)
    def test_examples_is_list(self, type_name):
        assert isinstance(TYPE_CONFIGS[type_name]["examples"], list)


class TestFixedTextTypes:
    """Fixed-text types have empty fields."""

    @pytest.mark.parametrize("type_name", sorted(FIXED_TEXT_TYPES))
    def test_empty_fields(self, type_name):
        assert TYPE_CONFIGS[type_name]["fields"] == {}

    @pytest.mark.parametrize("type_name", sorted(FIXED_TEXT_TYPES))
    def test_empty_examples(self, type_name):
        assert TYPE_CONFIGS[type_name]["examples"] == []


class TestNonFixedTypes:
    """Non-fixed types have at least 1 example."""

    NON_FIXED = sorted(set(ALL_TYPES) - FIXED_TEXT_TYPES)

    @pytest.mark.parametrize("type_name", NON_FIXED)
    def test_has_at_least_one_example(self, type_name):
        examples = TYPE_CONFIGS[type_name]["examples"]
        assert len(examples) >= 1, f"{type_name} needs at least 1 example"

    @pytest.mark.parametrize("type_name", NON_FIXED)
    def test_example_structure(self, type_name):
        for i, ex in enumerate(TYPE_CONFIGS[type_name]["examples"]):
            assert "input" in ex, f"{type_name} example {i} missing 'input'"
            assert "output" in ex, f"{type_name} example {i} missing 'output'"
            assert isinstance(ex["input"], str)
            assert isinstance(ex["output"], dict)


class TestSaleConfig:
    """SALE config has expected fields."""

    def test_sale_fields(self):
        fields = TYPE_CONFIGS["SALE"]["fields"]
        expected = {
            "sellers", "buyers", "survey_numbers", "area",
            "consideration_amount", "document_number", "document_date",
        }
        assert set(fields.keys()) == expected

    def test_sale_has_two_examples(self):
        assert len(TYPE_CONFIGS["SALE"]["examples"]) >= 2


class TestGetConfigForTypes:
    """get_config_for_types filters correctly."""

    def test_returns_requested_types_only(self):
        result = get_config_for_types(["SALE", "LOAN"])
        assert set(result.keys()) == {"SALE", "LOAN"}

    def test_skips_unknown_types(self):
        result = get_config_for_types(["SALE", "NONEXISTENT"])
        assert set(result.keys()) == {"SALE"}

    def test_empty_input(self):
        result = get_config_for_types([])
        assert result == {}

    def test_all_types(self):
        result = get_config_for_types(ALL_TYPES)
        assert len(result) == 19

    def test_returns_same_config_objects(self):
        result = get_config_for_types(["SALE"])
        assert result["SALE"] is TYPE_CONFIGS["SALE"]
