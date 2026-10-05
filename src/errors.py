"""Typed, user-facing errors for data preparation and result generation."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Stable codes that UI layers can map to Korean guidance."""

    FILE_UNREADABLE = "FILE_UNREADABLE"
    REQUIRED_COLUMN_MISSING = "REQUIRED_COLUMN_MISSING"
    INVALID_REFERENCE_ROW = "INVALID_REFERENCE_ROW"
    NO_VALID_REFERENCE_DATA = "NO_VALID_REFERENCE_DATA"
    REFERENCE_GROUP_NOT_FOUND = "REFERENCE_GROUP_NOT_FOUND"
    EMPTY_QUANTILE_BOUNDARIES = "EMPTY_QUANTILE_BOUNDARIES"
    INVALID_QUANTILE_BOUNDARIES = "INVALID_QUANTILE_BOUNDARIES"
    QUANTILE_OUT_OF_RANGE = "QUANTILE_OUT_OF_RANGE"
    MESSAGE_CONFIGURATION_INVALID = "MESSAGE_CONFIGURATION_INVALID"
    MESSAGE_CATALOG_MISSING = "MESSAGE_CATALOG_MISSING"
    MESSAGE_UNSAFE = "MESSAGE_UNSAFE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    REQUIRED = "REQUIRED"
    INVALID_NUMBER = "INVALID_NUMBER"


class DashboardError(Exception):
    """Base class carrying a stable code and optional structured context."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.details = details or {}

    def __str__(self) -> str:
        return self.message


class DataPreparationError(DashboardError):
    """Raised when normalized reference data cannot be prepared."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | str = ErrorCode.FILE_UNREADABLE,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


class QuantileCalculationError(DashboardError):
    """Raised when reference boundaries cannot produce a percentile."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | str = ErrorCode.INVALID_QUANTILE_BOUNDARIES,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


class MessageConfigurationError(DashboardError):
    """Raised when the safe message catalog is incomplete or invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | str = ErrorCode.MESSAGE_CONFIGURATION_INVALID,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


__all__ = [
    "ErrorCode",
    "DashboardError",
    "DataPreparationError",
    "QuantileCalculationError",
    "MessageConfigurationError",
]
