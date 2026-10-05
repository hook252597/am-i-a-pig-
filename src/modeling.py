"""Training-data preparation for reference-standard regression models."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeRegressor

from .models import EvaluationResult, ReferenceRecord

DEFAULT_FEATURES: tuple[str, ...] = (
    "measure_value", "age_min", "age_max", "sex_code", "region_code", "measure_type_code",
)
DEFAULT_TARGET = "percentile"
GROUP_COLUMNS: tuple[str, ...] = ("source", "source_row")


def _code_map(values: Iterable[Any]) -> dict[str, int]:
    normalized = {"" if value is None else str(value) for value in values}
    return {value: index for index, value in enumerate(sorted(normalized))}


def _record_rows(records: Sequence[ReferenceRecord]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        for percentile, measure_value in sorted(record.quantiles.items(), key=lambda item: float(item[0])):
            rows.append({
                "measure_type": record.measure_type,
                "sex": record.sex,
                "age_min": int(record.age_min),
                "age_max": int(record.age_max),
                "region": record.region,
                "measure_value": float(measure_value),
                "percentile": float(percentile),
                "source": str(record.source),
                "source_row": int(record.source_row),
            })
    return rows


def records_to_training_frame(
    records: Sequence[ReferenceRecord], *, target: str = DEFAULT_TARGET,
    feature_names: Sequence[str] = DEFAULT_FEATURES,
) -> pd.DataFrame:
    """Expand records to one long-format row per percentile.

    ``group_key`` is stable for all percentiles from one source row, allowing
    the evaluator to split by source row and prevent train/eval leakage.
    """
    features = tuple(feature_names)
    if target != DEFAULT_TARGET:
        raise ValueError(f"지원하는 target은 '{DEFAULT_TARGET}'뿐입니다: {target!r}")
    if target in features:
        raise ValueError("target은 feature 목록에 포함될 수 없습니다.")
    unknown = set(features) - set(DEFAULT_FEATURES)
    if unknown:
        raise ValueError(f"지원하지 않는 feature가 있습니다: {sorted(unknown)!r}")

    frame = pd.DataFrame(_record_rows(records))
    if frame.empty:
        columns = [
            "measure_type", "sex", "age_min", "age_max", "region", "measure_value",
            "percentile", "source", "source_row", "group_key", *features,
        ]
        return pd.DataFrame(columns=list(dict.fromkeys(columns)))

    sex_codes = _code_map(frame["sex"])
    region_codes = _code_map(frame["region"])
    measure_type_codes = _code_map(frame["measure_type"])
    frame["sex_code"] = frame["sex"].map(lambda value: sex_codes[str(value)])
    frame["region_code"] = frame["region"].map(
        lambda value: region_codes["" if pd.isna(value) else str(value)]
    )
    frame["measure_type_code"] = frame["measure_type"].map(
        lambda value: measure_type_codes[str(value)]
    )
    frame["group_key"] = frame.apply(
        lambda row: f"{row['source']}::{int(row['source_row'])}", axis=1
    )
    validate_group_keys(frame)
    ordered = [
        "measure_type", "sex", "age_min", "age_max", "region", "measure_value",
        "percentile", "source", "source_row", "group_key", *features,
    ]
    return frame.loc[:, list(dict.fromkeys(ordered))].reset_index(drop=True)


def validate_group_keys(frame: pd.DataFrame) -> None:
    """Validate the source-row identity required for leakage-safe splitting."""
    missing = [column for column in (*GROUP_COLUMNS, "group_key") if column not in frame.columns]
    if missing:
        raise ValueError(f"group split에 필요한 열이 없습니다: {missing!r}")
    if frame[list(GROUP_COLUMNS) + ["group_key"]].isna().any().any():
        raise ValueError("source, source_row, group_key는 비어 있을 수 없습니다.")
    expected = frame.apply(lambda row: f"{row['source']}::{int(row['source_row'])}", axis=1)
    if not frame["group_key"].astype(str).reset_index(drop=True).equals(expected.astype(str).reset_index(drop=True)):
        raise ValueError("group_key는 source와 source_row에서 결정적으로 생성되어야 합니다.")


build_training_frame = records_to_training_frame
reference_records_to_frame = records_to_training_frame

__all__ = [
    "DEFAULT_FEATURES", "DEFAULT_TARGET", "GROUP_COLUMNS", "records_to_training_frame",
    "build_training_frame", "reference_records_to_frame", "validate_group_keys",
    "MODEL_NAMES", "evaluate_models",
]


MODEL_NAMES: tuple[str, ...] = ("Linear Regression", "Decision Tree Regressor")


def _evaluation_split(frame: pd.DataFrame, *, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return one deterministic, source-row-grouped train/eval split."""
    if "group_key" in frame.columns:
        groups = frame["group_key"].astype(str).to_numpy()
    else:
        missing = [column for column in GROUP_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"group split에 필요한 열이 없습니다: {missing!r}")
        groups = (
            frame["source"].astype(str) + "::" + frame["source_row"].astype(str)
        ).to_numpy()

    unique_groups = pd.unique(groups)
    if len(unique_groups) < 2:
        return np.array([], dtype=int), np.arange(len(frame), dtype=int)

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
    train_idx, eval_idx = next(splitter.split(frame, groups=groups))
    return np.asarray(train_idx, dtype=int), np.asarray(eval_idx, dtype=int)


