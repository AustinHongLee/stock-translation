"""Alternative valuation methods used when dividend yield is a poor fit.

These functions deliberately produce labelled scenarios, not buy/sell targets.
They use only data already available in the local database.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analyze.suitability import ValuationSuitability
from app.models import FinancialStatement, MarketValuation


@dataclass(frozen=True, slots=True)
class MultipleEstimate:
    label: str
    multiple: float
    price: float | None


@dataclass(frozen=True, slots=True)
class MultipleValuation:
    method: str
    title: str
    headline: str
    basis_label: str
    basis_value: float | None
    basis_source: str
    current_multiple: float | None
    multiple_label: str
    estimates: list[MultipleEstimate]
    fair_price: float | None
    fair_difference: float | None
    fair_difference_percent: float | None
    confidence: str
    notes: list[str]
    warning: str


@dataclass(frozen=True, slots=True)
class RelativeValuationResult:
    methods: list[MultipleValuation]
    primary_method: str | None
    status: str = "available"
    headline: str = ""
    notes: list[str] | None = None


PE_BANDS: dict[str, tuple[float, float, float]] = {
    "growth": (20.0, 28.0, 36.0),
    "general": (12.0, 18.0, 25.0),
    "mature_dividend": (10.0, 15.0, 20.0),
    "insufficient_data": (12.0, 18.0, 25.0),
    "turnaround_loss": (0.0, 0.0, 0.0),
    "cyclical": (0.0, 0.0, 0.0),
    "financial": (0.0, 0.0, 0.0),
}

PB_BANDS: dict[str, tuple[float, float, float]] = {
    "financial": (0.8, 1.1, 1.5),
    "cyclical": (0.7, 1.2, 2.0),
    "turnaround_loss": (0.7, 1.2, 2.0),
    "insufficient_data": (0.8, 1.2, 1.8),
    "growth": (2.0, 4.0, 7.0),
    "general": (1.0, 1.8, 3.0),
    "mature_dividend": (1.0, 1.5, 2.2),
}


def calculate_relative_valuation(
    *,
    financials: list[FinancialStatement],
    market: MarketValuation | None,
    latest_close: float | None,
    suitability: ValuationSuitability | None = None,
) -> RelativeValuationResult:
    """Build PE/PB scenario cards based on the suitability route."""

    company_type = suitability.company_type if suitability else "general"
    if suitability and _should_refuse_valuation(suitability):
        return RelativeValuationResult(
            methods=[],
            primary_method=None,
            status="not_applicable",
            headline="目前先不估價",
            notes=_refusal_notes(suitability),
        )

    requested = _requested_methods(suitability)
    methods: list[MultipleValuation] = []

    if "pe_band" in requested:
        pe = calculate_pe_band(
            financials=financials,
            market=market,
            latest_close=latest_close,
            company_type=company_type,
        )
        if pe:
            methods.append(pe)

    if "pb_band" in requested or "peer_pe_pb" in requested:
        pb = calculate_pb_band(
            financials=financials,
            market=market,
            latest_close=latest_close,
            company_type=company_type,
        )
        if pb:
            methods.append(pb)

    if not methods:
        for candidate in (
            calculate_pe_band(
                financials=financials,
                market=market,
                latest_close=latest_close,
                company_type=company_type,
            ),
            calculate_pb_band(
                financials=financials,
                market=market,
                latest_close=latest_close,
                company_type=company_type,
            ),
        ):
            if candidate:
                methods.append(candidate)

    primary = methods[0].method if methods else None
    return RelativeValuationResult(methods=methods, primary_method=primary)


def calculate_pe_band(
    *,
    financials: list[FinancialStatement],
    market: MarketValuation | None,
    latest_close: float | None,
    company_type: str = "general",
) -> MultipleValuation | None:
    eps, source, confidence, notes = _eps_basis(financials, market, latest_close)
    if eps is None or eps <= 0:
        return None
    current_pe = _safe_div(latest_close, eps) or (market.pe_ratio if market and market.pe_ratio else None)
    multiples, band_note = _scenario_multiples(
        current_multiple=current_pe,
        fallback=PE_BANDS.get(company_type, PE_BANDS["general"]),
    )
    if multiples is None:
        return None
    estimates = _multiple_estimates(eps, multiples)
    fair_price = estimates[1].price
    diff, diff_pct = _price_difference(latest_close, fair_price)
    notes = list(notes)
    if band_note:
        notes.append(band_note)
    if source == "official_pe_implied_ttm_eps":
        notes.append("目前用官方本益比反推 EPS，等資料源補齊近四季後會更穩。")
    return MultipleValuation(
        method="pe_band",
        title="本益比（PE）倍數敏感度",
        headline="這是 what-if：EPS 不變時，市場給的 PE 改變會怎樣。",
        basis_label="估算年 EPS",
        basis_value=eps,
        basis_source=source,
        current_multiple=current_pe,
        multiple_label="目前 PE",
        estimates=estimates,
        fair_price=fair_price,
        fair_difference=diff,
        fair_difference_percent=diff_pct,
        confidence=confidence,
        notes=notes,
        warning="PE 敏感度只展示倍數變化情境；目前 PE 本身也可能偏高或偏低。",
    )


def calculate_pb_band(
    *,
    financials: list[FinancialStatement],
    market: MarketValuation | None,
    latest_close: float | None,
    company_type: str = "general",
) -> MultipleValuation | None:
    book_value, source, confidence, notes = _book_value_basis(financials, market, latest_close)
    if book_value is None or book_value <= 0:
        return None
    current_pb = _safe_div(latest_close, book_value) or (market.pb_ratio if market and market.pb_ratio else None)
    multiples, band_note = _scenario_multiples(
        current_multiple=current_pb,
        fallback=PB_BANDS.get(company_type, PB_BANDS["general"]),
    )
    if multiples is None:
        return None
    estimates = _multiple_estimates(book_value, multiples)
    fair_price = estimates[1].price
    diff, diff_pct = _price_difference(latest_close, fair_price)
    notes = list(notes)
    if band_note:
        notes.append(band_note)
    return MultipleValuation(
        method="pb_band",
        title="本淨比（PB）倍數敏感度",
        headline="這是 what-if：每股淨值不變時，市場給的 PB 改變會怎樣。",
        basis_label="每股淨值",
        basis_value=book_value,
        basis_source=source,
        current_multiple=current_pb,
        multiple_label="目前 PB",
        estimates=estimates,
        fair_price=fair_price,
        fair_difference=diff,
        fair_difference_percent=diff_pct,
        confidence=confidence,
        notes=notes,
        warning="PB 敏感度只展示倍數變化情境；帳面淨值品質與 ROE 仍要另外確認。",
    )


def _requested_methods(suitability: ValuationSuitability | None) -> list[str]:
    if suitability is None:
        return ["pe_band", "pb_band"]
    ordered = [
        suitability.recommended_primary,
        *suitability.recommended_secondary,
    ]
    avoid = set(suitability.recommended_avoid)
    wanted = [item for item in ordered if item not in avoid]
    if "peer_pe_pb" in wanted:
        return ["pe_band", "pb_band"]
    if not any(item in {"pe_band", "pb_band"} for item in wanted):
        if suitability.company_type in {"cyclical", "financial", "turnaround_loss", "insufficient_data"}:
            wanted.append("pb_band")
        else:
            wanted.extend(["pe_band", "pb_band"])
    return _dedupe(wanted)


def _should_refuse_valuation(suitability: ValuationSuitability) -> bool:
    if suitability.recommended_primary == "none" and suitability.company_type in {
        "turnaround_loss",
        "no_estimate",
        "insufficient_data",
        "etf",
    }:
        return True
    if "newly_listed" in suitability.reasons or "loss_history" in suitability.reasons:
        return True
    return False


def _refusal_notes(suitability: ValuationSuitability) -> list[str]:
    notes: list[str] = []
    if "newly_listed" in suitability.reasons:
        notes.append("上市時間太短，市場還沒有足夠歷史區間可參考。")
    if "loss_history" in suitability.reasons:
        notes.append("近年曾虧損，PE 與股利法都容易變成假精確。")
    if "yield_too_low" in suitability.reasons:
        notes.append("股利不是主要報酬來源，股利法會系統性失真。")
    if "cyclical" in suitability.reasons:
        notes.append("景氣循環或獲利波動大，單一倍數容易誤導。")
    if not notes:
        notes.append("目前資料還不足以支撐估價，只先看營收、獲利與風險標籤。")
    notes.append("先看營收動能、毛利率趨勢、EPS 是否穩定，再決定是否值得估價。")
    return notes


def _eps_basis(
    financials: list[FinancialStatement],
    market: MarketValuation | None,
    latest_close: float | None,
) -> tuple[float | None, str, str, list[str]]:
    rows = [item for item in _sorted_financials(financials) if item.eps is not None]
    latest_four = rows[:4]
    if len(latest_four) >= 4:
        return sum(float(item.eps) for item in latest_four), "latest_four_quarters_eps", "high", []
    if market and market.pe_ratio and market.pe_ratio > 0 and latest_close and latest_close > 0:
        return latest_close / market.pe_ratio, "official_pe_implied_ttm_eps", "medium", []
    if rows:
        latest = float(rows[0].eps)
        return latest * 4, "latest_quarter_eps_annualized", "low", ["只有最新季 EPS，先用年化估算。"]
    return None, "missing_eps", "low", ["缺少 EPS，無法做本益比情境。"]


def _book_value_basis(
    financials: list[FinancialStatement],
    market: MarketValuation | None,
    latest_close: float | None,
) -> tuple[float | None, str, str, list[str]]:
    for item in _sorted_financials(financials):
        if item.book_value_per_share is not None and item.book_value_per_share > 0:
            return float(item.book_value_per_share), "latest_financial_book_value", "high", []
    if market and market.pb_ratio and market.pb_ratio > 0 and latest_close and latest_close > 0:
        return latest_close / market.pb_ratio, "official_pb_implied_book_value", "medium", [
            "目前用官方 PB 反推每股淨值。"
        ]
    return None, "missing_book_value", "low", ["缺少每股淨值，無法做本淨比情境。"]


def _multiple_estimates(basis_value: float, multiples: tuple[float, float, float]) -> list[MultipleEstimate]:
    labels = ["倍數 -20%", "目前倍數", "倍數 +20%"]
    return [
        MultipleEstimate(label=label, multiple=multiple, price=basis_value * multiple)
        for label, multiple in zip(labels, multiples)
    ]


def _scenario_multiples(
    *,
    current_multiple: float | None,
    fallback: tuple[float, float, float],
) -> tuple[tuple[float, float, float] | None, str]:
    if current_multiple is not None and current_multiple > 0:
        return (
            current_multiple * 0.8,
            current_multiple,
            current_multiple * 1.2,
        ), "暫無歷史倍數區間，先用目前倍數上下 20% 做敏感度情境。"
    if fallback == (0.0, 0.0, 0.0):
        return None, ""
    return fallback, "缺少目前倍數，先用保守預設倍數做情境。"


def _sorted_financials(financials: list[FinancialStatement]) -> list[FinancialStatement]:
    return sorted(financials, key=lambda item: (item.year, item.quarter), reverse=True)


def _price_difference(
    latest_close: float | None,
    fair_price: float | None,
) -> tuple[float | None, float | None]:
    if latest_close is None or fair_price is None:
        return None, None
    diff = latest_close - fair_price
    diff_pct = (diff / fair_price) * 100 if fair_price else None
    return diff, diff_pct


def _safe_div(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline in (None, 0):
        return None
    return value / baseline


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
