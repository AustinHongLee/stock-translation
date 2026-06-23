from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from app.analyze.financial import (
    FinancialMetrics,
    calculate_financial_metrics,
    financial_title,
    financial_tone,
)
from app.analyze.fundamental_trends import build_fundamental_trends
from app.analyze.historical_frequency import build_historical_frequency_report
from app.analyze.methods import MultipleValuation, RelativeValuationResult, calculate_relative_valuation
from app.analyze.valuation_bands import compute_valuation_bands
from app.analyze.summary import PriceSummary, calculate_price_summary
from app.analyze.stock_compare import (
    MIN_COMPARE_STOCKS,
    build_stock_comparison,
    normalize_compare_stock_ids,
)
from app.analyze.valuation import ValuationResult, calculate_dividend_valuation
from app.analyze.suitability import ValuationSuitability, assess_valuation_suitability
from app.analyze.vital_signs import VitalSignsReport, build_vital_signs_report
from app.analyze.watchlist_board import build_watchlist_board_item
from app.explain.rule_based import build_rule_based_health_report
from app.explain.validation import build_validation_brief

from app.catalog.stocks import StockCatalogEntry, search_stock_catalog
from app.chips import build_institutional_summary
from app.analyze.assessment import build_assessment
from app.analyze.levels import compute_support_resistance
from app.analyze.local_data import SORT_STOCK_ID, filter_sort_local_data_items
from app.models import DailyPrice, FinancialStatement, IntradayQuote, MonthlyRevenue, StockProfile
from app.portfolio import PriceSnapshot, calculate_portfolio
from app.portfolio.performance import PortfolioPerformance, calculate_portfolio_performance
from app.portfolio.models import PortfolioPosition, PortfolioResult, PortfolioTransaction
from app.quote.providers import QuoteProvider
from app.screener.value import DEFAULT_SCREENER_PATH, load_value_screener
from app.store.sqlite_store import SQLiteStore


HISTORICAL_VALUATION_DAYS = 365 * 5
LOCAL_DATA_CACHE_KEY = "local_data_v1"
LOCAL_DATA_CACHE_TTL_SECONDS = 300


def build_local_data_payload(store: SQLiteStore) -> dict[str, object]:
    """本地資料盤點：每檔已下載的日線檔數、最後資料日、是否過期、是否有法人，及波撐/波壓狀態。"""
    from datetime import date as _date
    today = _date.today()
    inst_ids = store.get_institutional_stock_ids()
    items: list[dict[str, object]] = []
    for sid in sorted(store.get_price_stock_ids()):
        prices = store.get_daily_prices(sid, limit=140)
        if not prices:
            continue
        last = prices[-1].date
        profile = store.get_profile(sid)
        name = (profile.short_name or profile.name) if profile else ""
        sr = compute_support_resistance(prices)
        items.append({
            "stock_id": sid,
            "name": name,
            "price_rows": store.count_daily_prices(sid),
            "last_date": last.isoformat(),
            "stale_days": (today - last).days,
            "has_institutional": sid in inst_ids,
            "sr_status": sr.get("status"),
            "support": sr.get("support"),
            "resistance": sr.get("resistance"),
        })
    items = filter_sort_local_data_items(items, sort_key=SORT_STOCK_ID)
    near = [it for it in items if it["sr_status"] in ("接近波撐", "接近波壓")]
    return {"generated_at": today.isoformat(), "count": len(items), "items": items, "near": near}


def build_cached_local_data_payload(
    store: SQLiteStore,
    *,
    max_age_seconds: int = LOCAL_DATA_CACHE_TTL_SECONDS,
) -> dict[str, object]:
    cached = store.get_json_cache(LOCAL_DATA_CACHE_KEY)
    if cached is not None:
        payload, updated_at = cached
        age = (datetime.now() - updated_at).total_seconds()
        if age <= max_age_seconds and isinstance(payload, dict):
            result = dict(payload)
            result["cache"] = {
                "hit": True,
                "updated_at": updated_at.isoformat(timespec="seconds"),
                "age_seconds": round(age),
                "ttl_seconds": max_age_seconds,
            }
            return result

    payload = build_local_data_payload(store)
    store.set_json_cache(LOCAL_DATA_CACHE_KEY, payload)
    result = dict(payload)
    result["cache"] = {
        "hit": False,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "age_seconds": 0,
        "ttl_seconds": max_age_seconds,
    }
    return result


def enrich_screener_with_levels(payload: dict[str, object], store: SQLiteStore) -> dict[str, object]:
    """對『本地已有日線』的個股，加上波段支撐/壓力接近狀態（其餘留空）。計算只讀本地、很快。"""
    items = payload.get("items")
    if not isinstance(items, list):
        return payload
    local_ids = store.get_price_stock_ids()
    for item in items:
        sid = str(item.get("stock_id", "")) if isinstance(item, dict) else ""
        if sid and sid in local_ids:
            prices = store.get_daily_prices(sid, limit=140)
            item["sr"] = compute_support_resistance(prices)
        elif isinstance(item, dict):
            item["sr"] = {"available": False, "status": ""}
    return payload


def build_value_screener_payload(path: Path = DEFAULT_SCREENER_PATH) -> dict[str, object]:
    return load_value_screener(path)


def build_local_stocks_payload(store: SQLiteStore) -> dict[str, object]:
    profiles = store.search_profiles("", limit=50)
    items: list[dict[str, object]] = []
    for profile in profiles:
        latest = store.get_daily_prices(profile.stock_id, limit=1)
        items.append(
            {
                "profile": profile_to_json(profile),
                "latest": price_to_json(latest[-1]) if latest else None,
                "rows": store.count_daily_prices(profile.stock_id),
            }
        )
    return {"items": items}


