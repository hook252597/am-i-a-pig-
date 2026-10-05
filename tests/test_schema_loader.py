from __future__ import annotations

import gc
import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from src.data_loader import COLUMN_LABELS, inspect_workbook, load_reference_data
from src.errors import DataPreparationError

PERCENTILE_COLUMNS = [f"{p}분위수 (단위)" for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)]


def _write(path: Path, rows: list[dict[str, object]], *, missing: str | None = None) -> None:
    columns = ["지역", "성별", "나이", *PERCENTILE_COLUMNS]
    frame = pd.DataFrame(rows, columns=columns)
    if missing:
        frame = frame.drop(columns=[missing])
    frame.to_excel(path, index=False)


def _row(age: str = "20~24 세", sex: str = "남성") -> dict[str, object]:
    return {
        "지역": "전국",
        "성별": sex,
        "나이": age,
        **{column: float(index + 1) for index, column in enumerate(PERCENTILE_COLUMNS)},
    }


def test_loads_bmi_and_waist_into_standard_schema(tmp_path: Path) -> None:
    bmi = tmp_path / "bmi.xlsx"
    waist = tmp_path / "waist.xlsx"
    _write(bmi, [_row()])
    _write(waist, [_row("25 ~ 29 세", "여성")])

    records, issues = load_reference_data(bmi, waist)

    assert issues == []
    assert [(record.measure_type, record.sex, record.age_min, record.age_max) for record in records] == [
        ("bmi", "남성", 20, 24),
        ("waist", "여성", 25, 29),
    ]
    assert records[0].region == "전국"
    assert records[0].source == "bmi.xlsx"
    assert records[0].source_row == 2
    assert records[0].quantiles[1.0] == 1.0


def test_invalid_rows_are_reported_and_valid_rows_continue(tmp_path: Path) -> None:
    bmi = tmp_path / "bmi.xlsx"
    waist = tmp_path / "waist.xlsx"
    invalid = _row("invalid")
    valid = _row("30~34 세")
    _write(bmi, [invalid, valid])
    _write(waist, [_row("35~39 세")])

    records, issues = load_reference_data(bmi, waist)

    assert len(records) == 2
    assert [record.age_min for record in records] == [30, 35]
    assert any(issue.source_row == 2 and issue.field == "나이" for issue in issues)


def test_missing_required_column_is_fatal(tmp_path: Path) -> None:
    bmi = tmp_path / "bmi.xlsx"
    waist = tmp_path / "waist.xlsx"
    _write(bmi, [_row()], missing="50분위수 (단위)")
    _write(waist, [_row()])

    with pytest.raises(DataPreparationError) as exc_info:
        load_reference_data(bmi, waist)

    assert exc_info.value.code == "REQUIRED_COLUMN_MISSING"
    assert "50분위수" in str(exc_info.value)


def test_no_valid_rows_is_fatal(tmp_path: Path) -> None:
    bmi = tmp_path / "bmi.xlsx"
    waist = tmp_path / "waist.xlsx"
    _write(bmi, [_row("bad")])
    _write(waist, [_row("also bad")])

    with pytest.raises(DataPreparationError) as exc_info:
        load_reference_data(bmi, waist)

    assert exc_info.value.code == "NO_VALID_REFERENCE_DATA"


def test_reload_is_deterministic_and_does_not_mutate_source(tmp_path: Path) -> None:
    bmi = tmp_path / "bmi.xlsx"
    waist = tmp_path / "waist.xlsx"
    _write(bmi, [_row(), _row("25~29 세")])
    _write(waist, [_row("30~34 세")])

    first = load_reference_data(bmi, waist)
    second = load_reference_data(bmi, waist)

    assert first == second
    assert [record.source_row for record in first[0]] == [2, 3, 2]


def test_inspection_exposes_korean_user_labels(tmp_path: Path) -> None:
    path = tmp_path / "reference.xlsx"
    _write(path, [_row()])

    info = inspect_workbook(path)

    assert info["sheets"] == ("Sheet1",)
    assert info["column_labels"] == COLUMN_LABELS
    assert info["column_labels"]["source_row"] == "원본 행"


