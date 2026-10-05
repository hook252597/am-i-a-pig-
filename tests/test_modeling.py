from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import composite

from src.modeling import (
    DEFAULT_FEATURES,
    _evaluation_split,
    evaluate_models,
    records_to_training_frame,
    validate_group_keys,
)
from src.models import ReferenceRecord


def _records() -> list[ReferenceRecord]:
    return [
        ReferenceRecord(
            measure_type="bmi", sex="남성", age_min=20, age_max=24, region="전국",
            quantiles={1.0: 18.0, 50.0: 22.0, 99.0: 30.0},
            source="bmi.xlsx", source_row=2,
        ),
        ReferenceRecord(
            measure_type="waist", sex="여성", age_min=25, age_max=29, region=None,
            quantiles={1.0: 60.0, 50.0: 70.0, 99.0: 90.0},
            source="waist.xlsx", source_row=3,
        ),
    ]


def test_records_are_expanded_to_long_training_rows() -> None:
    frame = records_to_training_frame(_records())

    assert len(frame) == 6
    assert frame["percentile"].tolist() == [1.0, 50.0, 99.0, 1.0, 50.0, 99.0]
    assert set(DEFAULT_FEATURES).issubset(frame.columns)
    assert frame.loc[0, "measure_value"] == 18.0
    assert frame.loc[3, "measure_value"] == 60.0
    assert frame["region_code"].notna().all()


def test_percentile_is_target_and_never_a_feature() -> None:
    frame = records_to_training_frame(_records())

    assert "percentile" not in DEFAULT_FEATURES
    assert frame["percentile"].dtype.kind in "fi"
    with pytest.raises(ValueError, match="feature"):
        records_to_training_frame(_records(), feature_names=("measure_value", "percentile"))


def test_same_source_row_has_one_group_key_for_all_percentiles() -> None:
    frame = records_to_training_frame(_records())

    assert frame.groupby(["source", "source_row"], sort=False)["group_key"].nunique().tolist() == [1, 1]
    assert frame["group_key"].nunique() == 2
    validate_group_keys(frame)


def test_invalid_group_key_is_rejected() -> None:
    frame = records_to_training_frame(_records())
    frame.loc[0, "group_key"] = "wrong"

    with pytest.raises(ValueError, match="group_key"):
        validate_group_keys(frame)


def test_codes_are_deterministic_and_empty_records_keep_schema() -> None:
    first = records_to_training_frame(_records())
    second = records_to_training_frame(list(reversed(_records())))
    assert first.loc[0, "sex_code"] == second.loc[3, "sex_code"]
    assert first.loc[0, "region_code"] == second.loc[3, "region_code"]

    empty = records_to_training_frame([])
    assert set(DEFAULT_FEATURES).issubset(empty.columns)
    assert "percentile" in empty.columns


def test_evaluate_models_returns_both_models_with_shared_evaluation_rows() -> None:
    frame = records_to_training_frame(_records())

    results = evaluate_models(frame, seed=17)

    assert [result.model_name for result in results] == [
        "Linear Regression", "Decision Tree Regressor",
    ]
    assert all(result.evaluable for result in results)
    assert all(result.mae is not None and result.mae >= 0 for result in results)
    assert all(result.r2 is not None for result in results)
    assert results[0].y_true == results[1].y_true
    assert results[0].feature_names == results[1].feature_names == DEFAULT_FEATURES


def test_target_is_not_in_feature_names_or_pipeline_inputs() -> None:
    frame = records_to_training_frame(_records())

    results = evaluate_models(frame)

    assert all(result.target_name == "percentile" for result in results)
    assert all("percentile" not in result.feature_names for result in results)


def test_evaluation_with_fewer_than_two_eval_rows_is_unevaluable() -> None:
    records = [
        ReferenceRecord(
            measure_type="bmi", sex="남성", age_min=20, age_max=24, region="전국",
            quantiles={50.0: 22.0}, source="one.xlsx", source_row=1,
        ),
        ReferenceRecord(
            measure_type="bmi", sex="남성", age_min=25, age_max=29, region="전국",
            quantiles={50.0: 23.0}, source="one.xlsx", source_row=2,
        ),
    ]

    results = evaluate_models(records_to_training_frame(records), seed=3)

    assert all(not result.evaluable for result in results)
    assert all(result.mae is None and result.r2 is None for result in results)
    assert all(result.reason and "2개" in result.reason for result in results)


def test_zero_eval_target_variance_is_unevaluable() -> None:
    frame = records_to_training_frame(_records())
    frame["percentile"] = 50.0

    results = evaluate_models(frame, seed=17)

    assert all(not result.evaluable for result in results)
    assert all(result.mae is None and result.r2 is None for result in results)
    assert all(result.reason and "분산이 0" in result.reason for result in results)