def build_watchlist_payload(store: SQLiteStore) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for row in store.list_watchlist():
        profile = None
        if row["name"]:
            profile = StockProfile(
                stock_id=row["stock_id"],
                market=row["market"],
                name=row["name"],
                short_name=row["short_name"],
                industry_code=row["industry_code"],
                listed_date=_date_or_none(row["listed_date"]),
                source_updated_at=_date_or_none(row["source_updated_at"]),
            )
        prices = store.get_daily_prices(row["stock_id"], limit=260)
        profile_json = profile_to_json(profile) if profile else None
        items.append(
            {
                "stock_id": row["stock_id"],
                "profile": profile_json,
                "latest": price_to_json(prices[-1]) if prices else None,
                "rows": store.count_daily_prices(row["stock_id"]),
                "added_at": row["added_at"],
                "note": row["note"],
                "board": build_watchlist_board_item(row["stock_id"], profile_json, prices),
            }
        )
    return {"items": items}


def build_compare_payload(store: SQLiteStore, stock_ids: str | list[str]) -> dict[str, object]:
    ids = normalize_compare_stock_ids(stock_ids)
    if len(ids) < MIN_COMPARE_STOCKS:
        raise ValueError("請輸入 2–3 檔股票代號。")
    items: list[dict[str, object]] = []
    for stock_id in ids:
        items.append(
            {
                "stock_id": stock_id,
                "profile": store.get_profile(stock_id),
                "prices": store.get_daily_prices(stock_id, limit=260),
                "institutional_trades": store.get_institutional_trades(stock_id, limit=60),
                "monthly_revenues": store.get_monthly_revenues(stock_id, limit=3),
                "financial_statements": store.get_financial_statements(stock_id, limit=4),
            }
        )
    payload = build_stock_comparison(items)
    payload["requested"] = ids
    return payload


def build_search_payload(
    store: SQLiteStore,
    query: str,
    *,
    catalog_path: Path | None = None,
) -> dict[str, object]:
    query = query.strip()
    results: list[dict[str, object]] = []
    seen: set[str] = set()

    catalog_results = search_stock_catalog(
        query,
        limit=30,
        **({"path": catalog_path} if catalog_path is not None else {}),
    )
    for entry in catalog_results:
        local_profile = store.get_profile(entry.stock_id)
        if local_profile is not None:
            item = profile_to_json(local_profile)
            item["is_local"] = True
            item["match_source"] = "catalog_local"
        else:
            item = catalog_entry_to_json(entry)
            item["is_local"] = False
            item["match_source"] = "catalog"
        results.append(item)
        seen.add(str(item["stock_id"]))
        if len(results) >= 20:
            break

    if len(results) < 20:
        for profile in store.search_profiles(query, limit=20):
            if profile.stock_id in seen:
                continue
            item = profile_to_json(profile)
            item["is_local"] = True
            item["match_source"] = "local"
            results.append(item)
            seen.add(profile.stock_id)
            if len(results) >= 20:
                break

    exact_result = any(str(item.get("stock_id", "")) == query for item in results)
    return {
        "query": query,
        "results": results,
        "can_sync": query.isdecimal() and len(query) >= 4 and not exact_result,
    }


def build_portfolio_payload(store: SQLiteStore) -> dict[str, object]:
    transactions = store.get_portfolio_transactions()
    stock_ids = sorted({item.stock_id for item in transactions})
    latest_prices = {
        stock_id: _latest_price_snapshot(store, stock_id)
        for stock_id in stock_ids
    }
    profiles = {
        stock_id: store.get_profile(stock_id)
        for stock_id in stock_ids
    }
    result = calculate_portfolio(transactions, latest_prices)
    dividends_by_stock = {
        stock_id: store.get_dividend_records(stock_id)
        for stock_id in stock_ids
    }
    benchmark_prices = store.get_daily_prices("0050") if transactions else []
    performance = calculate_portfolio_performance(
        portfolio=result,
        transactions=transactions,
        dividends_by_stock=dividends_by_stock,
        latest_prices=latest_prices,
        benchmark_prices=benchmark_prices,
        benchmark_symbol="0050",
        benchmark_name="0050 台灣50",
    )
    return {
        "summary": portfolio_summary_to_json(result),
        "performance": portfolio_performance_to_json(performance),
        "positions": [
            portfolio_position_to_json(position, profiles.get(position.stock_id))
            for position in result.positions
        ],
        "transactions": [
            portfolio_transaction_to_json(transaction, profiles.get(transaction.stock_id))
            for transaction in transactions
        ],
        "limitations": [
            "第一版採移動平均成本法。",
            "市值與帳面損益使用最近收盤價估算，不是即時成交價。",
            "含息報酬目前只納入可辨識除息日的現金股利；股票股利、除權息成本調整、完整稅務與多帳戶尚未納入。",
            "所有內容只描述資料狀態，不構成買賣建議。",
        ],
        "expert_checks": [
            "買進總成本是否應包含手續費。",
            "賣出收入是否正確扣除手續費與證交稅。",
            "含息總報酬是否等於帳面損益 + 已實現損益 + 累計現金股利。",
            "XIRR 與 0050 對比是否符合你們平常看的口徑。",
            "第一版使用移動平均成本法是否符合預期。",
            "白話文案是否可能讓新手誤以為是買賣建議。",
            "尚未納入股票股利與除權息成本調整的限制是否標示清楚。",
        ],
    }


