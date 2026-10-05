"""BMI calculation and display formatting helpers."""

from __future__ import annotations


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """Calculate raw BMI from kilograms and centimetres.

    Height is converted to metres before applying the BMI formula.  The raw
    floating-point result is returned so downstream percentile and grade
    calculations are not affected by display rounding.
    """
    height_m = height_cm / 100.0
    return weight_kg / (height_m**2)


def format_bmi(raw_bmi: float) -> str:
    """Format a raw BMI for display without changing the raw value."""
    return f"{raw_bmi:.2f}"


__all__ = ["calculate_bmi", "format_bmi"]
