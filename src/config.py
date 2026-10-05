"""Shared policy and input boundaries for the dashboard.

Keeping these values in one module prevents UI, calculations, and tests from
silently drifting apart when a policy changes.
"""

from __future__ import annotations

from typing import Final

PERCENTILES: Final[tuple[int, ...]] = (1, 5, 10, 25, 50, 75, 90, 95, 99)

# Bounds are lower-inclusive and upper-exclusive, except for the final band,
# which includes 100.0.
GRADE_BANDS: Final[tuple[tuple[float, float, int, str, str], ...]] = (
    (0.0, 20.0, 1, "🐣", "가볍게 출발"),
    (20.0, 40.0, 2, "🙂", "안정적인 흐름"),
    (40.0, 60.0, 3, "😎", "균형 잡힌 구간"),
    (60.0, 80.0, 4, "😅", "조금 더 살펴보기"),
    (80.0, 100.0, 5, "🚨", "건강 습관 점검"),
)

DISCLAIMER: Final[str] = "의료진단이 아니며 의료적 판단을 대체하지 않는다"
REGION_FALLBACKS: Final[tuple[str | None, ...]] = ("전국", "미지정", None, "")
RANDOM_SEED: Final[int] = 42

# Public validation policy: (minimum, maximum, unit).
INPUT_RANGES: Final[dict[str, tuple[float, float, str]]] = {
    "age": (0.0, 120.0, "세"),
    "height_cm": (30.0, 250.0, "cm"),
    "weight_kg": (1.0, 300.0, "kg"),
    "waist_cm": (20.0, 200.0, "cm"),
}

# Names used by callers that need a direct lookup without unpacking ranges.
AGE_RANGE: Final[tuple[int, int]] = (0, 120)
HEIGHT_CM_RANGE: Final[tuple[float, float]] = (30.0, 250.0)
WEIGHT_KG_RANGE: Final[tuple[float, float]] = (1.0, 300.0)
WAIST_CM_RANGE: Final[tuple[float, float]] = (20.0, 200.0)

__all__ = [
    "AGE_RANGE",
    "DISCLAIMER",
    "GRADE_BANDS",
    "HEIGHT_CM_RANGE",
    "INPUT_RANGES",
    "PERCENTILES",
    "RANDOM_SEED",
    "REGION_FALLBACKS",
    "WAIST_CM_RANGE",
    "WEIGHT_KG_RANGE",
]
