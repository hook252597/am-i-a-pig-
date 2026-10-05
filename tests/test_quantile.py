from __future__ import annotations

import pytest

from src.models import ReferenceRecord
from src.quantile import select_reference_group


def _record(
    measure_type: str = "waist",
    *,
    region: str | None = "전국",
    sex: str = "남성",
    age_min: int = 20,
    age_max: int = 24,
    row: int = 1,
) -> ReferenceRecord:
    return ReferenceRecord(
        measure_type=measure_type,  # type: ignore[arg-type]
        sex=sex,
        age_min=age_min,
        age_max=age_max,
        region=region,
        quantiles={1.0: 70.0, 50.0: 80.0, 99.0: 100.0},
        source="fixture.xlsx",
        source_row=row,
    )


def test_age_range_includes_both_endpoints() -> None:
    records = [_record(age_min=20, age_max=24)]

    first, first_info = select_reference_group(
        records, measure_type="waist", sex="남성", age=20, region="서울"
    )
    last, last_info = select_reference_group(
        records, measure_type="waist", sex="남성", age=24, region="서울"
    )

    assert first is records[0]
    assert last is records[0]
    assert first_info.selected_region == "전국"
    assert last_info.selected_region == "전국"


def test_waist_requested_region_has_priority_over_fallbacks() -> None:
    records = [
        _record(region="전국", row=1),
        _record(region="서울", row=2),
        _record(region="미지정", row=3),
    ]

    selected, info = select_reference_group(
        records, measure_type="waist", sex="남성", age=22, region="서울"
    )

    assert selected is records[1]
    assert info.requested_region == "서울"
    assert info.selected_region == "서울"
    assert info.used_fallback is False
    assert "일치" in (info.reason or "")


@pytest.mark.parametrize(
    ("available_regions", "expected"),
    [
        (["전국", "미지정", None, ""], "전국"),
        (["미지정", None, ""], "미지정"),
        ([None, ""], None),
        ([""], ""),
    ],
)
def test_waist_fallback_follows_configured_order(
    available_regions: list[str | None], expected: str | None
) -> None:
    records = [
        _record(region=region, row=index)
        for index, region in enumerate(available_regions, start=1)
    ]

    selected, info = select_reference_group(
        records, measure_type="waist", sex="남성", age=22, region="부산"
    )

    assert (selected.region if selected else None) == expected
    assert info.requested_region == "부산"
    assert info.used_fallback is (selected is not None)
    if selected is not None:
        assert "fallback" in (info.reason or "") or "정책" in (info.reason or "")


def test_no_matching_sex_or_age_returns_selection_failure() -> None:
    records = [_record(sex="여성"), _record(age_min=30, age_max=34, row=2)]

    selected, info = select_reference_group(
        records, measure_type="waist", sex="남성", age=22, region="서울"
    )

    assert selected is None
    assert info.selected_region is None
    assert info.used_fallback is False
    assert "없습니다" in (info.reason or "")


def test_bmi_uses_policy_region_independently_of_requested_waist_region() -> None:
    records = [
        _record("bmi", region="전국", row=1),
        _record("bmi", region="서울", row=2),
        _record("waist", region="서울", row=3),
    ]

    bmi, bmi_info = select_reference_group(
        records, measure_type="bmi", sex="남성", age=22, region="서울"
    )
    waist, waist_info = select_reference_group(
        records, measure_type="waist", sex="남성", age=22, region="서울"
    )

    assert bmi is records[0]
    assert bmi_info.requested_region == "서울"
    assert bmi_info.selected_region == "전국"
    assert bmi_info.used_fallback is False
    assert waist is records[2]
    assert waist_info.selected_region == "서울"
    assert waist_info.used_fallback is False


from pathlib import Path

import pandas as pd

from src.data_loader import load_reference_data
from src.errors import QuantileCalculationError
from src.quantile import percentile_position


def test_percentile_position_returns_matching_boundary_percentile() -> None:
    boundaries = {10.0: 10.0, 50.0: 20.0, 90.0: 30.0}

    assert percentile_position(10.0, boundaries) == 10.0
    assert percentile_position(20.0, boundaries) == 50.0
    assert percentile_position(30.0, boundaries) == 90.0


def test_percentile_position_linearly_interpolates_between_boundaries() -> None:
    boundaries = {10.0: 10.0, 50.0: 20.0}

    assert percentile_position(15.0, boundaries) == pytest.approx(30.0)


def test_percentile_position_clamps_values_outside_reference_range() -> None:
    boundaries = {10.0: 10.0, 50.0: 20.0, 90.0: 30.0}

    assert percentile_position(9.9, boundaries) == 0.0
    assert percentile_position(30.1, boundaries) == 100.0


def test_percentile_position_uses_lowest_percentile_for_duplicate_boundary() -> None:
    boundaries = {10.0: 10.0, 50.0: 10.0, 90.0: 20.0}

    assert percentile_position(10.0, boundaries) == 10.0


