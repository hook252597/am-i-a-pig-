"""Catalog size, safety, and deterministic selection tests."""

from __future__ import annotations

import random

import pytest
from hypothesis import given, strategies as st
from hypothesis import settings

import src.messages as messages_module
from src.errors import MessageConfigurationError
from src.messages import MESSAGE_CATALOG, choose_message, validate_message_catalog


EXPECTED_KEYS = {(metric, grade) for metric in ("bmi", "waist") for grade in range(1, 6)}


def test_catalog_has_all_ten_combinations_and_at_least_five_unique_messages() -> None:
    validate_message_catalog()
    assert set(MESSAGE_CATALOG) == EXPECTED_KEYS
    for candidates in MESSAGE_CATALOG.values():
        assert len(candidates) >= 5
        assert len(set(candidates)) == len(candidates)


def test_catalog_messages_are_safe() -> None:
    # Validation is the single safety policy used by production selection.
    validate_message_catalog()
    for candidates in MESSAGE_CATALOG.values():
        assert all(message.strip() for message in candidates)


@pytest.mark.parametrize(
    "bad_catalog",
    [
        {key: value for key, value in MESSAGE_CATALOG.items() if key != ("bmi", 1)},
        {**MESSAGE_CATALOG, ("bmi", 1): ("같은 멘트",) * 5},
        {**MESSAGE_CATALOG, ("bmi", 1): ("돼지처럼 달려요",) * 5},
    ],
)
def test_invalid_catalog_raises_message_configuration_error(bad_catalog: dict) -> None:
    with pytest.raises(MessageConfigurationError):
        validate_message_catalog(bad_catalog)


def test_same_seed_matches_random_choice_from_sorted_candidates() -> None:
    seed = 12345
    expected = random.Random(seed).choice(sorted(MESSAGE_CATALOG[("bmi", 3)]))
    assert choose_message("bmi", 3, seed=seed) == expected
    assert choose_message("bmi", 3, seed=seed) == expected


@pytest.mark.parametrize("measure_type", ["bmi", "waist"])
@pytest.mark.parametrize("grade", range(1, 6))
def test_selected_message_belongs_to_current_candidate_list(
    measure_type: str, grade: int
) -> None:
    selected = choose_message(measure_type, grade, seed=7)  # type: ignore[arg-type]
    assert selected in MESSAGE_CATALOG[(measure_type, grade)]


# Feature: fun-obesity-dashboard, Property 8: 안전한 멘트 선택의 재현성
# Validates: Requirements 3.5, 3.6
@settings(max_examples=100)
@given(
    measure_type=st.sampled_from(["bmi", "waist"]),
    grade=st.integers(min_value=1, max_value=5),
    seed=st.integers(),
)
def test_property_8_same_seed_is_deterministic_and_selection_stays_in_candidates(
    measure_type: str, grade: int, seed: int
) -> None:
    first = choose_message(measure_type, grade, seed=seed)  # type: ignore[arg-type]
    second = choose_message(measure_type, grade, seed=seed)  # type: ignore[arg-type]

    assert first == second
    assert first in MESSAGE_CATALOG[(measure_type, grade)]


# Feature: fun-obesity-dashboard, Property 8: 안전한 멘트 선택의 재현성
# Validates: Requirements 3.5, 3.6
@settings(max_examples=100)
@given(
    measure_type=st.sampled_from(["bmi", "waist"]),
    grade=st.integers(min_value=1, max_value=5),
    seed=st.integers(),
)
def test_property_8_unsafe_catalog_blocks_message_generation(
    measure_type: str,
    grade: int,
    seed: int,
) -> None:
    invalid_catalog = dict(MESSAGE_CATALOG)
    invalid_catalog[(measure_type, grade)] = (
        "돼지처럼 달려요",
        "안전한 후보 하나",
        "안전한 후보 둘",
        "안전한 후보 셋",
        "안전한 후보 넷",
    )
    patch = pytest.MonkeyPatch()
    patch.setattr(messages_module, "MESSAGE_CATALOG", invalid_catalog)
    try:
        with pytest.raises(MessageConfigurationError):
            choose_message(measure_type, grade, seed=seed)  # type: ignore[arg-type]
    finally:
        patch.undo()


# Feature: fun-obesity-dashboard, Property 8: 안전한 멘트 선택의 재현성
# Validates: Requirements 3.5, 3.6
@settings(max_examples=100)
@given(
    missing_key=st.tuples(
        st.sampled_from(["bmi", "waist"]),
        st.integers(min_value=1, max_value=5),
    ),
    seed=st.integers(),
)
def test_property_8_incomplete_catalog_blocks_message_generation(
    missing_key: tuple[str, int], seed: int
) -> None:
    incomplete_catalog = {
        key: candidates
        for key, candidates in MESSAGE_CATALOG.items()
        if key != missing_key
    }
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(messages_module, "MESSAGE_CATALOG", incomplete_catalog)
        with pytest.raises(MessageConfigurationError):
            choose_message(*missing_key, seed=seed)  # type: ignore[arg-type]
