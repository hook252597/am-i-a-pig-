from __future__ import annotations

import pandas as pd
from hypothesis import given, settings, strategies as st

from src.models import EvaluationResult, MetricResult
from src.visualization import (
    actual_vs_predicted,
    eda_distribution,
    metric_bar,
    percentile_gauge,
    residual_chart,
)


def _metric(percentile: float = 42.5) -> MetricResult:
    return MetricResult.calculated(
        "bmi", 22.0, percentile, 3, "😎", "균형 잡힌 구간", "차분히 살펴봐요"
    )


def test_percentile_gauge_has_fixed_range_and_original_value() -> None:
    figure = percentile_gauge(_metric(42.5))

    indicator = figure.data[0]
    assert indicator.type == "indicator"
    assert indicator.value == 42.5
    assert indicator.gauge.axis.range == (0, 100)


def test_metric_bar_has_bounded_axis_and_metric_label() -> None:
    figure = metric_bar(_metric(77.0), title="BMI 백분위")

    bar = figure.data[0]
    assert bar.type == "bar"
    assert list(bar.x) == [77.0]
    assert bar.name == "BMI 백분위"
    assert figure.layout.xaxis.range == (0, 100)


def test_eda_distribution_has_histogram_trace() -> None:
    figure = eda_distribution(pd.DataFrame({"measure_value": [18.0, 22.0, 28.0]}))

    assert len(figure.data) == 1
    assert figure.data[0].type == "histogram"
    assert list(figure.data[0].x) == [18.0, 22.0, 28.0]


def test_model_charts_connect_trace_to_model_label() -> None:
    result = EvaluationResult(
        model_name="Linear Regression",
        target_name="percentile",
        feature_names=("measure_value",),
        y_true=(10.0, 20.0),
        y_pred=(11.0, 19.0),
        mae=1.0,
        r2=0.96,
        evaluable=True,
    )

    actual = actual_vs_predicted(result)
    residual = residual_chart(result)
    assert actual.data[0].name == "Linear Regression"
    assert list(actual.data[0].x) == [10.0, 20.0]
    assert list(actual.data[0].y) == [11.0, 19.0]
    assert residual.data[0].name == "Linear Regression residual"
    assert list(residual.data[0].y) == [-1.0, 1.0]


def test_unavailable_metric_returns_explanatory_placeholder() -> None:
    result = MetricResult.unavailable("waist", 80.0, "REFERENCE_GROUP_NOT_FOUND")

    gauge = percentile_gauge(result)
    bar = metric_bar(result)
    assert len(gauge.data) == 0
    assert len(bar.data) == 0
    assert "계산 불가" in gauge.layout.annotations[0].text
    assert "REFERENCE_GROUP_NOT_FOUND" in bar.layout.annotations[0].text


def test_unevaluable_model_returns_explanatory_placeholder() -> None:
    result = EvaluationResult(
        model_name="Decision Tree Regressor",
        target_name="percentile",
        feature_names=("measure_value",),
        y_true=(),
        y_pred=(),
        mae=None,
        r2=None,
        evaluable=False,
        reason="평가 행이 부족합니다.",
    )

    figure = actual_vs_predicted(result)
    assert len(figure.data) == 0
    assert "평가 불가" in figure.layout.annotations[0].text
    assert result.model_name in figure.layout.annotations[0].text


# Feature: fun-obesity-dashboard, Property 13: 시각화 값 일치·범위 보존과 모델 trace 라벨
# Validates: Requirements 5.3, 5.6
@settings(max_examples=100, deadline=None)
@given(
    percentile=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    y_values=st.lists(
        st.floats(min_value=-1_000.0, max_value=1_000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=8,
    ),
    residual_offsets=st.lists(
        st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=8,
    ),
    unavailable=st.booleans(),
    model_name=st.sampled_from(("Linear Regression", "Decision Tree Regressor")),
)
def test_property_13_visualization_preserves_values_and_model_trace_labels(
    percentile: float,
    y_values: list[float],
    residual_offsets: list[float],
    unavailable: bool,
    model_name: str,
) -> None:
    """Generated result values remain bounded and trace labels stay connected."""
    if unavailable:
        metric = MetricResult.unavailable("waist", 80.0, "REFERENCE_GROUP_NOT_FOUND")
        gauge = percentile_gauge(metric)
        bar = metric_bar(metric)
        assert len(gauge.data) == 0
        assert len(bar.data) == 0
        assert gauge.layout.annotations
        assert bar.layout.annotations
    else:
        metric = _metric(percentile)
        gauge = percentile_gauge(metric)
        bar = metric_bar(metric)
        indicator = gauge.data[0]
        numeric_bar = bar.data[0]
        assert indicator.value == percentile
        assert 0.0 <= indicator.value <= 100.0
        assert list(numeric_bar.x) == [percentile]
        assert 0.0 <= numeric_bar.x[0] <= 100.0
        assert list(numeric_bar.customdata) == [percentile]
        assert gauge.data[0].gauge.axis.range == (0, 100)
        assert bar.layout.xaxis.range == (0, 100)

    size = min(len(y_values), len(residual_offsets))
    actual_values = tuple(y_values[:size])
    predicted_values = tuple(
        actual - offset for actual, offset in zip(actual_values, residual_offsets[:size])
    )
    result = EvaluationResult(
        model_name=model_name,
        target_name="percentile",
        feature_names=("measure_value",),
        y_true=actual_values,
        y_pred=predicted_values,
        mae=1.0,
        r2=0.5,
        evaluable=True,
    )

    actual = actual_vs_predicted(result)
    residual = residual_chart(result)
    actual_trace = actual.data[0]
    residual_trace = residual.data[0]
    assert actual_trace.name == model_name
    assert actual_trace.legendgroup == model_name
    assert list(actual_trace.x) == list(actual_values)
    assert list(actual_trace.y) == list(predicted_values)
    assert list(actual_trace.customdata) == [model_name] * size
    assert residual_trace.name == f"{model_name} residual"
    assert residual_trace.legendgroup == model_name
    expected_residuals = [
        actual - predicted for actual, predicted in zip(actual_values, predicted_values)
    ]
    assert list(residual_trace.y) == expected_residuals
    assert list(residual_trace.customdata) == [model_name] * size
