from __future__ import annotations

from src.config import DISCLAIMER
from src.diagnosis import build_diagnostic
from src.models import ReferenceRecord, ValidatedInput


def _record(measure_type: str, *, region: str | None = "전국", row: int = 1) -> ReferenceRecord:
    return ReferenceRecord(
        measure_type=measure_type,  # type: ignore[arg-type]
        sex="남성",
        age_min=20,
        age_max=24,
        region=region,
        quantiles={1.0: 10.0, 50.0: 20.0, 99.0: 30.0},
        source="fixture.xlsx",
        source_row=row,
    )


def _user(region: str | None = "서울") -> ValidatedInput:
    return ValidatedInput(
        sex="남성", age=22, height_cm=175.0, weight_kg=70.0, waist_cm=80.0, region=region
    )


def test_build_diagnostic_returns_two_independent_results_and_disclaimer() -> None:
    result = build_diagnostic(_user(), [_record("bmi"), _record("waist", region="서울", row=2)])

    assert result.disclaimer == DISCLAIMER
    assert result.bmi.error is None
    assert result.waist.error is None
    assert result.bmi.raw_value == 70.0 / (1.75**2)
    assert result.waist.raw_value == 80.0
    assert result.bmi.selection_info is not None
    assert result.waist.selection_info is not None
    assert result.waist.selection_info.selected_region == "서울"
    assert result.waist.used_fallback is False


def test_missing_bmi_group_does_not_hide_successful_waist_result() -> None:
    result = build_diagnostic(_user(), [_record("waist", region="서울")])

    assert result.bmi.error == "REFERENCE_GROUP_NOT_FOUND"
    assert result.bmi.percentile is None
    assert result.bmi.grade is None
    assert result.bmi.message is None
    assert result.waist.error is None
    assert result.waist.grade is not None


def test_missing_requested_waist_region_preserves_fallback_metadata() -> None:
    result = build_diagnostic(_user("부산"), [_record("bmi"), _record("waist", region="전국", row=2)])

    assert result.waist.error is None
    assert result.waist.reference_region == "전국"
    assert result.waist.used_fallback is True
    assert result.waist.selection_info is not None
    assert result.waist.selection_info.requested_region == "부산"
    assert result.waist.selection_info.selected_region == "전국"
    assert result.waist.selection_info.used_fallback is True


def test_invalid_waist_boundaries_only_fail_waist_metric() -> None:
    invalid_waist = _record("waist", region="서울", row=2)
    invalid_waist = ReferenceRecord(
        measure_type=invalid_waist.measure_type,
        sex=invalid_waist.sex,
        age_min=invalid_waist.age_min,
        age_max=invalid_waist.age_max,
        region=invalid_waist.region,
        quantiles={},
        source=invalid_waist.source,
        source_row=invalid_waist.source_row,
    )
    result = build_diagnostic(_user(), [_record("bmi"), invalid_waist])

    assert result.bmi.error is None
    assert result.bmi.percentile is not None
    assert result.waist.error == "EMPTY_QUANTILE_BOUNDARIES"
    assert result.waist.percentile is None
    assert result.waist.grade is None
    assert result.waist.message is None


from hypothesis import given, settings, strategies as st


@st.composite
def _diagnosis_isolation_cases(draw: st.DrawFn) -> tuple[ValidatedInput, list[ReferenceRecord], str]:
    """Generate a valid user and one reference row for each independent metric."""
    height_cm = draw(st.floats(min_value=150.0, max_value=200.0, allow_nan=False, allow_infinity=False))
    weight_kg = draw(st.floats(min_value=45.0, max_value=120.0, allow_nan=False, allow_infinity=False))
    waist_cm = draw(st.floats(min_value=55.0, max_value=130.0, allow_nan=False, allow_infinity=False))
    user = ValidatedInput(
        sex="남성",
        age=22,
        height_cm=height_cm,
        weight_kg=weight_kg,
        waist_cm=waist_cm,
        region="서울",
    )

    bmi_value = weight_kg / ((height_cm / 100.0) ** 2)
    percentiles = (1.0, 25.0, 50.0, 75.0, 99.0)
    offsets = draw(
        st.lists(
            st.floats(min_value=0.1, max_value=20.0, allow_nan=False, allow_infinity=False),
            min_size=4,
            max_size=4,
            unique=True,
        ).map(sorted)
    )

    def boundaries(value: float) -> dict[float, float]:
        distances = (-offsets[3], -offsets[2], 0.0, offsets[0], offsets[1])
        return {percentile: value + distance for percentile, distance in zip(percentiles, distances)}

    records = [
        ReferenceRecord(
            measure_type="bmi",
            sex="남성",
            age_min=20,
            age_max=24,
            region="전국",
            quantiles=boundaries(bmi_value),
            source="generated.xlsx",
            source_row=1,
        ),
        ReferenceRecord(
            measure_type="waist",
            sex="남성",
            age_min=20,
            age_max=24,
            region="서울",
            quantiles=boundaries(waist_cm),
            source="generated.xlsx",
            source_row=2,
        ),
    ]
    changed_metric = draw(st.sampled_from(["bmi", "waist"]))
    return user, records, changed_metric


# Feature: fun-obesity-dashboard, Property 6: 지표 독립성과 부분 실패 격리
# Validates: Requirements 2.9, 2.10, 3.7, 5.4
@given(_diagnosis_isolation_cases())
@settings(max_examples=100)
def test_property_6_metric_changes_and_failures_are_isolated(
    case: tuple[ValidatedInput, list[ReferenceRecord], str],
) -> None:
    """한 지표의 참조값 변경 또는 실패가 다른 지표 결과를 바꾸지 않는다."""
    user, records, changed_metric = case
    baseline = build_diagnostic(user, records)

    changed_record = records[0 if changed_metric == "bmi" else 1]
    changed_quantiles = {
        percentile: value + 1_000.0
        for percentile, value in changed_record.quantiles.items()
    }
    changed_record = ReferenceRecord(
        measure_type=changed_record.measure_type,
        sex=changed_record.sex,
        age_min=changed_record.age_min,
        age_max=changed_record.age_max,
        region=changed_record.region,
        quantiles=changed_quantiles,
        source=changed_record.source,
        source_row=changed_record.source_row,
    )
    changed_records = [
        changed_record if record.measure_type == changed_metric else record
        for record in records
    ]
    changed = build_diagnostic(user, changed_records)

    failed_records = [record for record in records if record.measure_type != changed_metric]
    failed = build_diagnostic(user, failed_records)

    untouched = "waist" if changed_metric == "bmi" else "bmi"
    baseline_metric = getattr(baseline, untouched)
    changed_metric_result = getattr(changed, untouched)
    failed_metric_result = getattr(failed, untouched)

    assert changed_metric_result == baseline_metric
    assert failed_metric_result == baseline_metric
    assert changed_metric_result.raw_value == baseline_metric.raw_value
    assert changed_metric_result.grade == baseline_metric.grade
    assert changed_metric_result.message == baseline_metric.message
