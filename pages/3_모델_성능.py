"""Model-performance page for the two educational regression models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - exercised only without UI dependencies
    st = None  # type: ignore[assignment]

from app import (
    APP_TITLE,
    error_boundary,
    initialize_session_state,
    load_cached_reference_data,
    page_state,
    show_disclaimer,
)
from src.config import RANDOM_SEED
from src.modeling import DEFAULT_FEATURES, DEFAULT_TARGET, evaluate_models, records_to_training_frame
from src.models import EvaluationResult
from src.visualization import actual_vs_predicted, residual_chart


MODEL_HYPERPARAMETERS: dict[str, str] = {
    "Linear Regression": "기본 설정 (fit_intercept=True)",
    "Decision Tree Regressor": f"random_state={RANDOM_SEED}, max_depth=None",
}


def _evaluation_table(results: Sequence[EvaluationResult]) -> pd.DataFrame:
    """Build the display-only score table from evaluation service results."""
    return pd.DataFrame(
        [
            {
                "모델": result.model_name,
                "MAE": result.mae,
                "R²": result.r2,
            }
            for result in results
            if result.evaluable
        ],
        columns=["모델", "MAE", "R²"],
    )


def _sample_counts(frame: pd.DataFrame, results: Sequence[EvaluationResult]) -> tuple[int, int | None]:
    """Return train/eval row counts without reproducing the evaluator's split."""
    evaluated = next((result for result in results if result.evaluable), None)
    if evaluated is None:
        return len(frame), None
    evaluation_rows = len(evaluated.y_true)
    return len(frame) - evaluation_rows, evaluation_rows


def _render_configuration(frame: pd.DataFrame, results: Sequence[EvaluationResult]) -> None:
    """Show target, features, split counts, seed, and model settings."""
    train_count, eval_count = _sample_counts(frame, results)
    st.subheader("평가 설정")
    columns = st.columns(4)
    columns[0].metric("학습 표본 수", f"{train_count:,}행")
    columns[1].metric(
        "평가 표본 수",
        f"{eval_count:,}행" if eval_count is not None else "평가 불가",
    )
    columns[2].metric("고정 seed", str(RANDOM_SEED))
    columns[3].metric("target", DEFAULT_TARGET)

    st.write("**feature**: " + ", ".join(DEFAULT_FEATURES))
    st.caption("target은 feature에서 제외되며, 두 모델은 같은 평가 행과 train-only 전처리를 사용합니다.")
    settings = pd.DataFrame(
        [
            {"모델": name, "하이퍼파라미터": hyperparameters}
            for name, hyperparameters in MODEL_HYPERPARAMETERS.items()
        ]
    )
    st.dataframe(settings, hide_index=True, use_container_width=True)


def _render_unavailable(results: Sequence[EvaluationResult]) -> None:
    """Explain why scores and comparisons are intentionally absent."""
    reasons = sorted({result.reason for result in results if result.reason})
    reason = " / ".join(reasons) or "평가 조건을 충족하지 못했습니다."
    st.warning(f"모델 평가를 사용할 수 없습니다: {reason}")
    st.info("평가 불가 상태에서는 MAE·R² 점수와 모델 비교를 표시하지 않습니다. 평가 표본과 target 분산을 확인해 주세요.")


def _render_charts(results: Sequence[EvaluationResult]) -> None:
    """Render both Plotly charts for every evaluated model."""
    st.subheader("실제값 대 예측값")
    actual_columns = st.columns(len(results))
    for column, result in zip(actual_columns, results):
        with column:
            st.plotly_chart(actual_vs_predicted(result), use_container_width=True)

    st.subheader("잔차")
    residual_columns = st.columns(len(results))
    for column, result in zip(residual_columns, results):
        with column:
            st.plotly_chart(residual_chart(result), use_container_width=True)


def render_page() -> None:
    """Render the model comparison page using only public service helpers."""
    initialize_session_state()
    state = page_state("model")
    state["last_target"] = DEFAULT_TARGET
    st.set_page_config(page_title=f"모델 성능 | {APP_TITLE}", page_icon="📈", layout="wide")
    st.title("모델 성능")
    st.caption("참조표준 분위수 위치를 추정하는 두 교육·탐색 모델의 동일 조건 비교")
    show_disclaimer()

    with error_boundary("모델 성능"):
        records, row_issues = load_cached_reference_data()
        frame = records_to_training_frame(records, target=DEFAULT_TARGET)
        results = evaluate_models(frame, target=DEFAULT_TARGET, seed=RANDOM_SEED)

        _render_configuration(frame, results)
        if row_issues:
            st.caption(f"참조 데이터에서 제외된 행: {len(row_issues):,}개")

        if not results or not all(result.evaluable for result in results):
            _render_unavailable(results)
            return

        st.subheader("모델 평가 점수")
        st.dataframe(_evaluation_table(results), hide_index=True, use_container_width=True)
        st.caption("MAE는 작을수록 좋고, R²는 평가 데이터에 따라 달라질 수 있습니다. 숫자만으로 의료적 의미를 판단하지 마세요.")
        _render_charts(results)


if st is not None:
    render_page()
