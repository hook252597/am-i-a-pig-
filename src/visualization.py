"""Plotly figures for diagnosis, EDA, and model evaluation.

This module is deliberately a rendering boundary: percentile, grade, and model
metrics are calculated elsewhere and are only read from the shared result
contracts here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import plotly.graph_objects as go

from .models import EvaluationResult, MetricResult


def _placeholder(message: str, *, title: str | None = None) -> go.Figure:
    """Return an explanatory figure without a misleading numeric trace."""
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        align="center",
    )
    figure.update_layout(title=title, template="plotly_white")
    return figure


def _metric_value(result: MetricResult) -> float | None:
    """Read and safely bound a calculated metric's percentile for display."""
    if result.error is not None or result.percentile is None:
        return None
    # The model contract validates this already; keep the renderer defensive.
    return max(0.0, min(100.0, float(result.percentile)))


def percentile_gauge(result: MetricResult, *, title: str | None = None) -> go.Figure:
    """Render one metric percentile as a 0--100 Plotly gauge."""
    value = _metric_value(result)
    metric_title = title or result.measure_type.upper()
    if value is None:
        reason = result.error or "분위수 결과를 사용할 수 없습니다."
        return _placeholder(
            f"{metric_title}: 계산 불가\n{reason}", title=metric_title
        )

    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": metric_title},
            gauge={"axis": {"range": [0, 100]}},
        )
    )
    figure.update_layout(template="plotly_white")
    return figure


def metric_bar(result: MetricResult, *, title: str | None = None) -> go.Figure:
    """Render one metric percentile as a horizontal 0--100 bar."""
    value = _metric_value(result)
    metric_title = title or result.measure_type.upper()
    if value is None:
        reason = result.error or "분위수 결과를 사용할 수 없습니다."
        return _placeholder(
            f"{metric_title}: 계산 불가\n{reason}", title=metric_title
        )

    figure = go.Figure(
        go.Bar(
            x=[value],
            y=[metric_title],
            name=metric_title,
            orientation="h",
            customdata=[result.percentile],
            hovertemplate="%{y}: %{x:.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        template="plotly_white",
        xaxis={"range": [0, 100], "title": "백분위"},
        yaxis={"title": None},
    )
    return figure


def eda_distribution(
    frame: Any,
    *,
    value_column: str = "measure_value",
    title: str = "측정값 분포",
) -> go.Figure:
    """Render an EDA distribution from a prepared tabular frame.

    EDA input is intentionally kept separate from calculation results because
    it describes source rows rather than a diagnosis or model evaluation.
    """
    if frame is None or not hasattr(frame, "columns"):
        return _placeholder("분포 데이터를 사용할 수 없습니다.", title=title)
    if value_column not in frame.columns:
        return _placeholder(
            f"분포 데이터를 사용할 수 없습니다. '{value_column}' 열이 없습니다.",
            title=title,
        )

    values = frame[value_column].dropna()
    if len(values) == 0:
        return _placeholder("분포 데이터가 비어 있습니다.", title=title)

    figure = go.Figure(go.Histogram(x=values.tolist(), name=value_column))
    figure.update_layout(template="plotly_white", title=title, xaxis_title=value_column)
    return figure


def model_scatter(
    result: EvaluationResult,
    *,
    chart: str = "actual-vs-predicted",
) -> go.Figure:
    """Render actual/predicted or residual values for one evaluated model."""
    if not result.evaluable:
        return _placeholder(
            f"{result.model_name}: 평가 불가\n{result.reason or '평가 조건을 충족하지 못했습니다.'}",
            title=result.model_name,
        )

    label = result.model_name
    if chart in {"residual", "residuals"}:
        residuals = [actual - predicted for actual, predicted in zip(result.y_true, result.y_pred)]
        trace = go.Scatter(
            x=list(range(len(residuals))),
            y=residuals,
            mode="markers",
            name=f"{label} residual",
            legendgroup=label,
            customdata=[label] * len(residuals),
            hovertemplate="%{y:.4f}<extra>%{customdata}</extra>",
        )
        figure = go.Figure(trace)
        figure.update_layout(
            template="plotly_white",
            title=f"{label} 잔차",
            xaxis_title="평가 행",
            yaxis_title="실제값 - 예측값",
        )
        return figure

    trace = go.Scatter(
        x=list(result.y_true),
        y=list(result.y_pred),
        mode="markers",
        name=label,
        legendgroup=label,
        customdata=[label] * len(result.y_true),
        hovertemplate="실제값=%{x:.4f}<br>예측값=%{y:.4f}<extra>%{customdata}</extra>",
    )
    figure = go.Figure(trace)
    figure.update_layout(
        template="plotly_white",
        title=f"{label}: 실제값-예측값",
        xaxis_title="실제값",
        yaxis_title="예측값",
    )
    return figure


def actual_vs_predicted(result: EvaluationResult) -> go.Figure:
    """Explicit alias for the model actual-vs-predicted chart."""
    return model_scatter(result, chart="actual-vs-predicted")


def residual_chart(result: EvaluationResult) -> go.Figure:
    """Explicit alias for the model residual chart."""
    return model_scatter(result, chart="residual")


__all__ = [
    "percentile_gauge",
    "metric_bar",
    "eda_distribution",
    "model_scatter",
    "actual_vs_predicted",
    "residual_chart",
]
