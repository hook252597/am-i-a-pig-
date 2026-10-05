"""Reference-standard exploratory data analysis page."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

import app
from src.config import PERCENTILES
from src.data_loader import COLUMN_LABELS
from src.visualization import eda_distribution


# This cache is keyed by the source fingerprint, so an edited workbook is read
# again instead of serving stale file-level quality statistics.
@st.cache_data(show_spinner=False)
def _read_source_frame(path: str, fingerprint: tuple[str, int | None]) -> pd.DataFrame:
    del fingerprint
    workbook = pd.ExcelFile(path)
    return pd.read_excel(workbook, sheet_name=workbook.sheet_names[0])


def _display_column_label(column: object) -> str:
    """Map source columns to stable, user-facing Korean descriptions."""
    text = str(column).strip()
    if text in COLUMN_LABELS:
        return COLUMN_LABELS[text]
    if any(text.startswith(f"{percentile}분위수") for percentile in PERCENTILES):
        return "분위수 기준값"
    return "추가 열"


def _source_summary(path: Path, fingerprint: tuple[str, int | None]) -> tuple[dict[str, Any], pd.DataFrame]:
    """Return quality metadata and a friendly dtype/missing table for one file."""
    frame = _read_source_frame(str(path), fingerprint)
    columns = pd.DataFrame(
        {
            "열 설명": [_display_column_label(column) for column in frame.columns],
            "자료형": [str(dtype) for dtype in frame.dtypes],
            "결측 수": [int(value) for value in frame.isna().sum()],
        }
    )
    return {
        "source": path.name,
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "missing_columns": int(frame.isna().any(axis=0).sum()),
        "missing_values": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
    }, columns


def _records_frame(records: list[Any]) -> pd.DataFrame:
    """Expand normalized records into long-form EDA rows."""
    rows: list[dict[str, Any]] = []
    for record in records:
        for percentile, value in record.quantiles.items():
            rows.append(
                {
                    "measure_type": "BMI" if record.measure_type == "bmi" else "허리둘레",
                    "sex": record.sex,
                    "age": f"{record.age_min}~{record.age_max}세",
                    "region": record.region or "미지정",
                    "percentile": float(percentile),
                    "value": float(value),
                    "source": record.source,
                }
            )
    return pd.DataFrame(rows)


def _render_source_quality() -> None:
    """Render per-file dimensions, types, missingness, and duplicates."""
    st.subheader("파일별 데이터 품질")
    for path in (app.BMI_PATH, app.WAIST_PATH):
        fingerprint = app.file_fingerprint(path)
        summary, columns = _source_summary(path, fingerprint)
        st.markdown(f"**{summary['source']}**")
        metric_columns = st.columns(5)
        metric_columns[0].metric("행 수", summary["rows"])
        metric_columns[1].metric("열 수", summary["columns"])
        metric_columns[2].metric("결측 열 수", summary["missing_columns"])
        metric_columns[3].metric("결측 셀 수", summary["missing_values"])
        metric_columns[4].metric("중복 행 수", summary["duplicate_rows"])
        st.dataframe(columns, use_container_width=True, hide_index=True)


def _render_categories(frame: pd.DataFrame) -> None:
    st.subheader("참조 범주")
    if frame.empty:
        st.info("유효한 참조 행이 없어 범주를 표시할 수 없습니다.")
        return
    category_columns = st.columns(3)
    category_columns[0].write("**성별**")
    category_columns[0].write(sorted(frame["sex"].dropna().unique().tolist()))
    category_columns[1].write("**연령 구간**")
    category_columns[1].write(sorted(frame["age"].dropna().unique().tolist()))
    category_columns[2].write("**지역**")
    category_columns[2].write(sorted(frame["region"].dropna().unique().tolist()))


def _render_distributions(frame: pd.DataFrame) -> None:
    st.subheader("분위수·참조 측정값 분포")
    if frame.empty:
        st.info("유효한 분위수 기준값이 없어 분포를 표시할 수 없습니다.")
        return
    measure_filter = st.selectbox(
        "분포 지표",
        ["전체", "BMI", "허리둘레"],
        key="eda.distribution_measure",
    )
    chart_frame = frame if measure_filter == "전체" else frame[frame["measure_type"] == measure_filter]
    if chart_frame.empty:
        st.info("선택한 지표의 분포 데이터가 없습니다.")
        return
    left, right = st.columns(2)
    left.plotly_chart(
        eda_distribution(
            chart_frame,
            value_column="value",
            title="분위수 기준값(참조 측정값) 분포",
        ),
        use_container_width=True,
    )
    right.plotly_chart(
        eda_distribution(
            chart_frame,
            value_column="percentile",
            title="분위수 위치 분포",
        ),
        use_container_width=True,
    )


def _render_validity(records: list[Any], issues: list[Any]) -> None:
    st.subheader("행 유효성 요약")
    valid_by_source = Counter(record.source for record in records)
    invalid_by_source = Counter(issue.source for issue in issues)
    sources = sorted(set(valid_by_source) | set(invalid_by_source))
    summary = pd.DataFrame(
        [
            {
                "원본 파일": source,
                "유효 행 수": valid_by_source.get(source, 0),
                "무효 행 진단 수": invalid_by_source.get(source, 0),
            }
            for source in sources
        ]
    )
    st.dataframe(summary, use_container_width=True, hide_index=True)
    if issues:
        st.warning(f"일부 행을 사용할 수 없습니다({len(issues)}건). 유효한 행은 계속 분석합니다.")


def render() -> None:
    """Render the complete EDA page inside the shared app boundaries."""
    st.title("데이터 탐색 EDA")
    app.show_disclaimer()
    state = app.page_state("eda")
    current_fingerprint = app.loader_cache_key()[0:2]
    previous_fingerprint = state.get("source_fingerprint")
    state["source_fingerprint"] = current_fingerprint
    if previous_fingerprint is not None and previous_fingerprint != current_fingerprint:
        st.info("원본 참조 파일 변경을 감지하여 EDA 캐시를 새로 갱신했습니다.")
    st.caption("원본 파일의 수정 시각을 포함한 fingerprint로 로딩·품질 요약 캐시를 관리합니다.")

    with app.error_boundary("EDA 데이터 탐색"):
        records, issues = app.load_cached_reference_data()
        _render_source_quality()
        normalized = _records_frame(records)
        _render_categories(normalized)
        _render_distributions(normalized)
        _render_validity(records, issues)


render()