def build_daily_price_payload(store: SQLiteStore, stock_id: str, day: str) -> dict[str, object]:
    """查某檔在指定日期（或最近一個不晚於該日的交易日）的開高低收，供交易表單半自動帶價。"""
    stock_id = (stock_id or "").strip()
    day = (day or "").strip()
    if not stock_id or not day:
        return {"available": False, "message": "缺少股票代號或日期"}
    try:
        target = date.fromisoformat(day)
    except ValueError:
        return {"available": False, "message": "日期格式不正確"}
    prices = store.get_daily_prices(
        stock_id,
        start_date=target - timedelta(days=14),
        end_date=target,
    )
    if not prices:
        return {"available": False, "message": "本地沒有這段期間的日線資料，請先同步這檔股票。"}
    chosen = prices[-1]  # 升冪排序，取最近且不晚於該日的交易日
    return {
        "available": True,
        "requested_date": day,
        "date": chosen.date.isoformat(),
        "is_exact": chosen.date == target,
        "open": chosen.open,
        "high": chosen.high,
        "low": chosen.low,
        "close": chosen.close,
    }


def _chips_trades_for(store: SQLiteStore, stock_id: str):
    """近一年（最多 400 筆）三大法人買賣超，由舊到新。"""
    return store.get_institutional_trades(stock_id, limit=400)


def institutional_to_json(trade) -> dict[str, object]:
    return {
        "date": trade.date.isoformat(),
        "foreign_net": int(trade.foreign_net),
        "trust_net": int(trade.trust_net),
        "dealer_net": int(trade.dealer_net),
        "total_net": int(trade.total_net),
    }


def build_stock_payload(
    store: SQLiteStore,
    stock_id: str,
    *,
    days: int = 365,
    quote_provider: QuoteProvider | None = None,
) -> dict[str, object]:
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    profile = store.get_profile(stock_id)
    prices = store.get_daily_prices(
        stock_id,
        start_date=start_date,
        end_date=end_date,
    )
    if not prices:
        prices = store.get_daily_prices(stock_id, limit=days)
    latest_close = prices[-1].close if prices else None
    valuation_prices = store.get_daily_prices(
        stock_id,
        start_date=end_date - timedelta(days=HISTORICAL_VALUATION_DAYS),
        end_date=end_date,
    )
    if latest_close is None and valuation_prices:
        latest_close = valuation_prices[-1].close
    monthly_revenues = store.get_monthly_revenues(stock_id, limit=12)
    financial_statements = store.get_financial_statements(stock_id, limit=8)
    latest_financial = financial_statements[0] if financial_statements else None
    summary = calculate_price_summary(prices)

    dividend_records = store.get_dividend_records(stock_id)
    market_valuation = store.get_latest_market_valuation(stock_id)
    dividend_valuation = calculate_dividend_valuation(
        dividend_records,
        market_valuation,
        latest_close,
        prices=valuation_prices,
        historical_years=5,
        listed_date=profile.listed_date if profile else None,
    )
    suitability = assess_valuation_suitability(
        dividends=dividend_records,
        financials=financial_statements,
        market=market_valuation,
        latest_close=latest_close,
        profile=profile,
        as_of_date=end_date,
    )
    relative_valuation = calculate_relative_valuation(
        financials=financial_statements,
        market=market_valuation,
        latest_close=latest_close,
        suitability=suitability,
    )
    valuation_payload = valuation_to_json(dividend_valuation)
    valuation_payload["suitability"] = suitability_to_json(suitability)
    valuation_payload["relative"] = relative_valuation_to_json(relative_valuation)
    valuation_payload["vital_signs"] = vital_signs_to_json(
        build_vital_signs_report(
            monthly_revenues=monthly_revenues,
            financials=financial_statements,
        )
    )
    # 歷史本益比／本淨比河流圖（用較長的價格與財報歷史還原；失敗不影響個股頁）。
    try:
        valuation_payload["bands"] = compute_valuation_bands(
            valuation_prices or prices,
            store.get_financial_statements(stock_id, limit=24),
            today=end_date,
            years=5,
        )
    except Exception:  # noqa: BLE001 - 河流圖是加值資訊，壞掉就不顯示
        valuation_payload["bands"] = None

    chips_trades = _chips_trades_for(store, stock_id)
    chips_summary = build_institutional_summary(chips_trades)
    revenue_summary_payload = revenue_summary_to_json(monthly_revenues)
    financial_summary_payload = financial_summary_to_json(latest_financial)
    assessment_payload = build_assessment(
        [price_to_json(item) for item in prices],
        valuation=valuation_payload,
        chips=chips_summary,
        revenue_summary=revenue_summary_payload,
        financial_summary=financial_summary_payload,
    )

    return {
        "profile": profile_to_json(profile) if profile else None,
        "prices": [price_to_json(item) for item in prices],
        "summary": summary_to_json(summary),
        "price_window": price_window_to_json(
            summary,
            requested_start=start_date,
            requested_end=end_date,
        ),
        "quote": build_quote_payload(
            stock_id,
            quote_provider=quote_provider,
            latest_close=latest_close,
        )["quote"],
        "report": build_rule_based_health_report(
            profile=profile,
            prices=prices,
            financial_statement=latest_financial,
            suitability=suitability,
            valuation=dividend_valuation,
        ),
        "validation": build_validation_brief(prices),
        "dividends": [dividend_to_json(item) for item in store.get_dividend_records(stock_id)],
        "monthly_revenues": [monthly_revenue_to_json(item) for item in monthly_revenues],
        "revenue_summary": revenue_summary_payload,
        "financial_statements": [
            financial_statement_to_json(item) for item in financial_statements
        ],
        "financial_summary": financial_summary_payload,
        "fundamental_trends": build_fundamental_trends(financial_statements),
        "historical_frequency": build_historical_frequency_report(prices),
        "valuation": valuation_payload,
        "brief": stock_brief_to_json(profile, suitability),
        "chips": chips_summary,
        "chips_series": [institutional_to_json(t) for t in chips_trades],
        "assessment": assessment_payload,
        "is_watchlisted": store.is_watchlisted(stock_id),
    }


