"""Excel reference-data loading and normalization.

The loader deliberately keeps the original workbook untouched: pandas creates a
new frame for each read and normalization only reads from that frame.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import PERCENTILES
from .errors import DataPreparationError, ErrorCode
from .models import MeasureType, ReferenceRecord, RowIssue

AGE_PATTERN = re.compile(r"^(\d+)\s*~\s*(\d+)\s*세$")
COLUMN_LABELS: dict[str, str] = {
    "지역": "지역",
    "성별": "성별",
    "나이": "연령 구간",
    "quantiles": "분위수 기준값",
    "source": "원본 파일",
    "source_row": "원본 행",
}


def _quantile_column(columns: Iterable[object], percentile: int) -> str | None:
    """Find a percentile column while allowing unit suffixes."""
    prefix = f"{percentile}분위수"
    for column in columns:
        if str(column).strip().startswith(prefix):
            return str(column)
    return None


def _required_columns(columns: Iterable[object]) -> tuple[bool, list[str]]:
    names = {str(column).strip() for column in columns}
    missing = [name for name in ("지역", "성별", "나이") if name not in names]
    missing.extend(
        f"{p}분위수"
        for p in PERCENTILES
        if not any(str(column).strip().startswith(f"{p}분위수") for column in columns)
    )
    return not missing, missing


def _as_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _row_issue(source: str, row: int, field: str, code: str, reason: str) -> RowIssue:
    return RowIssue(source=source, source_row=row, field=field, code=code, reason=reason)


def _normalize_frame(
    frame: pd.DataFrame, *, measure_type: MeasureType, source: str
) -> tuple[list[ReferenceRecord], list[RowIssue]]:
    records: list[ReferenceRecord] = []
    issues: list[RowIssue] = []
    quantile_columns = {p: _quantile_column(frame.columns, p) for p in PERCENTILES}

    for index, row in frame.iterrows():
        source_row = int(index) + 2  # Excel header occupies row 1.
        row_issues: list[RowIssue] = []
        sex = _as_text(row.get("성별"))
        region_value = row.get("지역")
        region = None if pd.isna(region_value) else _as_text(region_value)
        age_text = _as_text(row.get("나이"))
        age_match = AGE_PATTERN.fullmatch(age_text)
        if not sex:
            row_issues.append(_row_issue(source, source_row, "성별", "REQUIRED", "성별 값이 비어 있습니다."))
        if not age_match:
            row_issues.append(_row_issue(source, source_row, "나이", "INVALID_AGE", "나이는 '20~24 세' 형식이어야 합니다."))

        quantiles: dict[float, float] = {}
        for percentile, column in quantile_columns.items():
            raw = row.get(column) if column is not None else None
            try:
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError
            except (TypeError, ValueError):
                row_issues.append(
                    _row_issue(source, source_row, f"{percentile}분위수", "INVALID_NUMBER", "분위수 기준값은 유한한 숫자여야 합니다.")
                )
                continue
            quantiles[float(percentile)] = value

        if len(quantiles) == len(PERCENTILES):
            values = [quantiles[float(p)] for p in PERCENTILES]
            if any(left > right for left, right in zip(values, values[1:])):
                row_issues.append(_row_issue(source, source_row, "분위수", "INVALID_ORDER", "분위수 기준값은 오름차순이어야 합니다."))

        if row_issues:
            issues.extend(row_issues)
            continue

        age_min, age_max = int(age_match.group(1)), int(age_match.group(2))
        if age_min > age_max:
            issues.append(_row_issue(source, source_row, "나이", "INVALID_AGE", "연령 구간의 시작은 끝보다 클 수 없습니다."))
            continue
        records.append(
            ReferenceRecord(
                measure_type=measure_type,
                sex=sex,
                age_min=age_min,
                age_max=age_max,
                region=region or None,
                quantiles=quantiles,
                source=source,
                source_row=source_row,
            )
        )
    return records, issues


def _read_workbook(path: Path, measure_type: MeasureType) -> tuple[list[ReferenceRecord], list[RowIssue]]:
    if not path.exists() or not path.is_file():
        raise DataPreparationError(
            f"참조 파일을 읽을 수 없습니다: {path.name}",
            code=ErrorCode.FILE_UNREADABLE,
            details={"path": str(path), "label": "참조 파일"},
        )
    try:
        workbook = pd.ExcelFile(path)
        if not workbook.sheet_names:
            raise ValueError("시트가 없습니다.")
        # The current reference workbooks contain one sheet. Reading the first
        # sheet makes the selected sheet explicit and deterministic.
        frame = pd.read_excel(workbook, sheet_name=workbook.sheet_names[0])
    except Exception as exc:
        raise DataPreparationError(
            f"참조 파일을 읽을 수 없습니다: {path.name}",
            code=ErrorCode.FILE_UNREADABLE,
            details={"path": str(path), "reason": str(exc)},
        ) from exc

    valid_columns, missing = _required_columns(frame.columns)
    if not valid_columns:
        raise DataPreparationError(
            f"{path.name}에 필수 열이 없습니다: {', '.join(missing)}",
            code=ErrorCode.REQUIRED_COLUMN_MISSING,
            details={"source": str(path), "missing": tuple(missing), "labels": COLUMN_LABELS},
        )
    return _normalize_frame(frame.copy(deep=True), measure_type=measure_type, source=path.name)


def load_reference_data(
    bmi_path: str | Path, waist_path: str | Path
) -> tuple[list[ReferenceRecord], list[RowIssue]]:
    """Load both workbooks as deterministic records and non-fatal row issues."""
    paths = ((Path(bmi_path), "bmi"), (Path(waist_path), "waist"))
    records: list[ReferenceRecord] = []
    issues: list[RowIssue] = []
    for path, measure_type in paths:
        loaded, row_issues = _read_workbook(path, measure_type)  # type: ignore[arg-type]
        records.extend(loaded)
        issues.extend(row_issues)
    if not records:
        raise DataPreparationError(
            "유효한 참조 데이터 행이 없습니다.",
            code=ErrorCode.NO_VALID_REFERENCE_DATA,
            details={"issues": tuple(issues)},
        )
    return records, issues


def inspect_workbook(path: str | Path) -> dict[str, object]:
    """Return sheet and user-facing column metadata without normalizing rows."""
    path = Path(path)
    if not path.exists():
        raise DataPreparationError(f"참조 파일을 찾을 수 없습니다: {path.name}", code=ErrorCode.FILE_UNREADABLE)
    try:
        workbook = pd.ExcelFile(path)
        frame = pd.read_excel(workbook, sheet_name=workbook.sheet_names[0], nrows=0)
    except Exception as exc:
        raise DataPreparationError(f"참조 파일을 읽을 수 없습니다: {path.name}", code=ErrorCode.FILE_UNREADABLE) from exc
    return {
        "source": path.name,
        "sheets": tuple(workbook.sheet_names),
        "columns": tuple(str(column) for column in frame.columns),
        "column_labels": dict(COLUMN_LABELS),
    }


__all__ = ["AGE_PATTERN", "COLUMN_LABELS", "inspect_workbook", "load_reference_data"]
