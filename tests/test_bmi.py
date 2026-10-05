"""Examples and property tests for raw BMI calculation and display formatting."""

from __future__ import annotations

import math

from hypothesis import given, settings, strategies as st

from src.bmi import calculate_bmi, format_bmi
from src.quantile import percentile_position



def test_calculate_bmi_uses_weight_divided_by_height_squared() -> None:
    assert calculate_bmi(70.0, 175.0) == 70.0 / (1.75**2)



def test_calculate_bmi_converts_height_from_centimetres_to_metres() -> None:
    assert calculate_bmi(60.0, 160.0) == 60.0 / (1.6**2)



def test_format_bmi_rounds_only_for_display_to_two_decimal_places() -> None:
    assert format_bmi(23.4567) == "23.46"
    assert format_bmi(20.0) == "20.00"



def test_raw_bmi_is_preserved_for_downstream_calculations() -> None:
    raw_bmi = calculate_bmi(65.0, 171.0)

    assert not math.isclose(raw_bmi, float(format_bmi(raw_bmi)))
    assert raw_bmi == 65.0 / (1.71**2)


# Feature: fun-obesity-dashboard, Property 2: BMI 원시 계산과 표시 분리
# Validates: Requirements 2.1, 2.2
@given(
    weight_kg=st.floats(
        min_value=1.0,
        max_value=300.0,
        allow_nan=False,
        allow_infinity=False,
        width=64,
    ),
    height_cm=st.floats(
        min_value=30.0,
        max_value=250.0,
        allow_nan=False,
        allow_infinity=False,
        width=64,
    ),
)
@settings(max_examples=100, deadline=None)
def test_property_raw_bmi_matches_formula_and_display_does_not_change_quantile_input(
    weight_kg: float, height_cm: float
) -> None:
    """Raw BMI remains the quantile input after display formatting."""
    raw_bmi = calculate_bmi(weight_kg, height_cm)
    expected_raw_bmi = weight_kg / ((height_cm / 100.0) ** 2)

    # The quantile calculation uses a raw value, not the formatted string.
    boundaries = {
        1.0: raw_bmi - 1.0,
        50.0: raw_bmi + 1.0,
        99.0: raw_bmi + 2.0,
    }
    raw_percentile = percentile_position(raw_bmi, boundaries)
    expected_percentile = 1.0 + (raw_bmi - (raw_bmi - 1.0)) * (50.0 - 1.0) / 2.0

    displayed_bmi = format_bmi(raw_bmi)

    assert raw_bmi == expected_raw_bmi
    assert math.isclose(raw_percentile, expected_percentile, rel_tol=1e-12)
    assert isinstance(displayed_bmi, str)
    assert raw_bmi == calculate_bmi(weight_kg, height_cm)
    assert percentile_position(raw_bmi, boundaries) == raw_percentile
