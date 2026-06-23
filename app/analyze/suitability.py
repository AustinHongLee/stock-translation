"""估價方法適用性判斷(分析層純函數)。

輸入:股利、財報、官方估值、現價、基本資料。
輸出:公司類型 + 股利法適用狀態(applicable / low_confidence / not_applicable)
      + 原因碼 + 建議改看的方法 + 股利資料完整度。

鐵則(對齊《04》《06》):純計算、固定輸入→固定輸出、可單元測試;
不碰網路、不碰 AI、不產生目標股價或未來價格判斷。對應規格《12》B 部分。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from app.analyze.dividends import annual_cash_dividends_by_year as _annual_cash_by_year
from app.models import DividendRecord, FinancialStatement, MarketValuation, StockProfile

# --- 可調門檻常數(對齊《12》3.6) ---------------------------------------
YEARS_FULL_SAMPLE = 5
YEARS_MIN_SHOW = 3
YIELD_HARD_FLOOR = 1.0      # %,低於 → 硬性不適用
YIELD_SOFT_FLOOR = 2.5      # %,低於 → 低信心/改看他法
DIVIDEND_CV_MAX = 0.40      # 配息變異係數上限
ZERO_DIV_YEARS_MAX = 1      # 近 5 年零配息超過此數 → 不穩
EPS_NEG_YEARS_MAX = 1       # 可得年數內虧損超過此數 → 虧損型
EPS_CAGR_GROWTH = 15.0      # %,EPS 年複合成長高於此(且低配息低息)→ 成長型
PAYOUT_HIGH = 100.0         # %,配息率高於此 → 吃老本
PAYOUT_GROWTH = 30.0        # %,配息率低於此(且高成長)→ 成長型佐證
ONEOFF_MULTIPLE = 2.0       # 單年股利 > 中位數×此倍 → 一次性
NONOP_SHARE_MAX = 0.50      # 業外/稅前 高於此 → 一次性獲利疑慮
LISTED_MIN_YEARS = 3
EARNINGS_CV_CYCLICAL = 0.50 # EPS 變異係數高於此 → 疑似景氣循環/獲利大起大落

# industry_code 對照(初版;產業是提示,判斷仍以財務特徵為主)
CYCLICAL_INDUSTRY_CODES: frozenset[str] = frozenset({
    "01",  # 水泥
    "03",  # 塑膠/塑化
    "10",  # 造紙
    "11",  # 鋼鐵
    "12",  # 橡膠
    "15",  # 航運
    "26",  # 光電:面板/太陽能常有景氣循環特性
    "35",  # 綠能環保
})
FINANCIAL_INDUSTRY_CODES: frozenset[str] = frozenset({"17"})
CONSTRUCTION_INDUSTRY_CODES: frozenset[str] = frozenset({"14"})


@dataclass(frozen=True, slots=True)
class ValuationSuitability:
    company_type: str
    company_type_label: str
    state: str  # applicable | low_confidence | not_applicable
    reasons: list[str] = field(default_factory=list)
    recommended_primary: str = "yield"
    recommended_secondary: list[str] = field(default_factory=list)
    recommended_avoid: list[str] = field(default_factory=list)
    data_confidence: str = "medium"
    confidence_factors: list[str] = field(default_factory=list)
    headline: str = ""


# --- 對外主函式 ----------------------------------------------------------
def assess_valuation_suitability(
    *,
    dividends: list[DividendRecord],
    financials: list[FinancialStatement] | None = None,
    market: MarketValuation | None = None,
    latest_close: float | None = None,
    profile: StockProfile | None = None,
    as_of_date: date | None = None,
) -> ValuationSuitability:
    financials = financials or []
    as_of_date = as_of_date or date.today()

    annual_cash = _annual_cash_by_year(dividends)
    recent_years = sorted(annual_cash, reverse=True)[:YEARS_FULL_SAMPLE]
    recent_values = [annual_cash[y] for y in recent_years]
    data_years = len(recent_values)
    average_cash = sum(recent_values) / data_years if data_years else None

    current_yield = _current_yield(average_cash, latest_close, market)
    dividend_cv = _cv(recent_values)
    zero_div_years = _zero_dividend_years(annual_cash)
    years_since_listing = _years_since(profile.listed_date if profile else None, as_of_date)

    annual_eps = _annual_eps(financials)
    eps_ttm = _eps_ttm(financials)
    eps_neg_years = sum(1 for v in annual_eps.values() if v < 0)
    eps_cagr = _eps_cagr(annual_eps)
    earnings_cv = _cv([abs(v) for v in annual_eps.values()]) if len(annual_eps) >= 2 else None
    payout_ratio = _payout_ratio(average_cash, annual_eps, eps_ttm)
    oneoff = _oneoff_flag(recent_values, financials)

    is_etf = _is_etf(profile)
    industry = profile.industry_code if profile else None
    cyclical_industry = bool(industry and industry in CYCLICAL_INDUSTRY_CODES)
    financial_industry = bool(industry and industry in FINANCIAL_INDUSTRY_CODES)
    construction_industry = bool(industry and industry in CONSTRUCTION_INDUSTRY_CODES)
    cyclical = cyclical_industry or (earnings_cv is not None and earnings_cv > EARNINGS_CV_CYCLICAL)
    growth = (
        eps_cagr is not None
        and eps_cagr > EPS_CAGR_GROWTH
        and (payout_ratio is None or payout_ratio < PAYOUT_GROWTH)
        and (current_yield is None or current_yield < YIELD_SOFT_FLOOR)
    )

    # --- 收集原因碼 ---
    na_reasons: list[str] = []
    if is_etf:
        na_reasons.append("etf")
    if (eps_ttm is not None and eps_ttm < 0) or eps_neg_years > EPS_NEG_YEARS_MAX:
        na_reasons.append("loss_history")
    if current_yield is not None and current_yield < YIELD_HARD_FLOOR:
        na_reasons.append("yield_too_low")
    if average_cash is None or data_years < YEARS_MIN_SHOW:
        na_reasons.append("insufficient_data")
    if years_since_listing is not None and years_since_listing < LISTED_MIN_YEARS:
        na_reasons.append("newly_listed")
    if zero_div_years > ZERO_DIV_YEARS_MAX:
        na_reasons.append("unstable_dividend")

    low_reasons: list[str] = []
    if cyclical:
        low_reasons.append("cyclical")
    if growth:
        low_reasons.append("growth_stock")
    if (current_yield is not None and current_yield < YIELD_SOFT_FLOOR) and "yield_too_low" not in na_reasons:
        low_reasons.append("low_yield")
    if dividend_cv is not None and dividend_cv > DIVIDEND_CV_MAX:
        low_reasons.append("unstable_dividend")
    if payout_ratio is not None and payout_ratio > PAYOUT_HIGH:
        low_reasons.append("high_payout")
    if oneoff:
        low_reasons.append("one_off_dividend")
    if average_cash is not None and YEARS_MIN_SHOW <= data_years < YEARS_FULL_SAMPLE:
        low_reasons.append("short_history")

    # --- 決定狀態 ---
    if na_reasons:
        state = "not_applicable"
        reasons = _dedupe(na_reasons + low_reasons)
    elif low_reasons:
        state = "low_confidence"
        reasons = _dedupe(low_reasons)
    else:
        state = "applicable"
        reasons = []

    hard_no_estimate = (
        "loss_history" in reasons
        or "newly_listed" in reasons
        or (
            cyclical
            and "yield_too_low" in reasons
            and "insufficient_data" in reasons
        )
    )

    company_type, company_type_label = _classify(
        is_etf=is_etf,
        loss="loss_history" in na_reasons,
        hard_no_estimate=hard_no_estimate,
        dividend_data_short="insufficient_data" in na_reasons,
        cyclical=cyclical,
        financial=financial_industry,
        construction=construction_industry,
        growth=growth,
        state=state,
    )
    primary, secondary, avoid = _route_methods(company_type)
    if "yield_too_low" in reasons:
        secondary = [item for item in secondary if item != "yield"]
        avoid = _dedupe(avoid + ["yield"])
        if primary == "yield":
            primary = "none"
    confidence, factors = _data_confidence(data_years=data_years)
    headline = _headline(state)

    return ValuationSuitability(
        company_type=company_type,
        company_type_label=company_type_label,
        state=state,
        reasons=reasons,
        recommended_primary=primary,
        recommended_secondary=secondary,
        recommended_avoid=avoid,
        data_confidence=confidence,
        confidence_factors=factors,
        headline=headline,
    )


# --- 分類與路由 ----------------------------------------------------------
def _classify(
    *,
    is_etf,
    loss,
    hard_no_estimate,
    dividend_data_short,
    cyclical,
    financial,
    construction,
    growth,
    state,
):
    if is_etf:
        return "etf", "ETF"
    if loss:
        return "turnaround_loss", "轉機股(近年曾虧損)"
    if hard_no_estimate:
        return "no_estimate", "高不確定(暫不估價)"
    if cyclical:
        return "cyclical", "景氣循環股"
    if financial:
        return "financial", "金融股"
    if construction:
        return "construction", "營建/資產型"
    if growth:
        return "growth", "成長股"
    if state == "applicable":
        return "mature_dividend", "成熟高息股"
    if dividend_data_short:
        return "general", "一般股(股利資料短)"
    return "general", "一般股"


def _route_methods(company_type: str) -> tuple[str, list[str], list[str]]:
    table = {
        "mature_dividend": ("yield", ["pe_band"], []),
        "growth": ("pe_band", ["revenue_momentum"], ["yield"]),
        "cyclical": ("pb_band", ["revenue_momentum", "gross_margin_trend"], ["yield", "pe_single"]),
        "financial": ("pb_band", ["roe", "yield"], ["pe_single"]),
        "construction": ("pb_band", ["revenue_momentum"], ["yield", "pe_single"]),
        "turnaround_loss": ("none", ["revenue_momentum", "gross_margin_trend"], ["yield", "pe_band", "pb_band"]),
        "no_estimate": ("none", ["revenue_momentum", "gross_margin_trend"], ["yield", "pe_band", "pb_band"]),
        "etf": ("distribution_yield_band", ["premium_discount"], ["yield"]),
        "insufficient_data": ("none", ["peer_pe_pb"], ["yield"]),
        "general": ("pe_band", ["pb_band", "yield"], []),
    }
    return table.get(company_type, ("pe_band", ["pb_band"], []))


def _data_confidence(*, data_years):
    factors: list[str] = []
    if data_years < YEARS_FULL_SAMPLE:
        factors.append(f"dividend_years={data_years}")
    if data_years >= YEARS_FULL_SAMPLE:
        level = "high"
    elif data_years >= YEARS_MIN_SHOW:
        level = "medium"
    else:
        level = "low"
    return level, factors


def _headline(state: str) -> str:
    return {
        "applicable": "適合用股利法估價",
        "low_confidence": "股利法參考性偏低，建議搭配其他方法",
        "not_applicable": "這檔不適合用股利法估價",
    }[state]


# --- 訊號計算(純函數) --------------------------------------------------
def _current_yield(average_cash, latest_close, market) -> float | None:
    if average_cash and latest_close and latest_close > 0:
        return (average_cash / latest_close) * 100
    if market and market.dividend_yield is not None:
        return market.dividend_yield
    return None


def _cv(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    mean = sum(clean) / len(clean)
    if mean == 0:
        return None
    return statistics.pstdev(clean) / abs(mean)


def _zero_dividend_years(annual_cash: dict[int, float]) -> int:
    """配息年份「之間」的缺口年數(時有時無)。

    只計算最早與最晚配息年之間的內部缺口,不把「上市前/資料前」的年份
    當成停配——否則只有 3 年資料的公司會被誤判為配息不穩。
    """
    positive_years = {y for y, v in annual_cash.items() if v > 0}
    if len(positive_years) < 2:
        return 0
    lo, hi = min(positive_years), max(positive_years)
    start = max(lo, hi - YEARS_FULL_SAMPLE + 1)
    return sum(1 for y in range(start, hi + 1) if y not in positive_years)


def _years_since(start: date | None, as_of: date) -> float | None:
    if start is None:
        return None
    return (as_of - start).days / 365.25


def _sorted_financials(financials: list[FinancialStatement]) -> list[FinancialStatement]:
    return sorted(financials, key=lambda f: (f.year, f.quarter), reverse=True)


def _eps_ttm(financials: list[FinancialStatement]) -> float | None:
    rows = [f for f in _sorted_financials(financials) if f.eps is not None][:4]
    if not rows:
        return None
    return sum(f.eps for f in rows)


def _annual_eps(financials: list[FinancialStatement]) -> dict[int, float]:
    by_year: dict[int, float] = {}
    seen: dict[int, int] = {}
    for f in financials:
        if f.eps is None:
            continue
        by_year[f.year] = by_year.get(f.year, 0.0) + f.eps
        seen[f.year] = seen.get(f.year, 0) + 1
    # 只保留有至少一季資料的年度(避免半年資料誤判,仍當作該年趨勢參考)
    return by_year


def _eps_cagr(annual_eps: dict[int, float]) -> float | None:
    years = sorted(annual_eps)
    if len(years) < 2:
        return None
    first, last = annual_eps[years[0]], annual_eps[years[-1]]
    if first <= 0 or last <= 0:
        return None
    span = years[-1] - years[0]
    if span <= 0:
        return None
    return ((last / first) ** (1 / span) - 1) * 100


def _payout_ratio(average_cash, annual_eps: dict[int, float], eps_ttm) -> float | None:
    if average_cash is None:
        return None
    basis = None
    if annual_eps:
        latest_year = max(annual_eps)
        basis = annual_eps[latest_year]
    if (basis is None or basis <= 0) and eps_ttm is not None:
        basis = eps_ttm
    if basis is None or basis <= 0:
        return None
    return (average_cash / basis) * 100


def _oneoff_flag(recent_values: list[float], financials: list[FinancialStatement]) -> bool:
    positive = [v for v in recent_values if v > 0]
    if len(positive) >= 3:
        median = statistics.median(positive)
        if median > 0 and max(positive) > median * ONEOFF_MULTIPLE:
            return True
    rows = _sorted_financials(financials)
    if rows:
        latest = rows[0]
        if (
            latest.non_operating_income_expense is not None
            and latest.pre_tax_income
            and latest.pre_tax_income > 0
            and latest.non_operating_income_expense / latest.pre_tax_income > NONOP_SHARE_MAX
        ):
            return True
    return False


def _is_etf(profile: StockProfile | None) -> bool:
    if profile is None:
        return False
    sid = (profile.stock_id or "").strip()
    if sid.startswith("00") and len(sid) >= 4:
        return True
    return (profile.market or "").upper() in {"ETF", "ETN"}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
