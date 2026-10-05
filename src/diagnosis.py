"""Assemble independent BMI and waist diagnostic results."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .bmi import calculate_bmi
from .config import RANDOM_SEED
from .errors import ErrorCode
from .grading import grade_for_percentile
from .models import (
    DiagnosticResult,
    MetricResult,
    ReferenceRecord,
    SelectionInfo,
    ValidatedInput,
)
from .quantile import percentile_position, select_reference_group

try:  # The message catalog is added independently of the calculation service.
    from .messages import choose_message as _catalog_choose_message
except ImportError:  # pragma: no cover - exercised until the catalog is present
    _catalog_choose_message = None


_DEFAULT_MESSAGES: dict[tuple[str, int], str] = {
    ("bmi", grade): f"BMI 참조 위치를 차분히 확인해 보세요 ({grade}단계)."
    for grade in range(1, 6)
}
_DEFAULT_MESSAGES.update(
    {
        ("waist", grade): f"허리둘레 참조 위치를 차분히 확인해 보세요 ({grade}단계)."
        for grade in range(1, 6)
    }
)


def _message_for(measure_type: str, grade: int, seed: int) -> str:
    """Get a deterministic catalog message without coupling calculation to UI."""
    if _catalog_choose_message is not None:
        return _catalog_choose_message(measure_type, grade, seed=seed)  # type: ignore[arg-type]
    return _DEFAULT_MESSAGES[(measure_type, grade)]


def _unavailable(
    measure_type: str,
    raw_value: float,
    error: str,
    selection: SelectionInfo | None = None,
) -> MetricResult:
    return MetricResult.unavailable(
        measure_type,  # type: ignore[arg-type]
        raw_value,
        error,
        reference_region=selection.selected_region if selection else None,
        used_fallback=selection.used_fallback if selection else False,
        selection_info=selection,
    )


def _build_metric(
    measure_type: str,
    raw_value: float,
    records: Sequence[ReferenceRecord],
    user: ValidatedInput,
    *,
    seed: int,
) -> MetricResult:
    """Calculate one metric; all failures remain local to this metric."""
    selection: SelectionInfo | None = None
    try:
        reference, selection = select_reference_group(
            records,
            measure_type=measure_type,  # type: ignore[arg-type]
            sex=user.sex,
            age=user.age,
            region=user.region,
        )
        if reference is None:
            return _unavailable(
                measure_type,
                raw_value,
                ErrorCode.REFERENCE_GROUP_NOT_FOUND.value,
                selection,
            )

        percentile = percentile_position(raw_value, reference.quantiles)
        grade, emoji, label = grade_for_percentile(percentile)
        message = _message_for(measure_type, grade, seed)
        return MetricResult.calculated(
            measure_type,  # type: ignore[arg-type]
            raw_value,
            percentile,
            grade,
            emoji,
            label,
            message,
            reference_region=selection.selected_region,
            used_fallback=selection.used_fallback,
            selection_info=selection,
        )
    except Exception as exc:  # isolate malformed data/catalog errors per metric
        error = getattr(exc, "code", None) or ErrorCode.INVALID_QUANTILE_BOUNDARIES.value
        return _unavailable(measure_type, raw_value, str(error), selection)


def build_bmi_metric(
    user: ValidatedInput,
    records: Sequence[ReferenceRecord],
    *,
    seed: int = RANDOM_SEED,
) -> MetricResult:
    """Build the BMI result independently from the waist result."""
    try:
        raw_value = calculate_bmi(user.weight_kg, user.height_cm)
        if not math.isfinite(raw_value):
            raise ValueError("BMI 계산 결과가 유한하지 않습니다.")
    except Exception as exc:
        return _unavailable(
            "bmi",
            float("nan"),
            str(getattr(exc, "code", None) or ErrorCode.INVALID_NUMBER.value),
        )
    return _build_metric("bmi", raw_value, records, user, seed=seed)


def build_waist_metric(
    user: ValidatedInput,
    records: Sequence[ReferenceRecord],
    *,
    seed: int = RANDOM_SEED,
) -> MetricResult:
    """Build the waist result independently from the BMI result."""
    try:
        raw_value = float(user.waist_cm)
        if not math.isfinite(raw_value):
            raise ValueError("허리둘레 계산 결과가 유한하지 않습니다.")
    except Exception as exc:
        return _unavailable(
            "waist",
            float("nan"),
            str(getattr(exc, "code", None) or ErrorCode.INVALID_NUMBER.value),
        )
    return _build_metric("waist", raw_value, records, user, seed=seed)


def build_diagnostic(
    user: ValidatedInput,
    records: Sequence[ReferenceRecord],
    *,
    seed: int = RANDOM_SEED,
) -> DiagnosticResult:
    """Return independent BMI and waist results with the common disclaimer."""
    # Do not share mutable state or short-circuit: either metric may succeed.
    bmi = build_bmi_metric(user, records, seed=seed)
    waist = build_waist_metric(user, records, seed=seed)
    return DiagnosticResult(bmi=bmi, waist=waist)


__all__ = [
    "build_bmi_metric",
    "build_diagnostic",
    "build_waist_metric",
]
