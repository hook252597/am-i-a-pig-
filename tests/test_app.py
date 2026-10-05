from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import app
from src.errors import DataPreparationError, ErrorCode
from src.models import EvaluationResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _page(pattern: str) -> str:
    return str(next((PROJECT_ROOT / "pages").glob(pattern)))


def _run_page(pattern: str) -> AppTest:
    return AppTest.from_file(_page(pattern)).run()


def _all_values(at: AppTest) -> list[str]:
    values: list[str] = []
    for collection_name in ("title", "header", "subheader", "caption", "info", "warning", "error", "success"):
        values.extend(str(element.value) for element in getattr(at, collection_name))
    return values


def test_loader_cache_key_includes_paths_mtimes_and_configuration(tmp_path: Path) -> None:
    bmi = tmp_path / "bmi.xlsx"
    waist = tmp_path / "waist.xlsx"
    bmi.write_bytes(b"bmi")
    waist.write_bytes(b"waist")

    first = app.loader_cache_key(bmi, waist, config=("policy", 1))
    second = app.loader_cache_key(bmi, waist, config=("policy", 2))

    assert first[0][0] == str(bmi.resolve())
    assert first[1][0] == str(waist.resolve())
    assert first[0][1] is not None
    assert first[1][1] is not None
    assert first != second


def test_missing_file_fingerprint_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "missing.xlsx"

    fingerprint = app.file_fingerprint(path)

    assert fingerprint == (str(path.resolve()), None)


def test_page_state_namespaces_are_distinct() -> None:
    diagnosis = app.page_state("diagnosis")
    eda = app.page_state("eda")
    model = app.page_state("model")
    diagnosis["input"] = "diagnosis-only"

    assert eda == {}
    assert model == {}
    assert app.page_state("diagnosis")["input"] == "diagnosis-only"


def test_safe_error_message_is_actionable_without_exception_details() -> None:
    error = DataPreparationError(
        "raw workbook traceback and personal input",
        code=ErrorCode.FILE_UNREADABLE,
        details={"personal_input": "should-not-display"},
    )

    message = app._safe_error_message(error, area="참조 데이터")

    assert "data/" in message
    assert "raw workbook" not in message
    assert "personal_input" not in message
    assert "traceback" not in message.lower()


def test_common_disclaimer_is_the_configured_policy() -> None:
    assert app.DISCLAIMER == "의료진단이 아니며 의료적 판단을 대체하지 않는다"


def test_app_navigation_exposes_all_three_pages() -> None:
    at = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()

    assert not at.exception
    assert at.radio[0].label == "페이지"
    assert at.radio[0].options == list(app.PAGE_OPTIONS)
    assert set(app.PAGE_OPTIONS) == {"진단", "데이터 탐색 EDA", "모델 성능"}
    assert app.DISCLAIMER in _all_values(at)


def test_diagnosis_page_renders_inputs_charts_and_partial_calculation_boundary() -> None:
    at = _run_page("1_*.py")

    assert not at.exception
    assert at.header[0].value == "측정값 입력"
    assert [control.label for control in at.selectbox] == ["성별 *", "지역 (선택)"]
    assert [control.label for control in at.number_input] == [
        "나이 * (세)",
        "키 * (cm)",
        "몸무게 * (kg)",
        "허리둘레 * (cm)",
    ]
    assert at.button[0].label == "진단하기"

    # Age 20 matches the reference age ranges and produces a usable BMI result.
    at.number_input[0].set_value(20)
    at.button[0].click().run()

    assert not at.exception
    assert "진단 결과" in [element.value for element in at.header]
    assert len(at.get("plotly_chart")) == 4
    assert any("BMI 표시값" == metric.label for metric in at.metric)
    assert any("허리둘레 계산 불가" in warning.value for warning in at.warning)
    assert app.DISCLAIMER in _all_values(at)


def test_eda_page_renders_quality_summary_categories_and_distribution_charts() -> None:
    at = _run_page("2_*.py")

    assert not at.exception
    assert at.title[0].value == "데이터 탐색 EDA"
    assert {item.value for item in at.subheader} >= {
        "파일별 데이터 품질",
        "참조 범주",
        "분위수·참조 측정값 분포",
        "행 유효성 요약",
    }
    assert len(at.dataframe) >= 3
    assert len(at.get("plotly_chart")) >= 1
    assert at.selectbox[0].label == "분포 지표"
    assert app.DISCLAIMER in _all_values(at)


def test_model_page_renders_scores_configuration_and_model_charts() -> None:
    at = _run_page("3_*.py")

    assert not at.exception
    assert at.title[0].value == "모델 성능"
    assert {item.value for item in at.subheader} >= {
        "평가 설정",
        "모델 평가 점수",
        "실제값 대 예측값",
        "잔차",
    }
    assert len(at.dataframe) == 2
    assert len(at.get("plotly_chart")) == 4
    assert app.DISCLAIMER in _all_values(at)


def test_eda_error_boundary_shows_safe_actionable_message_without_traceback() -> None:
    error = DataPreparationError(
        "private workbook details",
        code=ErrorCode.FILE_UNREADABLE,
        details={"secret": "must not be rendered"},
    )
    with patch("app.load_cached_reference_data", side_effect=error):
        at = _run_page("2_*.py")

    assert not at.exception
    assert len(at.error) == 1
    message = at.error[0].value
    assert "EDA 데이터 탐색 데이터를 준비하지 못했습니다" in message
    assert "private workbook details" not in message
    assert "secret" not in message
    assert "Traceback" not in message


def test_model_page_shows_calculation_unavailable_without_scores_or_charts() -> None:
    unavailable = [
        EvaluationResult(
            model_name=name,
            target_name="percentile",
            feature_names=("measure_value",),
            y_true=(),
            y_pred=(),
            mae=None,
            r2=None,
            evaluable=False,
            reason="평가 표본이 2개 미만입니다.",
        )
        for name in ("Linear Regression", "Decision Tree Regressor")
    ]
    with patch("src.modeling.evaluate_models", return_value=unavailable):
        at = _run_page("3_*.py")

    assert not at.exception
    assert any("모델 평가를 사용할 수 없습니다" in item.value for item in at.warning)
    assert len(at.get("plotly_chart")) == 0
    assert not any(item.label == "MAE" for item in at.metric)
    assert app.DISCLAIMER in _all_values(at)