def portfolio_summary_to_json(result: PortfolioResult) -> dict[str, object]:
    missing_price_count = sum(1 for item in result.positions if item.market_value is None)
    return {
        "positions_count": len(result.positions),
        "transactions_count": len(result.transactions),
        "realized_pnl": result.realized_pnl,
        "total_cost_basis": result.total_cost_basis,
        "total_market_value": result.total_market_value,
        "total_unrealized_pnl": result.total_unrealized_pnl,
        "total_unrealized_return_percent": result.total_unrealized_return_percent,
        "missing_price_count": missing_price_count,
        "sentence": portfolio_sentence(result, missing_price_count),
        "price_basis": "最近收盤價",
        "cost_method": "移動平均成本法",
    }


def portfolio_performance_to_json(performance: PortfolioPerformance) -> dict[str, object]:
    benchmark = performance.benchmark
    return {
        "total_cash_dividends": performance.total_cash_dividends,
        "total_return_amount": performance.total_return_amount,
        "total_return_percent": performance.total_return_percent,
        "xirr_percent": performance.xirr_percent,
        "dividend_data_complete": performance.dividend_data_complete,
        "notes": performance.notes,
        "cash_dividend_events": [
            {
                "stock_id": item.stock_id,
                "ex_date": item.ex_date.isoformat(),
                "shares": item.shares,
                "cash_dividend_per_share": item.cash_dividend_per_share,
                "cash_amount": item.cash_amount,
                "source": item.source,
            }
            for item in performance.cash_dividend_events
        ],
        "benchmark": (
            {
                "symbol": benchmark.symbol,
                "name": benchmark.name,
                "total_return_amount": benchmark.total_return_amount,
                "total_return_percent": benchmark.total_return_percent,
                "xirr_percent": benchmark.xirr_percent,
                "latest_value": benchmark.latest_value,
                "latest_date": benchmark.latest_date.isoformat()
                if benchmark.latest_date
                else None,
                "status": benchmark.status,
                "note": benchmark.note,
            }
            if benchmark
            else None
        ),
    }


def portfolio_sentence(result: PortfolioResult, missing_price_count: int) -> str:
    if not result.transactions:
        return "尚未新增交易。先輸入一筆買進，系統會用最近收盤價估算目前帳面狀態。"
    if not result.positions:
        realized = format_money_text(result.realized_pnl)
        return f"目前沒有持股；已實現損益合計約 {realized}。這只是交易紀錄整理，不代表投資建議。"
    if missing_price_count:
        return (
            f"目前有 {len(result.positions)} 檔持倉，其中 {missing_price_count} 檔缺少最近收盤價，"
            "所以暫時不能完整估算市值與帳面損益。"
        )
    pnl = result.total_unrealized_pnl or 0
    direction = "帳面約賺" if pnl > 0 else "帳面約虧" if pnl < 0 else "帳面大致持平"
    return (
        f"以最近收盤價估算，你目前持有 {len(result.positions)} 檔，"
        f"{direction} {format_money_text(abs(pnl))}"
        f"（{format_percent_text(result.total_unrealized_return_percent)}）。"
        "這還不是落袋損益，也尚未納入股利與除權息。"
    )


def portfolio_position_to_json(
    position: PortfolioPosition,
    profile: StockProfile | None,
) -> dict[str, object]:
    return {
        "stock_id": position.stock_id,
        "profile": profile_to_json(profile) if profile else None,
        "shares": position.shares,
        "average_cost": position.average_cost,
        "cost_basis": position.cost_basis,
        "latest_close": position.latest_close,
        "latest_close_date": (
            position.latest_close_date.isoformat() if position.latest_close_date else None
        ),
        "market_value": position.market_value,
        "unrealized_pnl": position.unrealized_pnl,
        "unrealized_return_percent": position.unrealized_return_percent,
    }


def portfolio_transaction_to_json(
    transaction: PortfolioTransaction,
    profile: StockProfile | None = None,
) -> dict[str, object]:
    return {
        "id": transaction.id,
        "stock_id": transaction.stock_id,
        "profile": profile_to_json(profile) if profile else None,
        "trade_date": transaction.trade_date.isoformat(),
        "side": transaction.side,
        "shares": transaction.shares,
        "price": transaction.price,
        "fee": transaction.fee,
        "tax": transaction.tax,
        "note": transaction.note,
        "created_at": (
            transaction.created_at.isoformat(timespec="seconds")
            if transaction.created_at
            else None
        ),
        "updated_at": (
            transaction.updated_at.isoformat(timespec="seconds")
            if transaction.updated_at
            else None
        ),
    }


def _latest_price_snapshot(store: SQLiteStore, stock_id: str) -> PriceSnapshot | None:
    latest = store.get_daily_prices(stock_id, limit=1)
    if not latest:
        return None
    price = latest[-1]
    return PriceSnapshot(close=price.close, date=price.date)


def build_quote_payload(
    stock_id: str,
    *,
    quote_provider: QuoteProvider | None,
    latest_close: float | None = None,
) -> dict[str, object]:
    if quote_provider is None:
        return {
            "quote": unavailable_quote_to_json(
                "尚未啟用盤中報價來源，目前只顯示日線收盤分析。",
                latest_close=latest_close,
            )
        }

    try:
        quote = quote_provider.fetch_quote(stock_id)
    except Exception as exc:
        return {
            "quote": unavailable_quote_to_json(
                f"盤中報價暫時取不到：{exc}",
                latest_close=latest_close,
            )
        }

    if quote is None:
        return {
            "quote": unavailable_quote_to_json(
                "盤中報價來源沒有回傳這檔股票。",
                latest_close=latest_close,
            )
        }
    return {"quote": quote_to_json(quote, latest_close=latest_close)}


