"""Convert percentile positions into the dashboard's five grade bands."""

from __future__ import annotations

import math

from .config import GRADE_BANDS


def grade_for_percentile(percentile: float) -> tuple[int, str, str]:
    """Return ``(grade, emoji, label)`` for a percentile in ``[0, 100]``.

    Band boundaries and their presentation values are intentionally sourced
    from :data:`src.config.GRADE_BANDS` so the policy has one source of truth.
    Invalid positions raise before any grade or message is produced.
    """
    try:
        position = float(percentile)
    except (TypeError, ValueError) as exc:
        raise ValueError("분위수 위치는 0~100이어야 합니다.") from exc

    if not math.isfinite(position) or not 0.0 <= position <= 100.0:
        raise ValueError("분위수 위치는 0~100이어야 합니다.")

    for index, (lower, upper, grade, emoji, label) in enumerate(GRADE_BANDS):
        is_last_band = index == len(GRADE_BANDS) - 1
        if lower <= position < upper or (is_last_band and lower <= position <= upper):
            return grade, emoji, label

    # This protects callers if the configured bands develop a gap or do not
    # cover the validated range completely.
    raise ValueError("분위수 위치에 해당하는 등급 구간이 없습니다.")


__all__ = ["grade_for_percentile"]