def test_evaluation_is_reproducible_for_same_frame_and_seed() -> None:
    frame = records_to_training_frame(_records())

    first = evaluate_models(frame, seed=29)
    second = evaluate_models(frame.copy(), seed=29)

    assert first == second


@composite
def _evaluation_records(draw: st.DrawFn) -> list[ReferenceRecord]:
    """Generate several independent source-row groups with nonconstant targets."""
    group_count = draw(st.integers(min_value=6, max_value=12))
    base_values = draw(
        st.lists(
            st.integers(min_value=10, max_value=200),
            min_size=group_count,
            max_size=group_count,
            unique=True,
        )
    )
    return [
        ReferenceRecord(
            measure_type="bmi" if index % 2 == 0 else "waist",
            sex="남성" if index % 2 == 0 else "여성",
            age_min=20 + index,
            age_max=24 + index,
            region="전국" if index % 3 else None,
            quantiles={
                1.0: float(base),
                50.0: float(base + 10),
                99.0: float(base + 20),
            },
            source="generated.xlsx",
            source_row=index + 1,
        )
        for index, base in enumerate(base_values)
    ]


# Feature: fun-obesity-dashboard, Property 9: 모델 평가의 동일 조건·재현성·누수 방지
# Validates: Requirements 4.2, 4.3, 4.7
@given(records=_evaluation_records(), seed=st.integers(min_value=0, max_value=10_000))
@settings(max_examples=100, deadline=None)
def test_property_9_model_evaluation_is_reproducible_grouped_and_train_only(
    records: list[ReferenceRecord], seed: int
) -> None:
    frame = records_to_training_frame(records)
    original = frame.copy(deep=True)

    first = evaluate_models(frame, seed=seed)
    second = evaluate_models(frame.copy(deep=True), seed=seed)

    assert first == second
    assert all(result.evaluable for result in first)
    assert all(result.mae is not None and result.mae >= 0 for result in first)
    assert all(result.r2 is not None for result in first)
    assert all("percentile" not in result.feature_names for result in first)
    assert first[0].feature_names == first[1].feature_names == DEFAULT_FEATURES
    assert first[0].y_true == first[1].y_true

    train_idx, eval_idx = _evaluation_split(frame, seed=seed)
    train_groups = set(frame.iloc[train_idx]["group_key"])
    eval_groups = set(frame.iloc[eval_idx]["group_key"])
    assert train_groups.isdisjoint(eval_groups)
    assert len(eval_idx) >= 2

    # Changing only evaluation targets cannot affect a train-only fitted pipeline.
    changed_eval_target = frame.copy(deep=True)
    changed_eval_target.loc[eval_idx, "percentile"] = [1000.0 + i for i in range(len(eval_idx))]
    changed = evaluate_models(changed_eval_target, seed=seed)
    assert [result.y_pred for result in changed] == [result.y_pred for result in first]
    assert frame.equals(original)


@composite
def _unevaluable_frames(draw: st.DrawFn) -> tuple[list[ReferenceRecord], bool]:
    constant_target = draw(st.booleans())
    group_count = draw(
        st.integers(min_value=1, max_value=3 if constant_target else 1)
    )
    bases = draw(
        st.lists(
            st.integers(min_value=10, max_value=200),
            min_size=group_count,
            max_size=group_count,
            unique=True,
        )
    )
    records = [
        ReferenceRecord(
            measure_type="bmi",
            sex="남성",
            age_min=20 + index,
            age_max=24 + index,
            region="전국",
            quantiles=(
                {50.0: float(base)}
                if constant_target
                else {1.0: float(base), 50.0: float(base + 10), 99.0: float(base + 20)}
            ),
            source="unevaluable.xlsx",
            source_row=index + 1,
        )
        for index, base in enumerate(bases)
    ]
    return records, constant_target


# Feature: fun-obesity-dashboard, Property 10: 모델 평가 가능성과 지표 제약
# Validates: Requirements 4.4, 4.5
@given(case=_unevaluable_frames(), seed=st.integers(min_value=0, max_value=10_000))
@settings(max_examples=100, deadline=None)
def test_property_10_unevaluable_data_never_produces_scores(
    case: tuple[list[ReferenceRecord], bool], seed: int
) -> None:
    records, _constant_target = case
    results = evaluate_models(records_to_training_frame(records), seed=seed)

    assert len(results) == 2
    assert all(not result.evaluable for result in results)
    assert all(result.mae is None and result.r2 is None for result in results)
    assert all(result.y_true == () and result.y_pred == () for result in results)
    assert all(result.reason for result in results)