def profile_to_json(profile: StockProfile) -> dict[str, object]:
    return {
        "stock_id": profile.stock_id,
        "name": profile.name,
        "short_name": profile.short_name,
        "industry_code": profile.industry_code,
        "industry_label": industry_label(profile.industry_code),
        "market": profile.market,
        "listed_date": profile.listed_date.isoformat() if profile.listed_date else None,
        "source_updated_at": (
            profile.source_updated_at.isoformat()
            if profile.source_updated_at
            else None
        ),
    }


# 證交所（TWSE）上市產業別代碼 → 中文（與主計總處行業標準分類不同系統）
_INDUSTRY_LABELS = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造業",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險業",
    "18": "貿易百貨業",
    "19": "綜合企業",
    "20": "其他業",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技業",
    "34": "電子商務",
    "35": "綠能環保業",
    "36": "數位雲端業",
    "37": "運動休閒",
    "38": "居家生活",
    "80": "管理股票",
}


def industry_label(industry_code: str | None) -> str | None:
    if not industry_code:
        return None
    return _INDUSTRY_LABELS.get(industry_code, f"產業代碼 {industry_code}")


def stock_brief_to_json(
    profile: StockProfile | None,
    suitability: ValuationSuitability,
) -> dict[str, object]:
    name = profile.short_name if profile else "這家公司"
    industry = industry_label(profile.industry_code if profile else None)
    company_sentence = (
        f"{name} 屬於 {industry}。"
        if industry
        else f"{name} 的產業資料待補。"
    )
    risk_tags = _risk_tags(suitability)
    valuation_sentence = _brief_valuation_sentence(suitability)
    beginner_sentence = _brief_beginner_sentence(suitability)
    return {
        "company_sentence": company_sentence,
        "valuation_sentence": valuation_sentence,
        "beginner_sentence": beginner_sentence,
        "watch_items": _brief_watch_items(suitability),
        "risk_tags": risk_tags,
        "non_advice": "這是資料翻譯，不是買賣建議，也不預測股價。",
    }


def _brief_valuation_sentence(suitability: ValuationSuitability) -> str:
    if suitability.recommended_primary == "none":
        return "目前先不估價；先確認營收、獲利與風險是否站穩。"
    if suitability.company_type == "construction":
        return "盈餘常受建案認列影響，先用 PB/資產角度輔助觀察。"
    if suitability.company_type == "cyclical":
        return "獲利可能跟景氣起伏，PE 與股利法都要降權看。"
    if "yield_too_low" in suitability.reasons:
        return "股利不是主要報酬來源，股利法不適合當主尺。"
    if "low_yield" in suitability.reasons:
        return "殖利率偏低，股利法只能當輔助，先搭配 PE/PB 與獲利趨勢看。"
    if suitability.company_type == "mature_dividend":
        return "配息資料較完整，股利法可作為其中一把尺。"
    return "先看適用方法與資料信心，再展開數字情境。"


def _brief_beginner_sentence(suitability: ValuationSuitability) -> str:
    if suitability.recommended_primary == "none":
        return "新手先不要急著套公式，先確認資料是否足夠、獲利是否穩定、風險標籤有沒有亮起。"
    if suitability.company_type == "etf":
        return "ETF 先看追蹤標的、費用、折溢價與配息紀錄，不用單一公司獲利邏輯。"
    if suitability.company_type == "cyclical":
        return "循環股先看景氣位置、毛利率與庫存，再把倍數情境當成輔助。"
    if suitability.company_type == "growth":
        return "成長型公司先看營收動能、毛利率與投入成長是否反映在獲利。"
    if suitability.company_type == "construction":
        return "營建或資產型公司先看建案認列、資產負債與現金流節奏。"
    if "low_yield" in suitability.reasons or "yield_too_low" in suitability.reasons:
        return "股利占比不高時，先把本業獲利與成長資料看完，再看股利情境。"
    return "先看資料信心與主要方法，再往下看營收、獲利、估值位階與消息風險。"


def _brief_watch_items(suitability: ValuationSuitability) -> list[str]:
    items: list[str] = []
    reason_set = set(suitability.reasons)
    if reason_set & {"insufficient_data", "short_history", "newly_listed"}:
        items.append("資料年數偏短，先確認樣本期間。")
    if reason_set & {"loss_history"}:
        items.append("近年曾虧損，先看虧損來源與是否改善。")
    if reason_set & {"unstable_dividend", "one_off_dividend"}:
        items.append("配息波動較大，平均數容易失真。")
    if reason_set & {"cyclical"}:
        items.append("景氣循環明顯，留意毛利率與庫存變化。")
    if reason_set & {"growth_stock", "yield_too_low", "low_yield"}:
        items.append("股利不是主軸，回到營收與獲利成長檢查。")
    if reason_set & {"high_payout"}:
        items.append("配息率偏高，確認獲利是否足以支撐。")
    if reason_set & {"etf"}:
        items.append("ETF 先看成分、費用與折溢價。")
    if not items:
        items.append("資料信心較完整，但仍要搭配營收、獲利與波動一起看。")
    items.append("所有情境都只是資料整理，不是操作指令。")
    return items[:4]


def _risk_tags(suitability: ValuationSuitability) -> list[str]:
    tags: list[str] = []
    if suitability.company_type_label:
        tags.append(suitability.company_type_label)
    reason_tags = {
        "yield_too_low": "低殖利率",
        "low_yield": "低殖利率",
        "newly_listed": "新上市",
        "insufficient_data": "股利資料短",
        "loss_history": "近年曾虧損",
        "cyclical": "景氣循環",
        "growth_stock": "成長取向",
        "high_payout": "配息率偏高",
        "one_off_dividend": "一次性股利風險",
        "unstable_dividend": "配息不穩",
    }
    for code in suitability.reasons:
        label = reason_tags.get(code)
        if label and label not in tags:
            tags.append(label)
    return tags[:5]


