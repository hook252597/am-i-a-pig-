"""Examples for diagnosis input validation."""

from __future__ import annotations

import math

import pytest

from src.validation import validate_input


@pytest.fixture
def valid_input() -> dict[str, object]:
    return {
        "sex": "남",
        "age": 40,
        "height_cm": 170.5,
        "weight_kg": 65.25,
        "waist_cm": 80.0,
        "region": "전국",
    }


def test_inclusive_boundaries_are_accepted() -> None:
    for field, value in {
        "age": 0,
        "height_cm": 30,
        "weight_kg": 1,
        "waist_cm": 20,
    }.items():
        raw = {"sex": "여", "age": 40, "height_cm": 170, "weight_kg": 60, "waist_cm": 80}
        raw[field] = value
        result, errors = validate_input(raw)
        assert errors == []
        assert result is not None
        assert getattr(result, field) == float(value) if field != "age" else result.age == value

    raw = {"sex": "여", "age": 120, "height_cm": 250, "weight_kg": 300, "waist_cm": 200}
    result, errors = validate_input(raw)
    assert errors == []
    assert result is not None
    assert (result.age, result.height_cm, result.weight_kg, result.waist_cm) == (120, 250.0, 300.0, 200.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("age", 121),
        ("height_cm", 250.0001),
        ("weight_kg", 300.0001),
        ("waist_cm", 200.0001),
        ("height_cm", 29.9999),
        ("weight_kg", 0.9999),
        ("waist_cm", 19.9999),
    ],
)
def test_adjacent_out_of_range_values_return_field_error(
    valid_input: dict[str, object], field: str, value: object
) -> None:
    valid_input[field] = value
    result, errors = validate_input(valid_input)
    assert result is None
    assert [(error.field, error.code) for error in errors] == [(field, "OUT_OF_RANGE")]
    assert field in errors[0].message


def test_age_requires_an_integer(valid_input: dict[str, object]) -> None:
    valid_input["age"] = 40.0
    result, errors = validate_input(valid_input)
    assert result is None
    assert [(error.field, error.code) for error in errors] == [("age", "INVALID_NUMBER")]


@pytest.mark.parametrize("field", ["sex", "age", "height_cm", "weight_kg", "waist_cm"])
def test_missing_required_field_returns_only_that_field_error(
    valid_input: dict[str, object], field: str
) -> None:
    del valid_input[field]
    result, errors = validate_input(valid_input)
    assert result is None
    assert [(error.field, error.code) for error in errors] == [(field, "REQUIRED")]


@pytest.mark.parametrize("value", ["not-a-number", object(), True])
def test_non_numeric_measurement_is_rejected(
    valid_input: dict[str, object], value: object
) -> None:
    valid_input["weight_kg"] = value
    result, errors = validate_input(valid_input)
    assert result is None
    assert [(error.field, error.code) for error in errors] == [("weight_kg", "INVALID_NUMBER")]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nan_and_infinite_values_are_rejected(
    valid_input: dict[str, object], value: float
) -> None:
    valid_input["height_cm"] = value
    result, errors = validate_input(valid_input)
    assert result is None
    assert [(error.field, error.code) for error in errors] == [("height_cm", "INVALID_NUMBER")]


def test_region_none_is_forwarded_without_error(valid_input: dict[str, object]) -> None:
    valid_input["region"] = None
    result, errors = validate_input(valid_input)
    assert errors == []
    assert result is not None
    assert result.region is None


def test_errors_are_isolated_and_valid_fields_are_normalized(
    valid_input: dict[str, object],
) -> None:
    valid_input.update({"age": 121, "weight_kg": "bad"})
    result, errors = validate_input(valid_input)
    assert result is None
    assert {(error.field, error.code) for error in errors} == {
        ("age", "OUT_OF_RANGE"),
        ("weight_kg", "INVALID_NUMBER"),
    }

    corrected = dict(valid_input, age=40, weight_kg=65)
    normalized, corrected_errors = validate_input(corrected)
    assert corrected_errors == []
    assert normalized is not None
    assert normalized.height_cm == 170.5
    assert normalized.waist_cm == 80.0
    assert normalized.weight_kg == 65.0


def test_same_input_is_idempotent(valid_input: dict[str, object]) -> None:
    assert validate_input(valid_input) == validate_input(valid_input)


# Feature: fun-obesity-dashboard, Property 1: 입력 검증과 표준화의 불변식
# Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.8
from hypothesis import given, settings, strategies as st


