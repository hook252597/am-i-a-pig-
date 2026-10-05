"""Streamlit entry point and shared application boundaries.

Page modules should use the helpers in this module for common setup, reference
-data loading, state namespaces, and user-facing error handling.  This keeps
page state independent and prevents implementation details (including raw
tracebacks and personal measurements) from reaching the UI or logs.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

try:
    import streamlit as st
except ModuleNotFoundError:  # Keep pure app helpers testable before UI dependencies install.
    class _StreamlitFallback:
        session_state: dict[str, Any] = {}

        @staticmethod
        def cache_data(*, show_spinner: bool = False) -> Callable[[Callable[..., T]], Callable[..., T]]:
            del show_spinner

            def decorate(function: Callable[..., T]) -> Callable[..., T]:
                return function

            return decorate

        def __getattr__(self, name: str) -> Any:
            raise ModuleNotFoundError(
                "Streamlit is required to run the dashboard UI; install requirements.txt first."
            )

    st = _StreamlitFallback()

from src.config import DISCLAIMER, GRADE_BANDS, INPUT_RANGES, PERCENTILES, RANDOM_SEED, REGION_FALLBACKS
from src.data_loader import load_reference_data
from src.errors import DashboardError, DataPreparationError
from src.models import ReferenceRecord, RowIssue

LOGGER = logging.getLogger(__name__)

APP_TITLE = "재미있는 비만도 진단 대시보드"
PAGE_OPTIONS: tuple[str, ...] = ("진단", "데이터 탐색 EDA", "모델 성능")
PAGE_NAMESPACES: tuple[str, ...] = ("diagnosis", "eda", "model")
DATA_DIR = Path(__file__).resolve().parent / "data"
BMI_PATH = DATA_DIR / "한국인_비만지수(체질량지수)_참조표준.xlsx"
WAIST_PATH = DATA_DIR / "한국인_비만지수(허리둘레)_참조표준.xlsx"

# Only policy/configuration values belong in this fingerprint.  User input is
# deliberately excluded from the loader cache and from all diagnostic logs.
LOADER_CONFIG: tuple[Any, ...] = (
    PERCENTILES,
    REGION_FALLBACKS,
    RANDOM_SEED,
    tuple(sorted(INPUT_RANGES.items())),
    GRADE_BANDS,
)

T = TypeVar("T")


def file_fingerprint(path: str | Path) -> tuple[str, int | None]:
    """Return a stable path/mtime key, including missing-file state."""
    resolved = Path(path).resolve()
    try:
        modified_ns: int | None = resolved.stat().st_mtime_ns
    except OSError:
        modified_ns = None
    return str(resolved), modified_ns


def loader_cache_key(
    bmi_path: str | Path = BMI_PATH,
    waist_path: str | Path = WAIST_PATH,
    *,
    config: tuple[Any, ...] = LOADER_CONFIG,
) -> tuple[tuple[str, int | None], tuple[str, int | None], tuple[Any, ...]]:
    """Build the explicit cache identity used by ``cached_reference_data``."""
    return file_fingerprint(bmi_path), file_fingerprint(waist_path), config


@st.cache_data(show_spinner=False)
def cached_reference_data(
    bmi_path: str,
    waist_path: str,
    bmi_mtime_ns: int | None,
    waist_mtime_ns: int | None,
    loader_config: tuple[Any, ...],
) -> tuple[list[ReferenceRecord], list[RowIssue]]:
    """Load reference data with paths, mtimes, and policy in the cache key.

    The mtime arguments are intentionally consumed by the function signature;
    they ensure a changed workbook cannot reuse an old normalized result.
    """
    del bmi_mtime_ns, waist_mtime_ns, loader_config
    return load_reference_data(bmi_path, waist_path)


def load_cached_reference_data(
    bmi_path: str | Path = BMI_PATH,
    waist_path: str | Path = WAIST_PATH,
    *,
    config: tuple[Any, ...] = LOADER_CONFIG,
) -> tuple[list[ReferenceRecord], list[RowIssue]]:
    """Resolve the cache fingerprint and load both reference workbooks."""
    (bmi_key, waist_key, config_key) = loader_cache_key(
        bmi_path, waist_path, config=config
    )
    return cached_reference_data(
        bmi_key[0], waist_key[0], bmi_key[1], waist_key[1], config_key
    )


def initialize_session_state() -> None:
    """Create independent state buckets for each page namespace."""
    for namespace in PAGE_NAMESPACES:
        key = f"{namespace}.state"
        if key not in st.session_state:
            st.session_state[key] = {}


def page_state(namespace: str) -> dict[str, Any]:
    """Return a page-local state dictionary and reject unknown namespaces."""
    if namespace not in PAGE_NAMESPACES:
        raise ValueError(f"알 수 없는 페이지 namespace입니다: {namespace}")
    initialize_session_state()
    return st.session_state[f"{namespace}.state"]


def show_disclaimer() -> None:
    """Render the one disclaimer shared by every result surface."""
    st.info(DISCLAIMER)


def configure_app() -> None:
    """Apply common Streamlit configuration and initialize page state."""
    st.set_page_config(page_title=APP_TITLE, page_icon="🐷", layout="wide")
    initialize_session_state()
    st.title(APP_TITLE)
    st.caption("참조표준 기반의 재미있는 상대 위치 안내")
    show_disclaimer()


def render_navigation() -> str:
    """Render common navigation and store only navigation-local state."""
    selected = st.sidebar.radio("페이지", PAGE_OPTIONS, key="navigation.page")
    st.sidebar.caption("페이지별 입력과 오류 상태는 서로 독립적으로 유지됩니다.")
    return selected


def _safe_error_message(error: Exception, *, area: str) -> str:
    """Map known failures to actionable text without exposing internals."""
    if isinstance(error, DataPreparationError):
        return f"{area} 데이터를 준비하지 못했습니다. data/ 폴더의 참조 파일과 열 구성을 확인한 뒤 다시 시도해 주세요."
    if isinstance(error, DashboardError):
        return f"{area}을 처리하지 못했습니다. 입력과 참조 데이터 조건을 확인한 뒤 다시 시도해 주세요."
    return f"{area} 중 문제가 발생했습니다. 잠시 후 다시 시도하거나 관리자에게 데이터 구성을 확인해 달라고 요청해 주세요."


def show_user_error(error: Exception, *, area: str) -> None:
    """Display an actionable error while keeping traceback and inputs private."""
    LOGGER.error("Dashboard operation failed in area=%s; user details omitted", area)
    st.error(_safe_error_message(error, area=area))


@contextmanager
def error_boundary(area: str) -> Iterator[None]:
    """Convert page/data exceptions to local user-facing messages."""
    try:
        yield
    except Exception as error:  # page boundary must also cover third-party errors
        show_user_error(error, area=area)


def guarded(area: str) -> Callable[[Callable[..., T]], Callable[..., T | None]]:
    """Decorator form of :func:`error_boundary` for page callbacks."""
    def decorate(function: Callable[..., T]) -> Callable[..., T | None]:
        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> T | None:
            with error_boundary(area):
                return function(*args, **kwargs)
            return None
        return wrapped
    return decorate


def main() -> None:
    """Initialize the shell and eagerly validate reference data availability."""
    configure_app()
    render_navigation()
    with error_boundary("참조 데이터 초기화"):
        load_cached_reference_data()


if __name__ == "__main__":
    main()