def catalog_entry_to_json(entry: StockCatalogEntry) -> dict[str, object]:
    return {
        "stock_id": entry.stock_id,
        "name": entry.name,
        "short_name": entry.short_name,
        "industry_code": None,
        "industry_label": None,
        "market": entry.market,
        "listed_date": None,
        "source_updated_at": None,
    }


def price_to_json(price: DailyPrice) -> dict[str, object]:
    return {
        "stock_id": price.stock_id,
        "date": price.date.isoformat(),
        "open": price.open,
        "high": price.high,
        "low": price.low,
        "close": price.close,
        "volume": price.volume,
        "trade_value": price.trade_value,
        "transaction_count": price.transaction_count,
        "change": price.change,
        "note": price.note,
        "source": price.source,
    }


def quote_to_json(quote: IntradayQuote, *, latest_close: float | None = None) -> dict[str, object]:
    midpoint = _midpoint(quote.best_bid_price, quote.best_ask_price)
    display_price = quote.current_price if quote.current_price is not None else midpoint
    display_price_label = "目前成交價" if quote.current_price is not None else "買賣中間價"
    display_change = _difference(display_price, quote.previous_close)
    display_change_percent = _percent_change(display_change, quote.previous_close)
    spread = _difference(quote.best_ask_price, quote.best_bid_price)
    spread_percent = _percent_change(spread, display_price)
    if quote.current_price is None and midpoint is not None:
        message = "成交價欄位暫無值，先用買一與賣一中間價當參考，不代表實際成交價。"
    else:
        message = "盤中資料會跳動，白話健檢仍以日線與基本資料為主。"

    return {
        "available": True,
        "status": "active" if quote.current_price is not None else "reference_only",
        "status_label": "盤中成交價" if quote.current_price is not None else "買賣價參考",
        "stock_id": quote.stock_id,
        "name": quote.name,
        "full_name": quote.full_name,
        "trade_datetime": (
            quote.trade_datetime.isoformat(sep=" ", timespec="seconds")
            if quote.trade_datetime
            else None
        ),
        "current_price": quote.current_price,
        "display_price": display_price,
        "display_price_label": display_price_label,
        "display_change": display_change,
        "display_change_percent": display_change_percent,
        "previous_close": quote.previous_close,
        "latest_close": latest_close,
        "open_price": quote.open_price,
        "high_price": quote.high_price,
        "low_price": quote.low_price,
        "volume": quote.volume,
        "best_bid_price": quote.best_bid_price,
        "best_ask_price": quote.best_ask_price,
        "spread": spread,
        "spread_percent": spread_percent,
        "bid_prices": list(quote.bid_prices),
        "ask_prices": list(quote.ask_prices),
        "source": quote.source,
        "source_delay_ms": quote.source_delay_ms,
        "message": message,
    }


def unavailable_quote_to_json(
    message: str,
    *,
    latest_close: float | None = None,
) -> dict[str, object]:
    return {
        "available": False,
        "status": "unavailable",
        "status_label": "未取得盤中報價",
        "display_price": latest_close,
        "display_price_label": "最近收盤",
        "display_change": None,
        "display_change_percent": None,
        "previous_close": None,
        "latest_close": latest_close,
        "open_price": None,
        "high_price": None,
        "low_price": None,
        "volume": None,
        "best_bid_price": None,
        "best_ask_price": None,
        "spread": None,
        "spread_percent": None,
        "source": None,
        "message": message,
    }


def dividend_to_json(record) -> dict[str, object]:
    return {
        "stock_id": record.stock_id,
        "year": record.year,
        "period": record.period,
        "status": record.status,
        "board_date": record.board_date.isoformat() if record.board_date else None,
        "shareholder_meeting_date": (
            record.shareholder_meeting_date.isoformat()
            if record.shareholder_meeting_date
            else None
        ),
        "cash_dividend": record.cash_dividend,
        "stock_dividend": record.stock_dividend,
        "source_updated_at": (
            record.source_updated_at.isoformat() if record.source_updated_at else None
        ),
        "note": record.note,
        "source": record.source,
    }


def monthly_revenue_to_json(record: MonthlyRevenue) -> dict[str, object]:
    return {
        "stock_id": record.stock_id,
        "year_month": record.year_month,
        "company_name": record.company_name,
        "industry": record.industry,
        "current_month_revenue": record.current_month_revenue,
        "previous_month_revenue": record.previous_month_revenue,
        "last_year_month_revenue": record.last_year_month_revenue,
        "mom_percent": record.mom_percent,
        "yoy_percent": record.yoy_percent,
        "cumulative_revenue": record.cumulative_revenue,
        "cumulative_last_year_revenue": record.cumulative_last_year_revenue,
        "cumulative_yoy_percent": record.cumulative_yoy_percent,
        "source_updated_at": (
            record.source_updated_at.isoformat() if record.source_updated_at else None
        ),
        "note": record.note,
        "source": record.source,
    }


def financial_statement_to_json(record: FinancialStatement) -> dict[str, object]:
    metrics = calculate_financial_metrics(record)
    return {
        "stock_id": record.stock_id,
        "year": record.year,
        "quarter": record.quarter,
        "quarter_label": metrics.quarter_label,
        "company_name": record.company_name,
        "revenue": record.revenue,
        "gross_profit": record.gross_profit,
        "operating_income": record.operating_income,
        "non_operating_income_expense": record.non_operating_income_expense,
        "pre_tax_income": record.pre_tax_income,
        "net_income": record.net_income,
        "parent_net_income": record.parent_net_income,
        "eps": record.eps,
        "total_assets": record.total_assets,
        "total_liabilities": record.total_liabilities,
        "parent_equity": record.parent_equity,
        "total_equity": record.total_equity,
        "book_value_per_share": record.book_value_per_share,
        "gross_margin_percent": metrics.gross_margin_percent,
        "operating_margin_percent": metrics.operating_margin_percent,
        "net_margin_percent": metrics.net_margin_percent,
        "roe_percent": metrics.roe_percent,
        "roa_percent": metrics.roa_percent,
        "source_updated_at": (
            record.source_updated_at.isoformat() if record.source_updated_at else None
        ),
        "source": record.source,
    }


