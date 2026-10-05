"""Reference-group selection and quantile boundary interpolation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .config import REGION_FALLBACKS
from .errors import ErrorCode, QuantileCalculationError
from .models import MeasureType, ReferenceRecord, SelectionInfo


def select_reference_group(
    records: Sequence[ReferenceRecord],
    *,
    measure_type: MeasureType,
    sex: str,
    age: int,
    region: str | None,
) -> tuple[ReferenceRecord | None, SelectionInfo]:
    """Select one sex/age-matched reference row using metric region policy."""
    candidates = [
        record
        for record in records
        if record.measure_type == measure_type
        and record.sex == sex
        and record.age_min <= age <= record.age_max
    ]
    if not candidates:
        return None, SelectionInfo(region, None, False, "일치하는 참조집단이 없습니다.")

    if measure_type == "bmi":
        selected = next((record for record in candidates if record.region in REGION_FALLBACKS), candidates[0])
        return selected, SelectionInfo(region, selected.region, False, "BMI 정책 지역을 사용했습니다.")

    if region is not None:
        selected = next((record for record in candidates if record.region == region), None)
        if selected is not None:
            return selected, SelectionInfo(region, selected.region, False, "요청 지역과 일치하는 집단을 사용했습니다.")

    for fallback_region in REGION_FALLBACKS:
        selected = next((record for record in candidates if record.region == fallback_region), None)
        if selected is not None:
            return selected, SelectionInfo(region, selected.region, True, "요청 지역이 없어 fallback 정책을 사용했습니다.")

    return None, SelectionInfo(region, None, False, "사용 가능한 fallback 참조집단이 없습니다.")


def percentile_position(
    value: float,
    boundaries: Mapping[float, float],
) -> float:
    """Return a measurement's position among percentile reference boundaries.

    Boundaries are supplied as ``percentile -> reference value``. Percentiles
    are considered in ascending order; exact boundary matches return the
    boundary's percentile, while values between distinct adjacent boundaries
    are linearly interpolated. Values outside the reference range are clamped
    to 0 or 100. Duplicate reference values resolve to the lowest percentile
    in the duplicate run.
    """
    if not boundaries:
        raise QuantileCalculationError(
            "참조 분위수 경계가 비어 있습니다.",
            code=ErrorCode.EMPTY_QUANTILE_BOUNDARIES,
        )

    try:
        numeric_value = float(value)
        pairs = sorted(
            (float(percentile), float(reference))
            for percentile, reference in boundaries.items()
        )
    except (TypeError, ValueError) as exc:
        raise QuantileCalculationError(
            "참조 분위수 경계는 숫자여야 합니다.",
            code=ErrorCode.INVALID_QUANTILE_BOUNDARIES,
        ) from exc

    if not math.isfinite(numeric_value) or any(
        not math.isfinite(percentile) or not math.isfinite(reference)
        for percentile, reference in pairs
    ):
        raise QuantileCalculationError(
            "측정값과 참조 분위수 경계는 유한한 숫자여야 합니다.",
            code=ErrorCode.INVALID_QUANTILE_BOUNDARIES,
        )

    if any(
        left_reference > right_reference
        for (_, left_reference), (_, right_reference) in zip(pairs, pairs[1:])
    ):
        raise QuantileCalculationError(
            "참조 분위수 기준값은 오름차순이어야 합니다.",
            code=ErrorCode.INVALID_QUANTILE_BOUNDARIES,
        )

    _, first_reference = pairs[0]
    if numeric_value < first_reference:
        return 0.0

    for (p1, x1), (p2, x2) in zip(pairs, pairs[1:]):
        # Equality is checked before duplicate handling, so a duplicate run
        # always resolves to its first (lowest) percentile.
        if numeric_value == x1:
            return _clamp_percentile(p1)
        if x1 < numeric_value < x2:
            ratio = (numeric_value - x1) / (x2 - x1)
            return _clamp_percentile(p1 + ratio * (p2 - p1))
        if x1 == x2 and numeric_value == x1:
            return _clamp_percentile(p1)

    last_percentile, last_reference = pairs[-1]
    if numeric_value == last_reference:
        return _clamp_percentile(last_percentile)
    return 100.0


def _clamp_percentile(percentile: float) -> float:
    return max(0.0, min(100.0, float(percentile)))


__all__ = ["percentile_position", "select_reference_group"]