def test_percentile_position_rejects_empty_boundaries() -> None:
    with pytest.raises(QuantileCalculationError) as exc_info:
        percentile_position(10.0, {})

    assert exc_info.value.code == "EMPTY_QUANTILE_BOUNDARIES"


def test_loader_reports_descending_reference_boundaries_as_row_issue(tmp_path: Path) -> None:
    columns = [
        "지역",
        "성별",
        "나이",
        *[f"{percentile}분위수" for percentile in (1, 5, 10, 25, 50, 75, 90, 95, 99)],
    ]
    row = {
        "지역": "전국",
        "성별": "남성",
        "나이": "20~24 세",
        **{column: float(index + 1) for index, column in enumerate(columns[3:])},
    }
    row["50분위수"] = 3.0
    row["75분위수"] = 2.0
    frame = pd.DataFrame([row], columns=columns)
    valid_row = {
        "지역": "전국",
        "성별": "남성",
        "나이": "20~24 세",
        **{column: float(index + 1) for index, column in enumerate(columns[3:])},
    }
    valid_frame = pd.DataFrame([valid_row], columns=columns)
    bmi_path = tmp_path / "bmi.xlsx"
    waist_path = tmp_path / "waist.xlsx"
    frame.to_excel(bmi_path, index=False)
    valid_frame.to_excel(waist_path, index=False)

    records, issues = load_reference_data(bmi_path, waist_path)

    assert len(records) == 1
    assert any(issue.source == "bmi.xlsx" and issue.code == "INVALID_ORDER" for issue in issues)


from hypothesis import given, settings, strategies as st
from hypothesis.strategies import composite


@composite
def _ascending_boundaries(draw: st.DrawFn) -> tuple[float, float, float, float]:
    """Generate two percentile/value boundaries in ascending order."""
    p1 = draw(st.integers(min_value=0, max_value=99))
    p2 = draw(st.integers(min_value=p1 + 1, max_value=100))
    x1 = draw(st.integers(min_value=-10_000, max_value=10_000))
    x2 = draw(st.integers(min_value=x1 + 1, max_value=x1 + 10_000))
    return float(p1), float(p2), float(x1), float(x2)


# Feature: fun-obesity-dashboard, Property 3: 분위수 보간의 정확성과 단조성
# Validates: Requirements 2.4, 2.10
@given(
    boundaries=_ascending_boundaries(),
    lower_ratio=st.integers(min_value=1, max_value=98),
    upper_ratio=st.integers(min_value=2, max_value=99),
)
@settings(max_examples=100)
def test_property_3_interpolation_formula_and_monotonicity(
    boundaries: tuple[float, float, float, float],
    lower_ratio: int,
    upper_ratio: int,
) -> None:
    p1, p2, x1, x2 = boundaries
    if lower_ratio > upper_ratio:
        lower_ratio, upper_ratio = upper_ratio, lower_ratio

    lower_value = x1 + (x2 - x1) * lower_ratio / 100.0
    upper_value = x1 + (x2 - x1) * upper_ratio / 100.0
    reference = {p1: x1, p2: x2}

    lower_result = percentile_position(lower_value, reference)
    upper_result = percentile_position(upper_value, reference)
    expected_lower = p1 + (lower_value - x1) * (p2 - p1) / (x2 - x1)
    expected_upper = p1 + (upper_value - x1) * (p2 - p1) / (x2 - x1)

    assert lower_result == pytest.approx(expected_lower)
    assert upper_result == pytest.approx(expected_upper)
    assert lower_result <= upper_result


# Feature: fun-obesity-dashboard, Property 4: 분위수 범위·외삽·중복 경계 정책
# Validates: Requirements 2.5, 2.6, 3.1
@given(
    boundaries=_ascending_boundaries(),
    below_distance=st.integers(min_value=1, max_value=10_000),
    above_distance=st.integers(min_value=1, max_value=10_000),
    arbitrary_value=st.integers(min_value=-20_000, max_value=20_000),
)
@settings(max_examples=100)
def test_property_4_range_extrapolation_and_duplicate_lowest_percentile(
    boundaries: tuple[float, float, float, float],
    below_distance: int,
    above_distance: int,
    arbitrary_value: int,
) -> None:
    p1, p2, x1, x2 = boundaries
    reference = {p1: x1, p2: x2}

    # Every input remains in the public [0, 100] percentile range.
    result = percentile_position(float(arbitrary_value), reference)
    assert 0.0 <= result <= 100.0

    # Values outside either end are explicitly clamped.
    assert percentile_position(x1 - below_distance, reference) == 0.0
    assert percentile_position(x2 + above_distance, reference) == 100.0

    # A duplicate boundary resolves to the lowest percentile in that run.
    duplicate_reference = {p1: x1, p2: x1, 100.0: x2}
    assert percentile_position(x1, duplicate_reference) == p1
    assert 0.0 <= percentile_position(x1, duplicate_reference) <= 100.0