def financial_summary_to_json(record: FinancialStatement | None) -> dict[str, object]:
    if record is None:
        return {
            "available": False,
            "title": "獲利資料待補",
            "tone": "unknown",
            "sentence": "目前還沒有同步最新季財報，無法判斷 EPS、ROE 或 ROA。",
            "facts": [],
        }

    metrics = calculate_financial_metrics(record)
    return {
        "available": True,
        "title": financial_title(metrics),
        "tone": financial_tone(metrics),
        "sentence": (
            f"{metrics.quarter_label} EPS {format_number_text(metrics.eps)}，"
            f"淨利率 {format_percent_text(metrics.net_margin_percent)}，"
            f"單季 ROE {format_percent_text(metrics.roe_percent)}。"
        ),
        "facts": [
            {"label": "季度", "value": metrics.quarter_label},
            {"label": "EPS", "value": metrics.eps},
            {"label": "毛利率", "value": metrics.gross_margin_percent},
            {"label": "營益率", "value": metrics.operating_margin_percent},
            {"label": "淨利率", "value": metrics.net_margin_percent},
            {"label": "單季 ROE", "value": metrics.roe_percent},
            {"label": "單季 ROA", "value": metrics.roa_percent},
        ],
        "source_updated_at": record.source_updated_at.isoformat()
        if record.source_updated_at
        else None,
    }


def revenue_summary_to_json(records: list[MonthlyRevenue]) -> dict[str, object]:
    if not records:
        return {
            "available": False,
            "title": "每月營收待補",
            "tone": "unknown",
            "sentence": "目前還沒有同步到每月營收，無法判斷公司最近生意是否成長。",
            "facts": [],
        }

    latest = records[0]
    yoy = latest.yoy_percent
    cumulative_yoy = latest.cumulative_yoy_percent
    if yoy is None:
        tone = "unknown"
        title = "營收資料不足"
    elif yoy >= 20:
        tone = "positive"
        title = "近期營收成長明顯"
    elif yoy >= 0:
        tone = "neutral"
        title = "近期營收仍在成長"
    else:
        tone = "caution"
        title = "近期營收衰退"

    sentence = (
        f"{latest.year_month} 月營收年增 {format_percent_text(yoy)}，"
        f"累計年增 {format_percent_text(cumulative_yoy)}。"
        "這能幫你判斷公司最近生意量是擴張還是收縮。"
    )
    return {
        "available": True,
        "title": title,
        "tone": tone,
        "sentence": sentence,
        "facts": [
            {"label": "最新月份", "value": latest.year_month},
            {"label": "當月營收", "value": latest.current_month_revenue},
            {"label": "月增率", "value": latest.mom_percent},
            {"label": "年增率", "value": latest.yoy_percent},
            {"label": "累計年增率", "value": latest.cumulative_yoy_percent},
        ],
        "source_updated_at": latest.source_updated_at.isoformat()
        if latest.source_updated_at
        else None,
    }


def summary_to_json(summary: PriceSummary) -> dict[str, object]:
    return {
        "rows": summary.rows,
        "start_date": summary.start_date,
        "end_date": summary.end_date,
        "latest_close": summary.latest_close,
        "previous_close": summary.previous_close,
        "change": summary.change,
        "change_percent": summary.change_percent,
        "change_source": summary.change_source,
        "change_note": summary.change_note,
        "high": summary.high,
        "low": summary.low,
        "price_position": summary.price_position,
    }


def price_window_to_json(
    summary: PriceSummary,
    *,
    requested_start: date,
    requested_end: date,
) -> dict[str, object]:
    actual_end = date.fromisoformat(summary.end_date) if summary.end_date else None
    stale_days = (requested_end - actual_end).days if actual_end else None
    is_stale = stale_days is None or stale_days > 10
    is_partial = (
        summary.start_date is None
        or summary.end_date is None
        or is_stale
        or date.fromisoformat(summary.start_date) > requested_start + timedelta(days=10)
    )
    label = "--"
    if summary.start_date and summary.end_date:
        label = f"{summary.start_date} 至 {summary.end_date}"
        if stale_days is not None and stale_days > 10:
            label += f" · 資料過期 {stale_days} 天"
    return {
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "actual_start": summary.start_date,
        "actual_end": summary.end_date,
        "stale_days": stale_days,
        "is_stale": is_stale,
        "is_partial": is_partial,
        "label": label,
    }


_SUITABILITY_REASON_TEXT = {
    "yield_too_low": "殖利率過低，股利不是主要報酬來源，股利反推價格不具參考性。",
    "loss_history": "公司近年曾虧損，沒有穩定獲利支撐配息。",
    "insufficient_data": "股利資料不足（少於 3 年），平均值還不穩。",
    "newly_listed": "上市未滿 3 年，價格與配息歷史都太短。",
    "unstable_dividend": "配息忽高忽低，平均會失真。",
    "cyclical": "景氣循環股，歷史平均股利在循環高／低點都會誤導。",
    "growth_stock": "比較像成長股，少配息、把錢留著擴張，該看本益比與成長性。",
    "low_yield": "殖利率偏低，股利法參考性下降。",
    "high_payout": "配息率偏高，可能在吃老本。",
    "one_off_dividend": "過去曾有一次性高股利，已留意但仍要小心。",
    "short_history": "只有 3–4 年資料，尚非完整 5 年樣本。",
    "etf": "ETF 沒有單一公司獲利，不適用個股股利法。",
}