def _build_preprocessor(feature_names: tuple[str, ...], frame: pd.DataFrame) -> ColumnTransformer:
    """Create a transformer whose fit statistics are learned inside each pipeline."""
    categorical = [
        name for name in feature_names
        if not pd.api.types.is_numeric_dtype(frame[name])
    ]
    numeric = [name for name in feature_names if name not in categorical]
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(("numeric", StandardScaler(), numeric))
    if categorical:
        transformers.append(
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical)
        )
    return ColumnTransformer(transformers=transformers, remainder="drop")


def evaluate_models(
    frame: pd.DataFrame,
    *,
    target: str = DEFAULT_TARGET,
    seed: int = 42,
) -> list[EvaluationResult]:
    """Evaluate both regressors under one deterministic, leakage-safe split.

    The input frame is expected to be produced by ``records_to_training_frame``.
    Source rows are treated as groups so percentile rows from one reference row
    cannot be split between training and evaluation.  Each model receives its
    own pipeline, but both pipelines use the same rows, features, and seed.
    """
    feature_names = tuple(DEFAULT_FEATURES)
    if target not in frame.columns:
        raise ValueError(f"target 열이 없습니다: {target!r}")
    if target in feature_names:
        raise ValueError("target은 feature 목록에 포함될 수 없습니다.")
    missing = [name for name in feature_names if name not in frame.columns]
    if missing:
        raise ValueError(f"필수 feature 열이 없습니다: {missing!r}")
    if frame.empty:
        train_idx = np.array([], dtype=int)
        eval_idx = np.array([], dtype=int)
    else:
        train_idx, eval_idx = _evaluation_split(frame, seed=seed)

    y = pd.to_numeric(frame[target], errors="raise").to_numpy(dtype=float)
    reason: str | None = None
    if len(train_idx) < 1:
        reason = "학습 데이터가 없어 평가할 수 없습니다."
    elif len(eval_idx) < 2:
        reason = "evaluation set에 2개 이상의 행이 필요합니다."
    elif float(np.var(y[eval_idx])) == 0.0:
        reason = "evaluation target의 분산이 0이어서 평가할 수 없습니다."

    if reason is not None:
        return [
            EvaluationResult(
                model_name=model_name,
                target_name=target,
                feature_names=feature_names,
                y_true=(),
                y_pred=(),
                mae=None,
                r2=None,
                evaluable=False,
                reason=reason,
            )
            for model_name in MODEL_NAMES
        ]

    x_train = frame.iloc[train_idx].loc[:, feature_names]
    x_eval = frame.iloc[eval_idx].loc[:, feature_names]
    y_train = y[train_idx]
    y_eval = y[eval_idx]
    models = {
        "Linear Regression": LinearRegression(),
        "Decision Tree Regressor": DecisionTreeRegressor(random_state=seed),
    }
    results: list[EvaluationResult] = []
    for model_name in MODEL_NAMES:
        pipeline = Pipeline([
            ("preprocess", _build_preprocessor(feature_names, frame)),
            ("model", models[model_name]),
        ])
        pipeline.fit(x_train, y_train)
        predictions = np.asarray(pipeline.predict(x_eval), dtype=float)
        results.append(
            EvaluationResult(
                model_name=model_name,
                target_name=target,
                feature_names=feature_names,
                y_true=tuple(float(value) for value in y_eval),
                y_pred=tuple(float(value) for value in predictions),
                mae=float(mean_absolute_error(y_eval, predictions)),
                r2=float(r2_score(y_eval, predictions)),
                evaluable=True,
            )
        )
    return results