_VALID_FIELD_STRATEGIES = {
    "age": st.integers(min_value=0, max_value=120),
    "height_cm": st.floats(min_value=30, max_value=250, allow_nan=False, allow_infinity=False),
    "weight_kg": st.floats(min_value=1, max_value=300, allow_nan=False, allow_infinity=False),
    "waist_cm": st.floats(min_value=20, max_value=200, allow_nan=False, allow_infinity=False),
}


def _valid_raw_inputs() -> st.SearchStrategy[dict[str, object]]:
    """Generate complete, valid raw inputs across every accepted range."""
    return st.fixed_dictionaries(
        {
            "sex": st.sampled_from(["남", "여"]),
            "age": _VALID_FIELD_STRATEGIES["age"],
            "height_cm": _VALID_FIELD_STRATEGIES["height_cm"],
            "weight_kg": _VALID_FIELD_STRATEGIES["weight_kg"],
            "waist_cm": _VALID_FIELD_STRATEGIES["waist_cm"],
            "region": st.one_of(st.none(), st.sampled_from(["전국", "서울"])),
        }
    )


def _invalid_value(field: str) -> st.SearchStrategy[object]:
    """Generate representative invalid values for one validation field."""
    if field == "sex":
        return st.one_of(st.none(), st.just(""), st.integers(), st.booleans())
    if field == "age":
        return st.one_of(
            st.integers(min_value=-1000, max_value=-1),
            st.integers(min_value=121, max_value=1000),
            st.sampled_from([math.nan, math.inf, -math.inf]),
            st.just("40"),
            st.just(True),
        )
    minimum, maximum = {"height_cm": (30, 250), "weight_kg": (1, 300), "waist_cm": (20, 200)}[field]
    return st.one_of(
        st.floats(min_value=-1000, max_value=minimum, exclude_max=True),
        st.floats(min_value=maximum, max_value=1000, exclude_min=True),
        st.sampled_from([math.nan, math.inf, -math.inf]),
        st.sampled_from(["not-a-number", "", True, object()]),
    )


@given(_valid_raw_inputs())
@settings(max_examples=100)
def test_property_1_accepts_valid_ranges_and_normalizes(raw: dict[str, object]) -> None:
    """All inclusive valid ranges are accepted and normalized deterministically."""
    result, errors = validate_input(raw)

    assert errors == []
    assert result is not None
    assert result.sex == raw["sex"]
    assert result.age == raw["age"]
    assert result.height_cm == float(raw["height_cm"])
    assert result.weight_kg == float(raw["weight_kg"])
    assert result.waist_cm == float(raw["waist_cm"])
    assert result.region == raw["region"]


@given(
    st.data(),
    st.sampled_from(["sex", "age", "height_cm", "weight_kg", "waist_cm"]),
    _valid_raw_inputs(),
)
@settings(max_examples=100)
def test_property_1_invalid_field_blocks_calculation_without_affecting_valid_fields(
    data: st.DataObject, field: str, raw: dict[str, object]
) -> None:
    """An invalid field prevents normalized output and reports only that field."""
    raw[field] = data.draw(_invalid_value(field), label=f"invalid {field}")
    result, errors = validate_input(raw)

    assert result is None
    assert errors
    assert {error.field for error in errors} == {field}


@given(
    st.data(),
    st.sampled_from(["age", "height_cm", "weight_kg", "waist_cm"]),
    _valid_raw_inputs(),
)
@settings(max_examples=100)
def test_property_1_error_isolation_preserves_other_field_errors(
    data: st.DataObject, field: str, raw: dict[str, object]
) -> None:
    """Changing one field cannot add, remove, or alter errors for other fields."""
    changed = dict(raw)
    changed[field] = data.draw(_invalid_value(field), label=f"invalid {field}")
    _, errors = validate_input(changed)
    error_by_field = {error.field: error for error in errors}

    assert set(error_by_field) == {field}
    for other_field in ("age", "height_cm", "weight_kg", "waist_cm"):
        if other_field != field:
            assert other_field not in error_by_field


@given(_valid_raw_inputs())
@settings(max_examples=100)
def test_property_1_repeated_validation_is_idempotent(raw: dict[str, object]) -> None:
    """Repeated validation returns equal normalized output and errors."""
    first = validate_input(raw)
    second = validate_input(dict(raw))

    assert second == first
