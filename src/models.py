"""Immutable data contracts shared by the dashboard services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

MeasureType = Literal["bmi", "waist"]

# Keep this fallback so the model module remains importable while config.py is
# being assembled in the bootstrap task.
try:
    from .config import DISCLAIMER
except ImportError:  # pragma: no cover - only used during incremental setup
    DISCLAIMER = "의료진단이 아니며 의료적 판단을 대체하지 않는다"


@dataclass(frozen=True)
class ReferenceRecord:
    """One normalized reference-data row."""

    measure_type: MeasureType
    sex: str
    age_min: int
    age_max: int
    region: str | None
    quantiles: Mapping[float, float]
    source: str
    source_row: int


@dataclass(frozen=True)
class ValidatedInput:
    """Validated user measurements, retained in the dashboard's units."""

    sex: str
    age: int
    height_cm: float
    weight_kg: float
    waist_cm: float
    region: str | None = None


@dataclass(frozen=True)
class SelectionInfo:
    """Reference-group selection and fallback state for one metric."""

    requested_region: str | None
    selected_region: str | None
    used_fallback: bool
    reason: str | None = None


@dataclass(frozen=True)
class FieldError:
    """A user-correctable validation error tied to one input field."""

    field: str
    code: str
    message: str


@dataclass(frozen=True)
class RowIssue:
    """A non-fatal issue associated with a source-data row."""

    source: str
    source_row: int
    field: str
    code: str
    reason: str


@dataclass(frozen=True)
class MetricResult:
    """Result for one metric, including an explicitly unavailable state."""

    measure_type: MeasureType
    raw_value: float
    percentile: float | None = None
    grade: int | None = None
    emoji: str | None = None
    label: str | None = None
    message: str | None = None
    reference_region: str | None = None
    used_fallback: bool = False
    error: str | None = None
    selection_info: SelectionInfo | None = None

    def __post_init__(self) -> None:
        if self.error is not None and any(
            value is not None for value in (self.percentile, self.grade, self.message)
        ):
            raise ValueError(
                "MetricResult.error가 있으면 percentile, grade, message는 None이어야 합니다."
            )
        if self.percentile is not None and not 0.0 <= self.percentile <= 100.0:
            raise ValueError("MetricResult.percentile은 0~100 범위여야 합니다.")

    @classmethod
    def unavailable(
        cls,
        measure_type: MeasureType,
        raw_value: float,
        error: str,
        *,
        reference_region: str | None = None,
        used_fallback: bool = False,
        selection_info: SelectionInfo | None = None,
    ) -> "MetricResult":
        """Create a result that cannot produce grade/message output."""
        if not error:
            raise ValueError("MetricResult 오류 코드는 비어 있을 수 없습니다.")
        return cls(
            measure_type=measure_type,
            raw_value=raw_value,
            reference_region=reference_region,
            used_fallback=used_fallback,
            error=error,
            selection_info=selection_info,
        )

    @classmethod
    def calculated(
        cls,
        measure_type: MeasureType,
        raw_value: float,
        percentile: float,
        grade: int,
        emoji: str,
        label: str,
        message: str,
        *,
        reference_region: str | None = None,
        used_fallback: bool = False,
        selection_info: SelectionInfo | None = None,
    ) -> "MetricResult":
        """Create a complete, available metric result."""
        return cls(
            measure_type=measure_type,
            raw_value=raw_value,
            percentile=percentile,
            grade=grade,
            emoji=emoji,
            label=label,
            message=message,
            reference_region=reference_region,
            used_fallback=used_fallback,
            selection_info=selection_info,
        )


@dataclass(frozen=True)
class DiagnosticResult:
    """Independent BMI and waist outcomes shown on the diagnosis page."""

    bmi: MetricResult
    waist: MetricResult
    disclaimer: str = DISCLAIMER


@dataclass(frozen=True)
class EvaluationResult:
    """Evaluation output shared by the two model-comparison pipelines."""

    model_name: str
    target_name: str
    feature_names: tuple[str, ...]
    y_true: tuple[float, ...]
    y_pred: tuple[float, ...]
    mae: float | None
    r2: float | None
    evaluable: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.evaluable and (self.mae is None or self.r2 is None):
            raise ValueError("평가 가능한 결과에는 mae와 r2가 필요합니다.")
        if not self.evaluable and (self.mae is not None or self.r2 is not None):
            raise ValueError("평가 불가 결과에는 mae와 r2를 포함할 수 없습니다.")
        if len(self.y_true) != len(self.y_pred):
            raise ValueError("y_true와 y_pred의 길이가 같아야 합니다.")


__all__ = [
    "MeasureType",
    "ReferenceRecord",
    "ValidatedInput",
    "MetricResult",
    "DiagnosticResult",
    "EvaluationResult",
    "SelectionInfo",
    "FieldError",
    "RowIssue",
]
