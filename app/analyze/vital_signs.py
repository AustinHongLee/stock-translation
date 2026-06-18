from __future__ import annotations

from dataclasses import dataclass

from app.analyze.financial import calculate_financial_metrics
from app.models import FinancialStatement, MonthlyRevenue


@dataclass(frozen=True, slots=True)
class VitalSign:
    key: str
    label: str
    value: str
    tone: str
    text: str


@dataclass(frozen=True, slots=True)
class VitalSignsReport:
    title: str
    tone: str
    sentence: str
    facts: list[VitalSign]


def build_vital_signs_report(
    *,
    monthly_revenues: list[MonthlyRevenue],
    financials: list[FinancialStatement],
) -> VitalSignsReport:
    """Build a non-price health card for stocks that should not be valued."""

    facts = [
        _revenue_direction(monthly_revenues),
        _gross_margin_trend(financials),
        _eps_status(financials),
        _break_even_status(financials),
    ]
    known = [item for item in facts if item.tone != "unknown"]
    caution_count = sum(1 for item in known if item.tone == "caution")
    positive_count = sum(1 for item in known if item.tone == "positive")

    if not known:
        title = "體質資料待補"
        tone = "unknown"
        sentence = "目前還沒有足夠營收或財報資料，先不要用價格硬猜公司體質。"
    elif caution_count:
        title = "先看體質有沒有修復"
        tone = "caution"
        sentence = "這檔目前不適合估價；先確認營收、毛利率與 EPS 是否連續改善。"
    elif positive_count >= 3:
        title = "體質訊號開始站穩"
        tone = "positive"
        sentence = "這檔雖然暫不估價，但營收與獲利訊號目前偏正向，可繼續追蹤是否延續。"
    else:
        title = "先觀察體質方向"
        tone = "neutral"
        sentence = "這檔暫不適合硬算價格；先看營收、毛利率與 EPS 是否往同一方向改善。"

    return VitalSignsReport(title=title, tone=tone, sentence=sentence, facts=facts)


