from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.assistant.deidentify import DeidentifyOptions, deidentify_payload


@dataclass(frozen=True, slots=True)
class AssistantContext:
    kind: str
    facts: dict[str, Any]
    source_note: str
    disclaimer: str


def build_assistant_context(
    *,
    kind: str,
    payload: dict[str, Any],
    mask_amounts: bool = True,
) -> AssistantContext:
    if kind not in {"portfolio", "stock"}:
        raise ValueError("assistant context only supports portfolio or stock payloads")

    safe_payload = deidentify_payload(
        payload,
        options=DeidentifyOptions(mask_amounts=mask_amounts),
    )
    facts = _portfolio_facts(safe_payload) if kind == "portfolio" else _stock_facts(safe_payload)
    return AssistantContext(
        kind=kind,
        facts=facts,
        source_note="只使用本機已同步且已計算完成的結構化資料。",
        disclaimer="本助理只做資料解讀與頁面導航，不提供交易指令或未來價格判斷。",
    )


def _portfolio_facts(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": payload.get("summary", {}),
        "performance": payload.get("performance", {}),
        "positions_count": len(payload.get("positions", []) or []),
        "limitations": payload.get("limitations", []),
    }


def _stock_facts(payload: dict[str, Any]) -> dict[str, Any]:
    valuation = payload.get("valuation", {}) or {}
    return {
        "profile": payload.get("profile", {}),
        "brief": payload.get("brief", {}),
        "report": payload.get("report", {}),
        "validation": payload.get("validation", {}),
        "valuation_suitability": valuation.get("suitability", {}),
        "relative_valuation": valuation.get("relative", {}),
    }
