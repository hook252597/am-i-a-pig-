"""진단 입력과 BMI/허리둘레 결과를 표시하는 Streamlit page."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import streamlit as st

import app
from src.bmi import format_bmi
from src.config import AGE_RANGE, HEIGHT_CM_RANGE, RANDOM_SEED, WAIST_CM_RANGE, WEIGHT_KG_RANGE
from src.diagnosis import build_diagnostic
from src.models import DiagnosticResult, FieldError, MetricResult, ReferenceRecord
from src.validation import validate_input
from src.visualization import metric_bar, percentile_gauge

PAGE_NAMESPACE = "diagnosis"
FIELD_LABELS = {
    "sex": "성별",
    "age": "나이",
    "height_cm": "키",
    "weight_kg": "몸무게",
    "waist_cm": "허리둘레",
    "region": "지역",
}


def _unique_text(values: Iterable[str | None]) -> list[str]:
    """Return stable, non-empty selectbox values."""
    return sorted({value.strip() for value in values if value and value.strip()})


def _control_options(records: Sequence[ReferenceRecord]) -> tuple[list[str], list[str]]:
    """Derive sex and waist-region controls from normalized reference records."""
    sexes = _unique_text(record.sex for record in records)
    regions = _unique_text(
        record.region for record in records if record.measure_type == "waist"
    )
    return sexes, regions


def _raw_input(
    sex: str | None,
    age: int | float | None,
    height_cm: float | None,
    weight_kg: float | None,
    waist_cm: float | None,
    region: str | None,
) -> dict[str, object]:
    """Build the raw form payload without normalizing or calculating values."""
    return {
        "sex": sex,
        "age": age,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "waist_cm": waist_cm,
        "region": region or None,
    }


def _show_field_errors(errors: Sequence[FieldError]) -> None:
    """Render every validation error with its associated user-facing field."""
    for error in errors:
        label = FIELD_LABELS.get(error.field, error.field)
        st.error(f"{label}: {error.message}")


def _display_number(value: float, *, decimals: int = 2) -> str:
    """Format a calculated value for display only."""
    return f"{value:.{decimals}f}"


def _render_reference_metadata(metric: MetricResult, label: str) -> None:
    """Show the selected reference region and explicit fallback information."""
    selection = metric.selection_info
    if selection is None:
        return

    selected = selection.selected_region or "지역 미지정"
    requested = selection.requested_region or "지역 미지정"
    st.caption(f"{label} 참조집단: {selected} (요청 지역: {requested})")
    if metric.used_fallback:
        reason = selection.reason or "요청 지역 참조집단이 없어 fallback을 적용했습니다."
        st.info(f"지역 fallback: {reason} 사용 지역은 {selected}입니다.")


def _render_metric(metric: MetricResult, *, title: str, unit: str) -> None:
    """Render one metric without reimplementing calculation or grading policy."""
    st.subheader(title)
    display_value = format_bmi(metric.raw_value) if metric.measure_type == "bmi" else _display_number(metric.raw_value)
    value_label = "BMI" if metric.measure_type == "bmi" else "허리둘레"
    value_column, result_column = st.columns(2)
    with value_column:
        st.metric(f"{value_label} 표시값", f"{display_value} {unit}")
        st.caption(f"원시값: {_display_number(metric.raw_value)} {unit}")
        st.caption(f"표시값: {display_value} {unit}")
    with result_column:
        if metric.percentile is not None:
            st.metric("참조집단 내 분위수", f"{metric.percentile:.2f}")
        else:
            st.metric("참조집단 내 분위수", "계산 불가")

    _render_reference_metadata(metric, title)
    if metric.error is not None:
        st.warning(f"{title} 계산 불가: {metric.error}. 해당 지표의 참조 조건을 확인해 주세요.")
    else:
        grade_text = f"{metric.emoji} {metric.grade}등급 · {metric.label}"
        st.success(grade_text)
        if metric.message:
            st.write(metric.message)

    gauge_column, bar_column = st.columns(2)
    with gauge_column:
        st.plotly_chart(
            percentile_gauge(metric, title=f"{title} 분위수 게이지"),
            use_container_width=True,
        )
    with bar_column:
        st.plotly_chart(
            metric_bar(metric, title=f"{title} 분위수 막대"),
            use_container_width=True,
        )


def _render_result(result: DiagnosticResult) -> None:
    """Render both independent metrics and the result-level disclaimer."""
    st.info(result.disclaimer)
    st.header("진단 결과")
    bmi_column, waist_column = st.columns(2)
    with bmi_column:
        _render_metric(result.bmi, title="BMI", unit="kg/m²")
    with waist_column:
        _render_metric(result.waist, title="허리둘레", unit="cm")


def _render_form(records: Sequence[ReferenceRecord], state: dict[str, Any]) -> None:
    """Collect required measurements and submit only validated input."""
    sexes, regions = _control_options(records)
    if not sexes:
        raise ValueError("성별 참조 범주를 찾을 수 없습니다.")

    st.header("측정값 입력")
    st.caption("필수 항목을 입력한 뒤 진단하기를 눌러 주세요. 지역은 선택 항목입니다.")
    with st.form("diagnosis.input.form"):
        sex = st.selectbox("성별 *", sexes, key="diagnosis.input.sex")
        age = st.number_input(
            "나이 * (세)",
            min_value=AGE_RANGE[0],
            max_value=AGE_RANGE[1],
            value=AGE_RANGE[0],
            step=1,
            format="%d",
            key="diagnosis.input.age",
        )
        height_cm = st.number_input(
            "키 * (cm)",
            min_value=float(HEIGHT_CM_RANGE[0]),
            max_value=float(HEIGHT_CM_RANGE[1]),
            value=170.0,
            step=0.1,
            key="diagnosis.input.height_cm",
        )
        weight_kg = st.number_input(
            "몸무게 * (kg)",
            min_value=float(WEIGHT_KG_RANGE[0]),
            max_value=float(WEIGHT_KG_RANGE[1]),
            value=65.0,
            step=0.1,
            key="diagnosis.input.weight_kg",
        )
        waist_cm = st.number_input(
            "허리둘레 * (cm)",
            min_value=float(WAIST_CM_RANGE[0]),
            max_value=float(WAIST_CM_RANGE[1]),
            value=80.0,
            step=0.1,
            key="diagnosis.input.waist_cm",
        )
        region = st.selectbox(
            "지역 (선택)",
            ["지역 미지정", *regions],
            key="diagnosis.input.region",
        )
        submitted = st.form_submit_button("진단하기", type="primary")

    if submitted:
        raw = _raw_input(
            sex,
            age,
            height_cm,
            weight_kg,
            waist_cm,
            None if region == "지역 미지정" else region,
        )
        validated, errors = validate_input(raw)
        state["errors"] = errors
        state["result"] = None
        if errors:
            _show_field_errors(errors)
            return
        assert validated is not None
        state["input"] = validated
        state["result"] = build_diagnostic(
            validated, records, seed=RANDOM_SEED
        )

    errors = state.get("errors", [])
    if errors and not submitted:
        _show_field_errors(errors)
    result = state.get("result")
    if result is not None:
        _render_result(result)


@app.guarded("진단")
def render_page() -> None:
    """Render the diagnosis page inside the shared error boundary."""
    app.initialize_session_state()
    state = app.page_state(PAGE_NAMESPACE)
    app.show_disclaimer()
    try:
        records, issues = app.load_cached_reference_data()
    except Exception:
        # Let the shared decorator render the actionable, traceback-free error.
        raise
    if issues:
        st.caption(f"참조 데이터 일부 행을 제외했습니다: {len(issues)}건")
    _render_form(records, state)


render_page()