from hypothesis import given, settings, strategies as st

from src.config import REGION_FALLBACKS


@st.composite
def _selection_scenarios(draw: st.DrawFn) -> tuple[
    str, str, int, int, int, str | None, bool, tuple[bool, ...], bool
]:
    """Generate matched candidates plus distractors for Property 5."""
    measure_type = draw(st.sampled_from(["bmi", "waist"]))
    sex = draw(st.sampled_from(["남성", "여성", "기타"]))
    age = draw(st.integers(min_value=0, max_value=120))
    age_min = draw(st.integers(min_value=0, max_value=age))
    age_max = draw(st.integers(min_value=age, max_value=120))
    requested_region = draw(st.one_of(st.none(), st.sampled_from(["서울", "부산", "제주"])))
    requested_available = draw(st.booleans())
    fallback_available = tuple(draw(st.booleans()) for _ in REGION_FALLBACKS)
    return (
        measure_type,
        sex,
        age,
        age_min,
        age_max,
        requested_region,
        requested_available,
        fallback_available,
        draw(st.booleans()),
    )


# Feature: fun-obesity-dashboard, Property 5: 결정적인 집단 선택과 지역 fallback
@given(_selection_scenarios())
@settings(max_examples=100)
def test_selection_is_deterministic_and_respects_region_fallback_policy(
    scenario: tuple[
        str,
        str,
        int,
        int,
        int,
        str | None,
        bool,
        tuple[bool, ...],
        bool,
    ],
) -> None:
    """성별·연령 필터, 지역 우선순위, 상태 기록을 모든 생성 사례에서 검증한다.

    **Validates: Requirements 2.3, 2.7, 2.8, 6.5**
    """
    (
        measure_type,
        sex,
        age,
        age_min,
        age_max,
        requested_region,
        requested_available,
        fallback_available,
        include_distractors,
    ) = scenario

    target_records: list[ReferenceRecord] = []
    if measure_type == "waist" and requested_region is not None and requested_available:
        target_records.append(
            _record(
                measure_type,
                region=requested_region,
                sex=sex,
                age_min=age_min,
                age_max=age_max,
                row=100,
            )
        )
    for row, (region, available) in enumerate(
        zip(REGION_FALLBACKS, fallback_available, strict=True), start=200
    ):
        if available:
            target_records.append(
                _record(
                    measure_type,
                    region=region,
                    sex=sex,
                    age_min=age_min,
                    age_max=age_max,
                    row=row,
                )
            )
    if not target_records:
        target_records.append(
            _record(
                measure_type,
                region="지역외",
                sex=sex,
                age_min=age_min,
                age_max=age_max,
                row=300,
            )
        )

    records = list(target_records)
    if include_distractors:
        records.extend(
            [
                _record(
                    measure_type,
                    region="부산",
                    sex="다른성별",
                    age_min=age_min,
                    age_max=age_max,
                    row=400,
                ),
                _record(
                    measure_type,
                    region="연령외",
                    sex=sex,
                    age_min=min(120, age_max + 1),
                    age_max=120,
                    row=401,
                ),
                _record(
                    "waist" if measure_type == "bmi" else "bmi",
                    region="서울",
                    sex=sex,
                    age_min=age_min,
                    age_max=age_max,
                    row=402,
                ),
            ]
        )

    first, first_info = select_reference_group(
        records,
        measure_type=measure_type,  # type: ignore[arg-type]
        sex=sex,
        age=age,
        region=requested_region,
    )
    second, second_info = select_reference_group(
        records,
        measure_type=measure_type,  # type: ignore[arg-type]
        sex=sex,
        age=age,
        region=requested_region,
    )

    assert first == second
    assert first_info == second_info
    assert first_info.requested_region == requested_region
    if first is not None:
        assert first.sex == sex
        assert first.age_min <= age <= first.age_max

    if measure_type == "waist" and requested_region is not None and requested_available:
        assert first is not None
        assert first.region == requested_region
        assert first_info.selected_region == requested_region
        assert first_info.used_fallback is False
    else:
        expected_region = next(
            (
                fallback_region
                for fallback_region, available in zip(
                    REGION_FALLBACKS, fallback_available, strict=True
                )
                if available
            ),
            None,
        )
        has_fallback = any(fallback_available)
        if measure_type == "bmi":
            assert first is not None
            assert first.region == expected_region or (
                expected_region is None and first.region == "지역외"
            )
            assert first_info.used_fallback is False
        elif not has_fallback:
            assert first is None
            assert first_info.selected_region is None
            assert first_info.used_fallback is False
        else:
            assert first is not None
            assert first.region == expected_region
            assert first_info.selected_region == expected_region
            assert first_info.used_fallback is True
            assert "fallback" in (first_info.reason or "")
