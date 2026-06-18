from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

SAFE_FALLBACK_MESSAGE = (
    "這題超出本工具範圍。我只能解讀已同步資料與帶你找到頁面，"
    "不提供交易指令或未來價格判斷。"
)

BLOCKED_OUTPUT_TERMS: tuple[str, ...] = (
    "買進",
    "賣出",
    "買賣",
    "建議買",
    "建議賣",
    "可以買",
    "可以賣",
    "該買",
    "該賣",
    "目標價",
    "會漲",
    "會跌",
    "必漲",
    "必跌",
    "加碼",
    "抄底",
    "停損",
    "停利",
    "明牌",
)

BLOCKED_REQUEST_TERMS: tuple[str, ...] = BLOCKED_OUTPUT_TERMS + (
    "推薦",
    "預測",
    "報一支",
    "哪支能買",
    "哪支會噴",
)


@dataclass(frozen=True, slots=True)
class AssistantGuardrailResult:
    allowed: bool
    matched_terms: tuple[str, ...]
    safe_message: str = SAFE_FALLBACK_MESSAGE


def check_output_guardrail(text: str, *, extra_terms: Iterable[str] = ()) -> AssistantGuardrailResult:
    return _check_text(text, (*BLOCKED_OUTPUT_TERMS, *tuple(extra_terms)))


def check_request_guardrail(text: str, *, extra_terms: Iterable[str] = ()) -> AssistantGuardrailResult:
    return _check_text(text, (*BLOCKED_REQUEST_TERMS, *tuple(extra_terms)))


def guard_assistant_output(text: str, *, fallback: str = SAFE_FALLBACK_MESSAGE) -> str:
    result = check_output_guardrail(text)
    if result.allowed:
        return text
    return fallback


def _check_text(text: str, blocked_terms: Iterable[str]) -> AssistantGuardrailResult:
    normalized = _normalize(text)
    matched: list[str] = []
    for term in blocked_terms:
        if _normalize(term) in normalized:
            matched.append(term)
    if _predictive_price_pattern(normalized):
        matched.append("未來價格判斷")
    unique = tuple(dict.fromkeys(matched))
    return AssistantGuardrailResult(allowed=not unique, matched_terms=unique)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _predictive_price_pattern(normalized: str) -> bool:
    return bool(re.search(r"(明天|下週|下周|年底|未來).{0,8}(漲|跌|到\d)", normalized))
