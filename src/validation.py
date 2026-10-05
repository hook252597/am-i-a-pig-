"""Validation and normalization for diagnosis-page inputs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .config import INPUT_RANGES
from .models import FieldError, ValidatedInput


_REQUIRED_FIELDS = ("sex", "age", "height_cm", "weight_kg", "waist_cm")


def _error(field: str, code: str, message: str) -> FieldError:
    """Create a structured, field-specific validation error."""
    return FieldError(field=field, code=code, message=message)


def _missing(raw: Mapping[str, object], field: str) -> bool:
    """Return whether a required field is absent or explicitly empty."""
    if field not in raw or raw[field] is None:
        return True
    value = raw[field]
    return isinstance(value, str) and not value.strip()


def _coerce_finite_number(
    raw: Mapping[str, object], field: str, errors: list[FieldError]
) -> float | None:
    """Validate one numeric field without modifying errors for other fields."""
    if _missing(raw, field):
        minimum, maximum, unit = INPUT_RANGES[field]
        errors.append(
            _error(
                field,
                "REQUIRED",
                f"{field}은(는) 필수 입력입니다. {minimum:g}~{maximum:g}{unit} 범위로 입력하세요.",
            )
        )
        return None

    value = raw[field]
    # bool is technically an int in Python, but is not a measurement.
    if isinstance(value, bool):
        number: float | None = None
    else:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError):
            number = None

    if number is None or not math.isfinite(number):
        errors.append(
            _error(
                field,
                "INVALID_NUMBER",
                f"{field}은(는) 유한한 숫자로 입력해야 합니다.",
            )
        )
        return None

    minimum, maximum, unit = INPUT_RANGES[field]
    if field == "age" and (not isinstance(value, int) or isinstance(value, bool)):
        errors.append(
            _error(field, "INVALID_NUMBER", "age은(는) 정수로 입력해야 합니다.")
        )
        return None

    if not minimum <= number <= maximum:
        errors.append(
            _error(
                field,
                "OUT_OF_RANGE",
                f"{field}은(는) {minimum:g}~{maximum:g}{unit} 범위로 입력해야 합니다.",
            )
        )
        return None

    return number


def validate_input(raw: dict[str, object]) -> tuple[ValidatedInput | None, list[FieldError]]:
    """Validate raw diagnosis inputs and return normalized values plus all errors.

    Every field is checked independently, so an invalid value never prevents
    errors from being reported for other fields or alters their normalized
    values.  Measurements remain in the model's standard cm/kg units; BMI
    converts height to metres at calculation time.  ``region=None`` is valid.
    """
    if not isinstance(raw, Mapping):
        raise TypeError("raw 입력은 매핑이어야 합니다.")

    errors: list[FieldError] = []

    if _missing(raw, "sex"):
        errors.append(_error("sex", "REQUIRED", "sex은(는) 필수 입력입니다."))
        sex: str | None = None
    else:
        value = raw["sex"]
        if not isinstance(value, str):
            errors.append(_error("sex", "INVALID_NUMBER", "sex은(는) 문자열이어야 합니다."))
            sex = None
        else:
            sex = value.strip()
            if not sex:
                errors.append(_error("sex", "REQUIRED", "sex은(는) 필수 입력입니다."))
                sex = None

    age_value = _coerce_finite_number(raw, "age", errors)
    height_value = _coerce_finite_number(raw, "height_cm", errors)
    weight_value = _coerce_finite_number(raw, "weight_kg", errors)
    waist_value = _coerce_finite_number(raw, "waist_cm", errors)

    if errors:
        return None, errors

    # The checks above guarantee these values and sex are present.
    assert sex is not None
    assert age_value is not None
    assert height_value is not None
    assert weight_value is not None
    assert waist_value is not None

    region = raw.get("region")
    if region is not None and not isinstance(region, str):
        region = str(region)

    return (
        ValidatedInput(
            sex=sex,
            age=int(age_value),
            height_cm=float(height_value),
            weight_kg=float(weight_value),
            waist_cm=float(waist_value),
            region=region,
        ),
        [],
    )


__all__ = ["validate_input"]
