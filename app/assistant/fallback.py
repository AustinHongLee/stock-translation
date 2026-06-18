from __future__ import annotations

from typing import Any

from app.assistant.context_builder import AssistantContext
from app.assistant.guardrail import SAFE_FALLBACK_MESSAGE, guard_assistant_output


def build_fallback_response(context: AssistantContext) -> str:
    if context.kind == "portfolio":
        text = _portfolio_response(context.facts)
    elif context.kind == "stock":
        text = _stock_response(context.facts)
    else:
        text = SAFE_FALLBACK_MESSAGE
    return guard_assistant_output(text)


def _portfolio_response(facts: dict[str, Any]) -> str:
    summary = facts.get("summary", {}) or {}
    performance = facts.get("performance", {}) or {}
    sentence = summary.get("sentence") or "目前持倉資料還不完整。"
    dividends = performance.get("total_cash_dividends")
    xirr = performance.get("xirr_percent")
    parts = [
        str(sentence),
        f"含息資料：累計現金股利 {dividends if dividends is not None else '待補'}。",
        f"年化報酬：{xirr if xirr is not None else '資料不足以年化'}。",
        "下一步可到持倉頁查看交易紀錄、含息總報酬與 0050 對照。",
    ]
    return " ".join(parts)


def _stock_response(facts: dict[str, Any]) -> str:
    brief = facts.get("brief", {}) or {}
    suitability = facts.get("valuation_suitability", {}) or {}
    report = facts.get("report", {}) or {}
    sections = report.get("sections", []) or []
    first_section = sections[0]["title"] if sections and isinstance(sections[0], dict) else "白話健檢"
    parts = [
        str(brief.get("company_sentence") or "這檔股票的公司簡介資料待補。"),
        str(brief.get("valuation_sentence") or "估值適用性仍需補資料確認。"),
        f"目前估值分流：{suitability.get('state_label', '待補資料')}。",
        f"可以先看「{first_section}」與估值適用性卡片，確認資料限制。",
    ]
    return " ".join(parts)