_VALID_SPEC = st.tuples(
    st.integers(min_value=0, max_value=100),
    st.integers(min_value=0, max_value=20),
    st.sampled_from(("남성", "여성")),
    st.sampled_from(("전국", "서울", "부산")),
    st.integers(min_value=1, max_value=1_000),
)


@st.composite
def _mixed_workbook_rows(draw: st.DrawFn) -> tuple[list[dict[str, object]], int, list[tuple[str, int, str, str, int]]]:
    valid_specs = draw(st.lists(_VALID_SPEC, min_size=1, max_size=4))
    invalid_count = draw(st.integers(min_value=1, max_value=3))
    valid_rows = [
        {
            "지역": region,
            "성별": sex,
            "나이": f"{age_min}~{age_min + age_span} 세",
            **{
                column: float(base + index)
                for index, column in enumerate(PERCENTILE_COLUMNS)
            },
        }
        for age_min, age_span, sex, region, base in valid_specs
    ]
    invalid_rows = [_row("잘못된 연령") for _ in range(invalid_count)]
    return valid_rows + invalid_rows, invalid_count, valid_specs


# Feature: fun-obesity-dashboard, Property 11: 표준 스키마 변환과 결정성
# Validates: Requirements 6.2, 6.3, 6.4
@given(bmi_case=_mixed_workbook_rows(), waist_case=_mixed_workbook_rows())
@settings(max_examples=100)
def test_standard_schema_conversion_is_lossless_deterministic_and_immutable(
    bmi_case: tuple[list[dict[str, object]], int, list[tuple[str, int, str, str, int]]],
    waist_case: tuple[list[dict[str, object]], int, list[tuple[str, int, str, str, int]]],
) -> None:
    """Mixed rows retain schema/order while invalid rows remain identifiable."""
    bmi_rows, bmi_invalid_count, bmi_specs = bmi_case
    waist_rows, waist_invalid_count, waist_specs = waist_case
    with tempfile.TemporaryDirectory() as directory:
        tmp_path = Path(directory)
        bmi_path = tmp_path / "bmi.xlsx"
        waist_path = tmp_path / "waist.xlsx"
        _write(bmi_path, bmi_rows)
        _write(waist_path, waist_rows)
        before = {path: hashlib.sha256(path.read_bytes()).digest() for path in (bmi_path, waist_path)}

        first_records, first_issues = load_reference_data(bmi_path, waist_path)
        second_records, second_issues = load_reference_data(bmi_path, waist_path)

        assert first_records == second_records
        assert first_issues == second_issues
        assert {path: hashlib.sha256(path.read_bytes()).digest() for path in before} == before

        expected_records = []
        for measure_type, source_name, specs in (
            ("bmi", "bmi.xlsx", bmi_specs),
            ("waist", "waist.xlsx", waist_specs),
        ):
            for source_row, (age_min, age_span, sex, region, base) in enumerate(specs, start=2):
                expected_records.append(
                    (
                        measure_type,
                        sex,
                        age_min,
                        age_min + age_span,
                        region,
                        {float(p): float(base + index) for index, p in enumerate((1, 5, 10, 25, 50, 75, 90, 95, 99))},
                        source_name,
                        source_row,
                    )
                )
        assert [
            (
                record.measure_type,
                record.sex,
                record.age_min,
                record.age_max,
                record.region,
                record.quantiles,
                record.source,
                record.source_row,
            )
            for record in first_records
        ] == expected_records

        expected_issue_rows = {
            (source, source_row)
            for source, rows, invalid_count in (
                ("bmi.xlsx", bmi_rows, bmi_invalid_count),
                ("waist.xlsx", waist_rows, waist_invalid_count),
            )
            for source_row in range(len(rows) - invalid_count + 2, len(rows) + 2)
        }
        assert {
            (issue.source, issue.source_row)
            for issue in first_issues
            if issue.field == "나이"
        } == expected_issue_rows
        gc.collect()
