from __future__ import annotations

from dataclasses import dataclass

from app.models import FinancialStatement


@dataclass(frozen=True, slots=True)
class FinancialMetrics:
    quarter_label: str
    eps: float | None
    gross_margin_percent: float | None
    operating_margin_percent: float | None
    net_margin_percent: float | None
    roe_percent: float | None
    roa_percent: float | None


def calculate_financial_metrics(statement: FinancialStatement) -> FinancialMetrics:
    return FinancialMetrics(
        quarter_label=f"{statement.year}Q{statement.quarter}",
        eps=statement.eps,
        gross_margin_percent=_percent(statement.gross_profit, statement.revenue),
        operating_margin_percent=_percent(statement.operating_income, statement.revenue),
        net_margin_percent=_percent(statement.parent_net_income or statement.net_income, statement.revenue),
        roe_percent=_percent(statement.parent_net_income, statement.parent_equity),
        roa_percent=_percent(statement.net_income, statement.total_assets),
    )


def financial_tone(metrics: FinancialMetrics) -> str:
    if metrics.eps is None or metrics.net_margin_percent is None:
        return "unknown"
    if metrics.eps < 0 or metrics.net_margin_percent < 0:
        return "caution"
    if metrics.net_margin_percent >= 20 and (metrics.roe_percent or 0) >= 5:
        return "positive"
    return "neutral"


def financial_title(metrics: FinancialMetrics) -> str:
    tone = financial_tone(metrics)
    if tone == "positive":
        return "獲利能力強"
    if tone == "caution":
        return "獲利能力轉弱"
    if tone == "unknown":
        return "獲利資料不足"
    return "獲利能力普通"


def _percent(value: int | float | None, baseline: int | float | None) -> float | None:
    if value is None or baseline in (None, 0):
        return None
    return round((float(value) / float(baseline)) * 100, 4)
