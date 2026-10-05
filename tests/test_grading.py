"""Boundary and interval tests for percentile grading."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings, strategies as st

from src.config import GRADE_BANDS
from src.grading import grade_for_percentile


@pytest.mark.parametrize(
    ("percentile", "expected"),
    [
        (0, (1, "🐣", "가볍게 출발")),
        (20, (2, "🙂", "안정적인 흐름")),
        (40, (3, "😎", "균형 잡힌 구간")),
        (60, (4, "😅", "조금 더 살펴보기")),
        (80, (5, "🚨", "건강 습관 점검")),
        (100, (5, "🚨", "건강 습관 점검")),
    ],
)
def test_explicit_boundary_mapping(
    percentile: float, expected: tuple[int, str, str]
) -> None:
    assert grade_for_percentile(percentile) == expected


@pytest.mark.parametrize(
    ("percentile", "expected_grade"),
    [(10, 1), (30, 2), (50, 3), (70, 4), (90, 5)],
)
def test_each_grade_covers_its_full_interval(
    percentile: float, expected_grade: int
) -> None:
    grade, _emoji, _label = grade_for_percentile(percentile)
    assert grade == expected_grade


@pytest.mark.parametrize("percentile", [-0.001, 100.001, math.nan, math.inf, -math.inf])
def test_out_of_range_percentile_does_not_create_grade_or_message(
    percentile: float,
) -> None:
    with pytest.raises(ValueError, match="0~100"):
        grade_for_percentile(percentile)


@pytest.mark.parametrize("percentile", [None, "not-a-number"])
def test_non_numeric_percentile_is_rejected(percentile: object) -> None:
    with pytest.raises(ValueError, match="0~100"):
        grade_for_percentile(percentile)  # type: ignore[arg-type]


# Feature: fun-obesity-dashboard, Property 7: 등급 함수의 전체성 및 범위 거부
@given(
    percentile=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    boundary=st.sampled_from((0.0, 20.0, 40.0, 60.0, 80.0, 100.0)),
    outside=st.one_of(
        st.floats(min_value=-1_000_000.0, max_value=-0.000001),
        st.floats(min_value=100.000001, max_value=1_000_000.0),
    ),
)
@settings(max_examples=100)
def test_property_7_grade_is_total_at_boundaries_and_rejects_out_of_range(
    percentile: float, boundary: float, outside: float
) -> None:
    """Every valid position has one grade; invalid positions have none.

    **Validates: Requirements 3.1, 3.2, 3.3**
    """
    grade, emoji, label = grade_for_percentile(percentile)
    matching_bands = [
        band
        for index, band in enumerate(GRADE_BANDS)
        if band[0] <= percentile < band[1]
        or (
            index == len(GRADE_BANDS) - 1
            and band[0] <= percentile <= band[1]
        )
    ]
    assert len(matching_bands) == 1
    assert (grade, emoji, label) == matching_bands[0][2:]

    expected_boundary_grade = {
        0.0: 1,
        20.0: 2,
        40.0: 3,
        60.0: 4,
        80.0: 5,
        100.0: 5,
    }[boundary]
    assert grade_for_percentile(boundary)[0] == expected_boundary_grade

    with pytest.raises(ValueError, match="0~100"):
        grade_for_percentile(outside)
