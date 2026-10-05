"""Safe, deterministic message catalog for metric grade results."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Final

from .errors import ErrorCode, MessageConfigurationError
from .models import MeasureType

# These terms cover insults, stigma, appearance judgements, and clinical fear
# language.  The catalog is intentionally conservative: messages are playful
# descriptions of progress, not judgements about a person's body or health.
_FORBIDDEN_TERMS: Final[tuple[str, ...]] = (
    "병신",
    "등신",
    "바보",
    "멍청",
    "돼지",
    "뚱뚱",
    "뚱보",
    "살쪘",
    "게으르",
    "못생",
    "몸매",
    "외모",
    "혐오",
    "죽어",
    "죽음",
    "암",
    "당뇨",
    "고혈압",
    "질병",
    "진단",
    "치료",
    "위험",
    "공포",
    "무섭",
    "심각",
)

# A tuple per key prevents accidental duplicate entries while retaining an
# easy-to-review, immutable default catalog.  Keys are deliberately explicit
# so a missing metric/grade cannot be silently filled by another combination.
MESSAGE_CATALOG: Final[dict[tuple[MeasureType, int], tuple[str, ...]]] = {
    (metric, grade): tuple(
        messages
    )
    for metric, messages_by_grade in {
        "bmi": {
            1: (
                "가벼운 리듬으로 오늘을 열어봐요.",
                "작은 움직임이 산뜻한 출발을 만들어요.",
                "오늘의 균형 감각이 기분 좋은 신호예요.",
                "천천히 시작해도 충분히 멋진 하루예요.",
                "나에게 맞는 속도로 즐겁게 출발해요.",
            ),
            2: (
                "차분한 흐름이 보기 좋게 이어지고 있어요.",
                "꾸준한 리듬이 오늘도 든든한 힘이 돼요.",
                "편안한 페이스로 좋은 흐름을 이어가요.",
                "작은 습관들이 안정적인 박자를 만들어요.",
                "지금의 균형을 가볍게 즐겨보세요.",
            ),
            3: (
                "균형 감각이 멋지게 빛나는 구간이에요.",
                "오늘도 내 리듬을 여유롭게 관찰해요.",
                "알맞은 속도와 편안한 흐름을 응원해요.",
                "몸과 일상의 박자를 함께 살펴봐요.",
                "나만의 균형점을 찾아가는 중이에요.",
            ),
            4: (
                "생활 리듬을 한 번 더 다정하게 살펴봐요.",
                "작은 루틴 하나가 기분 좋은 변화를 만들어요.",
                "내일의 편안함을 위해 오늘을 가볍게 챙겨요.",
                "잠깐 멈춰 내 페이스를 조율해볼까요.",
                "무리하지 않고 좋은 습관을 하나 골라봐요.",
            ),
            5: (
                "오늘의 생활 습관을 차분히 돌아보는 시간이에요.",
                "작은 선택부터 나를 위한 리듬을 만들어봐요.",
                "편안한 일상을 위해 한 가지 습관을 살펴봐요.",
                "내 페이스에 맞는 건강한 루틴을 찾아봐요.",
                "부담 없이 다음 한 걸음을 계획해보세요.",
            ),
        },
        "waist": {
            1: (
                "산뜻한 생활 리듬으로 오늘을 시작해요.",
                "가벼운 움직임이 즐거운 하루를 열어줘요.",
                "편안한 페이스가 좋은 기분을 더해줘요.",
                "오늘도 나에게 맞는 속도로 걸어가요.",
                "작은 활동 하나로 기분 좋은 출발을 만들어봐요.",
            ),
            2: (
                "꾸준한 일상이 안정적인 흐름을 보여줘요.",
                "편안한 리듬 속에서 좋은 습관을 이어가요.",
                "오늘의 차분한 페이스를 즐겨보세요.",
                "일상의 작은 균형이 든든하게 쌓이고 있어요.",
                "나에게 맞는 생활 박자를 잘 찾아가고 있어요.",
            ),
            3: (
                "몸의 리듬과 일상을 함께 살펴보는 구간이에요.",
                "균형 잡힌 하루를 위한 힌트를 찾아봐요.",
                "편안함과 활력을 나란히 챙겨보세요.",
                "내 생활에 잘 맞는 균형점을 관찰해요.",
                "오늘도 무리 없이 나만의 흐름을 이어가요.",
            ),
            4: (
                "일상 속 작은 루틴을 다정하게 점검해봐요.",
                "편안한 내일을 위해 오늘의 움직임을 살펴봐요.",
                "나에게 맞는 한 가지 습관부터 가볍게 골라요.",
                "잠시 쉬며 생활 리듬을 다시 맞춰볼까요.",
                "무리하지 않는 변화가 좋은 출발이 될 수 있어요.",
            ),
            5: (
                "나를 돌보는 생활 습관을 천천히 돌아봐요.",
                "편안한 하루를 위해 작은 루틴을 계획해봐요.",
                "오늘 할 수 있는 다정한 자기돌봄을 골라봐요.",
                "일상의 균형을 위해 다음 한 걸음을 생각해요.",
                "부담 없이 생활 페이스를 조율해보세요.",
            ),
        },
    }.items()
    for grade, messages in messages_by_grade.items()
}


def _configuration_error(
    message: str,
    *,
    code: ErrorCode,
    details: dict[str, object] | None = None,
) -> MessageConfigurationError:
    return MessageConfigurationError(message, code=code, details=details)


def validate_message_catalog(
    catalog: Mapping[tuple[str, int], Sequence[str]] | None = None,
) -> None:
    """Validate all ten metric/grade combinations and raise on bad config."""
    active = MESSAGE_CATALOG if catalog is None else catalog
    expected = {(metric, grade) for metric in ("bmi", "waist") for grade in range(1, 6)}
    if set(active) != expected:
        missing = sorted(expected - set(active))
        extra = sorted(set(active) - expected)
        raise _configuration_error(
            f"멘트 조합이 누락되었거나 잘못되었습니다: missing={missing}, extra={extra}",
            code=ErrorCode.MESSAGE_CATALOG_MISSING,
        )

    for key in sorted(expected):
        candidates = active[key]
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise _configuration_error(
                f"{key} 멘트 후보는 문자열 목록이어야 합니다.",
                code=ErrorCode.MESSAGE_CONFIGURATION_INVALID,
            )
        if len(candidates) < 5 or len(set(candidates)) != len(candidates):
            raise _configuration_error(
                f"{key} 멘트는 중복 없이 5개 이상이어야 합니다.",
                code=ErrorCode.MESSAGE_CONFIGURATION_INVALID,
            )
        if any(not isinstance(message, str) or not message.strip() for message in candidates):
            raise _configuration_error(
                f"{key} 멘트에는 비어 있지 않은 문자열만 사용할 수 있습니다.",
                code=ErrorCode.MESSAGE_CONFIGURATION_INVALID,
            )
        unsafe = [
            message for message in candidates
            if any(term in message.casefold() for term in _FORBIDDEN_TERMS)
        ]
        if unsafe:
            raise _configuration_error(
                f"{key} 멘트에 안전하지 않은 표현이 있습니다.",
                code=ErrorCode.MESSAGE_UNSAFE,
                details={"messages": unsafe},
            )


def choose_message(measure_type: MeasureType, grade: int, *, seed: int) -> str:
    """Choose reproducibly from the sorted candidates for one metric/grade."""
    validate_message_catalog()
    key = (measure_type, grade)
    if key not in MESSAGE_CATALOG:
        raise _configuration_error(
            f"지원하지 않는 멘트 조합입니다: {key}",
            code=ErrorCode.MESSAGE_CATALOG_MISSING,
        )
    candidates = sorted(MESSAGE_CATALOG[key])
    return random.Random(seed).choice(candidates)


__all__ = ["MESSAGE_CATALOG", "choose_message", "validate_message_catalog"]