def _revenue_direction(records: list[MonthlyRevenue]) -> VitalSign:
    usable = [
        item for item in sorted(records, key=lambda item: item.year_month, reverse=True)
        if item.yoy_percent is not None
    ][:6]
    if not usable:
        return VitalSign(
            key="revenue_yoy",
            label="營收方向",
            value="待補",
            tone="unknown",
            text="尚無月營收年增率，不能判斷生意量是擴張還是收縮。",
        )

    latest = usable[0]
    positives = sum(1 for item in usable if (item.yoy_percent or 0) > 0)
    negatives = sum(1 for item in usable if (item.yoy_percent or 0) < 0)
    tone = "neutral"
    if latest.yoy_percent is not None and latest.yoy_percent >= 10 and positives >= max(2, len(usable) // 2):
        tone = "positive"
    elif latest.yoy_percent is not None and latest.yoy_percent < 0 and negatives >= max(2, len(usable) // 2):
        tone = "caution"

    return VitalSign(
        key="revenue_yoy",
        label="營收方向",
        value=f"{latest.yoy_percent:.1f}%",
        tone=tone,
        text=f"最近 {len(usable)} 個月有 {positives} 個月年增為正，最新 {latest.year_month} 年增 {latest.yoy_percent:.1f}%。",
    )


def _gross_margin_trend(financials: list[FinancialStatement]) -> VitalSign:
    metrics = [
        calculate_financial_metrics(item)
        for item in _sorted_financials(financials)
        if calculate_financial_metrics(item).gross_margin_percent is not None
    ][:4]
    if not metrics:
        return VitalSign(
            key="gross_margin",
            label="毛利率",
            value="待補",
            tone="unknown",
            text="尚無毛利率資料，不能判斷產品或服務獲利品質。",
        )

    latest = metrics[0]
    previous = metrics[1] if len(metrics) > 1 else None
    tone = "neutral"
    trend_text = "目前先看下一季是否延續。"
    if latest.gross_margin_percent is not None and latest.gross_margin_percent < 0:
        tone = "caution"
        trend_text = "毛利率仍為負，代表本業成本壓力還沒有解除。"
    elif previous and latest.gross_margin_percent is not None and previous.gross_margin_percent is not None:
        diff = latest.gross_margin_percent - previous.gross_margin_percent
        if diff >= 1:
            tone = "positive"
            trend_text = f"較前一季改善 {diff:.1f} 個百分點。"
        elif diff <= -1:
            tone = "caution"
            trend_text = f"較前一季下滑 {abs(diff):.1f} 個百分點。"

    return VitalSign(
        key="gross_margin",
        label="毛利率",
        value=f"{latest.gross_margin_percent:.1f}%",
        tone=tone,
        text=f"{latest.quarter_label} 毛利率約 {latest.gross_margin_percent:.1f}%，{trend_text}",
    )


def _eps_status(financials: list[FinancialStatement]) -> VitalSign:
    ordered = [item for item in _sorted_financials(financials) if item.eps is not None]
    if not ordered:
        return VitalSign(
            key="eps",
            label="EPS",
            value="待補",
            tone="unknown",
            text="尚無 EPS 資料，不能判斷每股獲利是否穩定。",
        )

    latest = ordered[0]
    latest_eps = float(latest.eps or 0)
    if latest_eps < 0:
        loss_streak = 0
        for item in ordered:
            if item.eps is None or item.eps >= 0:
                break
            loss_streak += 1
        return VitalSign(
            key="eps",
            label="EPS",
            value=f"{latest_eps:.2f}",
            tone="caution",
            text=f"{latest.year}Q{latest.quarter} EPS 仍為負，已連續 {loss_streak} 季虧損；先看虧損是否收斂。",
        )

    previous = ordered[1] if len(ordered) > 1 else None
    if previous and previous.eps is not None and previous.eps < 0:
        text = f"{latest.year}Q{latest.quarter} EPS 轉正為 {latest_eps:.2f}，但需要更多季度確認不是一次性。"
        tone = "neutral"
    else:
        text = f"{latest.year}Q{latest.quarter} EPS 為 {latest_eps:.2f}，目前每股獲利為正。"
        tone = "positive"
    return VitalSign(key="eps", label="EPS", value=f"{latest_eps:.2f}", tone=tone, text=text)


def _break_even_status(financials: list[FinancialStatement]) -> VitalSign:
    ordered = _sorted_financials(financials)
    if not ordered:
        return VitalSign(
            key="break_even",
            label="損益兩平",
            value="待補",
            tone="unknown",
            text="尚無最新財報，不能判斷是否站回損益兩平。",
        )

    latest = ordered[0]
    metrics = calculate_financial_metrics(latest)
    eps = latest.eps
    net_margin = metrics.net_margin_percent
    if eps is None and net_margin is None:
        return VitalSign(
            key="break_even",
            label="損益兩平",
            value="待補",
            tone="unknown",
            text="最新財報缺少 EPS 或淨利率，暫時不能判斷損益兩平。",
        )

    is_positive = (eps is not None and eps > 0) or (net_margin is not None and net_margin > 0)
    if is_positive:
        return VitalSign(
            key="break_even",
            label="損益兩平",
            value="已站上",
            tone="positive",
            text=f"{latest.year}Q{latest.quarter} 已站上損益兩平；接著看是否能連續維持。",
        )
    return VitalSign(
        key="break_even",
        label="損益兩平",
        value="未站上",
        tone="caution",
        text=f"{latest.year}Q{latest.quarter} 尚未站上損益兩平，估價前要先看虧損何時收斂。",
    )


def _sorted_financials(financials: list[FinancialStatement]) -> list[FinancialStatement]:
    return sorted(financials, key=lambda item: (item.year, item.quarter), reverse=True)