_METHOD_LABEL = {
    "yield": "殖利率法",
    "pe_band": "本益比（PE）敏感度",
    "pb_band": "本淨比（PB）敏感度",
    "revenue_momentum": "營收動能",
    "gross_margin_trend": "毛利率趨勢",
    "roe": "股東權益報酬率（ROE）",
    "distribution_yield_band": "配息殖利率區間",
    "premium_discount": "折溢價（對淨值）",
    "peer_pe_pb": "與同業本益比／本淨比比較",
    "pe_single": "單一本益比",
    "none": "暫不估價",
}

_CONFIDENCE_LABEL = {"high": "信心較高", "medium": "信心中等", "low": "低信心"}
_STATE_LABEL = {
    "applicable": "股利法適用",
    "low_confidence": "股利法參考性低",
    "not_applicable": "股利法不適合",
}


def suitability_to_json(result: ValuationSuitability) -> dict[str, object]:
    return {
        "company_type": result.company_type,
        "company_type_label": result.company_type_label,
        "state": result.state,
        "state_label": _STATE_LABEL.get(result.state, result.state),
        "headline": result.headline,
        "reasons": result.reasons,
        "reason_texts": [
            _SUITABILITY_REASON_TEXT[code]
            for code in result.reasons
            if code in _SUITABILITY_REASON_TEXT
        ],
        "show_values": result.state != "not_applicable",
        "recommended": {
            "primary": result.recommended_primary,
            "primary_label": _METHOD_LABEL.get(result.recommended_primary, result.recommended_primary),
            "secondary_labels": [
                _METHOD_LABEL.get(code, code) for code in result.recommended_secondary
            ],
            "avoid_labels": [
                _METHOD_LABEL.get(code, code) for code in result.recommended_avoid
            ],
        },
        "data_confidence": result.data_confidence,
        "data_confidence_label": _CONFIDENCE_LABEL.get(result.data_confidence, "信心中等"),
    }


def valuation_to_json(result: ValuationResult) -> dict[str, object]:
    market = result.market
    historical = result.historical_yield
    return {
        "dividend_summary": {
            "rows": result.dividend_summary.rows,
            "average_cash_dividend": result.dividend_summary.average_cash_dividend,
            "latest_cash_dividend": result.dividend_summary.latest_cash_dividend,
            "latest_stock_dividend": result.dividend_summary.latest_stock_dividend,
            "years": result.dividend_summary.years,
            "estimate_source": result.dividend_summary.estimate_source,
        },
        "estimates": [
            {
                "scenario": item.scenario,
                "target_yield_percent": item.target_yield_percent,
                "price": item.price,
            }
            for item in result.estimates
        ],
        "historical_yield": (
            {
                "years": [
                    {
                        "year": item.year,
                        "cash_dividend": item.cash_dividend,
                        "average_close": item.average_close,
                        "yield_percent": item.yield_percent,
                    }
                    for item in historical.years
                ],
                "years_count": len(historical.years),
                "average_yield_percent": historical.average_yield_percent,
                "high_yield_percent": historical.high_yield_percent,
                "low_yield_percent": historical.low_yield_percent,
                "latest_close": historical.latest_close,
                "cheap_difference": historical.cheap_difference,
                "cheap_difference_percent": historical.cheap_difference_percent,
                "price_basis": historical.price_basis,
                "estimates": [
                    {
                        "scenario": item.scenario,
                        "target_yield_percent": item.target_yield_percent,
                        "price": item.price,
                    }
                    for item in historical.estimates
                ],
            }
            if historical
            else None
        ),
        "confidence": result.confidence,
        "suitability_notes": result.suitability_notes,
        "market": (
            {
                "date": market.date.isoformat(),
                "pe_ratio": market.pe_ratio,
                "dividend_yield": market.dividend_yield,
                "pb_ratio": market.pb_ratio,
                "source": market.source,
            }
            if market
            else None
        ),
        "warning": result.warning,
    }


def relative_valuation_to_json(result: RelativeValuationResult) -> dict[str, object]:
    return {
        "status": result.status,
        "headline": result.headline,
        "notes": result.notes or [],
        "primary_method": result.primary_method,
        "methods": [multiple_valuation_to_json(item) for item in result.methods],
    }


def vital_signs_to_json(result: VitalSignsReport) -> dict[str, object]:
    return {
        "title": result.title,
        "tone": result.tone,
        "sentence": result.sentence,
        "facts": [
            {
                "key": item.key,
                "label": item.label,
                "value": item.value,
                "tone": item.tone,
                "text": item.text,
            }
            for item in result.facts
        ],
    }


def multiple_valuation_to_json(item: MultipleValuation) -> dict[str, object]:
    return {
        "method": item.method,
        "title": item.title,
        "headline": item.headline,
        "basis_label": item.basis_label,
        "basis_value": item.basis_value,
        "basis_source": item.basis_source,
        "current_multiple": item.current_multiple,
        "multiple_label": item.multiple_label,
        "estimates": [
            {
                "label": estimate.label,
                "multiple": estimate.multiple,
                "price": estimate.price,
            }
            for estimate in item.estimates
        ],
        "fair_price": item.fair_price,
        "fair_difference": item.fair_difference,
        "fair_difference_percent": item.fair_difference_percent,
        "confidence": item.confidence,
        "notes": item.notes,
        "warning": item.warning,
    }


def _difference(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return round(value - baseline, 4)


def _percent_change(change: float | None, baseline: float | None) -> float | None:
    if change is None or baseline in (None, 0):
        return None
    return round((change / baseline) * 100, 4)


def _midpoint(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None:
        return None
    return round((bid + ask) / 2, 4)


def format_percent_text(value: float | None) -> str:
    if value is None:
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_number_text(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def format_money_text(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:,.0f} 元"


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
