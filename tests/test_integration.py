from __future__ import annotations

from hypothesis import given, settings, strategies as st

from src.diagnosis import build_diagnostic
from src.models import ReferenceRecord
from src.validation import validate_input
from src.visualization import metric_bar, percentile_gauge


_PERCENTILES = (1.0, 25.0, 50.0, 75.0, 99.0)


@st.composite
def _property_14_cases(draw: st.DrawFn) -> tuple[dict[str, object], list[ReferenceRecord], str]:
    """Generate one valid flow and an invalid-input variant for each run."""
    raw: dict[str, object] = {
        "sex": draw(st.sampled_from(("남성", "여성"))),
        "age": draw(st.integers(min_value=0, max_value=120)),
        "height_cm": draw(
            st.floats(min_value=150.0, max_value=200.0, allow_nan=False, allow_infinity=False)
        ),
        "weight_kg": draw(
            st.floats(min_value=45.0, max_value=120.0, allow_nan=False, allow_infinity=False)
        ),
        "waist_cm": draw(
            st.floats(min_value=55.0, max_value=130.0, allow_nan=False, allow_infinity=False)
        ),
        "region": draw(st.sampled_from((None, "서울", "부산"))),
    }

    height_cm = float(raw["height_cm"])
    weight_kg = float(raw["weight_kg"])
    waist_cm = float(raw["waist_cm"])
    bmi = weight_kg / ((height_cm / 100.0) ** 2)

    def boundaries(value: float) -> dict[float, float]:
        offsets = (-20.0, -10.0, 0.0, 10.0, 20.0)
        return {
            percentile: value + offset
            for percentile, offset in zip(_PERCENTILES, offsets)
        }

    records = [
        ReferenceRecord(
            measure_type="bmi",
            sex=str(raw["sex"]),
            age_min=0,
            age_max=120,
            region="전국",
            quantiles=boundaries(bmi),
            source="property14.xlsx",
            source_row=1,
        ),
        ReferenceRecord(
            measure_type="waist",
            sex=str(raw["sex"]),
            age_min=0,
            age_max=120,
            region="전국",
            quantiles=boundaries(waist_cm),
            source="property14.xlsx",
            source_row=2,
        ),
    ]

    invalid_field = draw(st.sampled_from(("age", "height_cm", "weight_kg", "waist_cm")))
    invalid_values: dict[str, object] = {
        "age": 121,
        "height_cm": 250.1,
        "weight_kg": 300.1,
        "waist_cm": 200.1,
    }
    invalid_raw = dict(raw)
    invalid_raw[invalid_field] = invalid_values[invalid_field]
    return invalid_raw, records, invalid_field


# Feature: fun-obesity-dashboard, Property 14: 통합 실패 우선성·순서 안정성·부분 실패 격리
# Validates: Requirements 7.11, 7.12, 7.13
@given(_property_14_cases())
@settings(max_examples=100, deadline=None)
def test_property_14_integration_flow_preserves_failure_and_order_policies(
    case: tuple[dict[str, object], list[ReferenceRecord], str],
) -> None:
    """입력 차단, 순서 불변성, partial metric 결과를 함께 검증한다."""
    invalid_raw, records, invalid_field = case

    # Invalid input is rejected at the validation boundary, so no validated
    # payload can reach build_diagnostic or produce a diagnosis visualization.
    validated, errors = validate_input(invalid_raw)
    assert validated is None
    assert any(error.field == invalid_field for error in errors)

    valid_raw = dict(invalid_raw)
    valid_raw[invalid_field] = {
        "age": 22,
        "height_cm": 175.0,
        "weight_kg": 70.0,
        "waist_cm": 80.0,
    }[invalid_field]
    valid_input, valid_errors = validate_input(valid_raw)
    assert valid_input is not None
    assert valid_errors == []

    # Reordering the input mapping and reference rows must not change the
    # normalized input or either metric result.
    reordered_input, reordered_errors = validate_input(
        dict(reversed(list(valid_raw.items())))
    )
    assert reordered_errors == []
    assert reordered_input == valid_input
    baseline = build_diagnostic(valid_input, records)
    reordered = build_diagnostic(reordered_input, list(reversed(records)))
    assert reordered == baseline

    # Removing one reference metric produces a local failure while preserving
    # the other metric and its rendered numeric visualization.
    failed_metric = "bmi" if invalid_field in ("age", "height_cm") else "waist"
    successful_metric = "waist" if failed_metric == "bmi" else "bmi"
    partial_records = [
        record for record in records if record.measure_type != failed_metric
    ]
    partial = build_diagnostic(valid_input, partial_records)
    failed_result = getattr(partial, failed_metric)
    successful_result = getattr(partial, successful_metric)
    baseline_success = getattr(baseline, successful_metric)

    assert failed_result.error is not None
    assert failed_result.percentile is None
    assert failed_result.grade is None
    assert failed_result.message is None
    assert successful_result == baseline_success
    assert len(metric_bar(failed_result).data) == 0
    assert len(percentile_gauge(failed_result).data) == 0
    assert len(metric_bar(successful_result).data) == 1
    assert len(percentile_gauge(successful_result).data) == 1
