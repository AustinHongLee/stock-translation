from __future__ import annotations

from app.analyze.valuation import ValuationResult
from app.analyze.financial import calculate_financial_metrics, financial_tone, financial_title
from app.analyze.health import HealthMetrics, calculate_health_metrics
from app.analyze.suitability import ValuationSuitability
from app.models import DailyPrice, FinancialStatement, StockProfile

DISCLAIMER = "本內容只解讀已同步資料，不構成投資建議，也不預測股價。"


def build_rule_based_health_report(
    *,
    profile: StockProfile | None,
    prices: list[DailyPrice],
    financial_statement: FinancialStatement | None = None,
    suitability: ValuationSuitability | None = None,
    valuation: ValuationResult | None = None,
) -> dict[str, object]:
    metrics = calculate_health_metrics(prices)
    name = profile.short_name if profile else "這支股票"
    return {
        "engine": "rule_based",
        "title": f"{name} 白話健檢",
        "disclaimer": DISCLAIMER,
        "sections": [
            _trend_section(metrics),
            _price_position_section(metrics),
            _profitability_section(financial_statement),
            _volatility_section(metrics),
            _dividend_stability_section(suitability, valuation),
            _valuation_suitability_section(suitability, metrics),
        ],
    }


def _trend_section(metrics: HealthMetrics) -> dict[str, object]:
    trend = metrics.trend
    if trend.latest_close is None:
        return _section(
            "trend",
            "最近趨勢",
            "unknown",
            [
                "數字：本地還沒有足夠日線資料。",
                "白話：目前只能先說資料不足，暫時不解讀最近走勢。",
                "為什麼：趨勢至少需要前後幾段收盤價比較，單點價格沒有意義。",
                "要注意：先同步日線資料，再回來看短期與中期變化。",
            ],
        )

    tone = "neutral"
    label = "變化不大"
    if trend.change_20d_percent is not None:
        if trend.change_20d_percent >= 5:
            tone = "positive"
            label = "短期偏強"
        elif trend.change_20d_percent <= -5:
            tone = "caution"
            label = "短期偏弱"

    sentences = [
        (
            f"數字：最新收盤價是 {_money(trend.latest_close)}，"
            f"約 20 個交易日前是 {_money(trend.close_20d_ago)}，"
            f"變化 {_signed_percent(trend.change_20d_percent)}。"
        ),
        f"白話：最近趨勢屬於「{label}」。",
        "為什麼：這裡只比較過去一段時間的收盤價，描述的是已發生的價格方向。",
    ]
    if trend.change_60d_percent is not None:
        sentences.append(
            f"要注意：拉長到約 60 個交易日，收盤價變化是 {_signed_percent(trend.change_60d_percent)}；短期訊號不一定代表中期也一樣。"
        )
    else:
        sentences.append("要注意：目前中期資料還不足，短期變化先保守看。")
    return _section("trend", "最近趨勢", tone, sentences)


def _price_position_section(metrics: HealthMetrics) -> dict[str, object]:
    position = metrics.price_position
    if position.latest_close is None or position.position is None:
        return _section(
            "price_position",
            "價格位階",
            "unknown",
            [
                "數字：本地還沒有足夠價格區間資料。",
                "白話：目前不能說價格在近一年偏高或偏低。",
                "為什麼：位階需要最近一段期間的高低區間才能比較。",
                "要注意：缺資料時不要用單日價格替代區間判讀。",
            ],
        )

    percent = position.position * 100
    label = "中段"
    if position.position >= 0.75:
        label = "靠近近一年高位"
    elif position.position <= 0.25:
        label = "靠近近一年低位"

    return _section(
        "price_position",
        "價格位階",
        "neutral",
        [
            (
                f"數字：近一年價格區間大約是 {_money(position.low)} 到 {_money(position.high)}，"
                f"目前收盤在區間的 {_percent(percent)}。"
            ),
            f"白話：目前價格位置「{label}」。",
            "為什麼：位階只是在同一檔股票自己的近一年區間裡定位，不是公司價值判斷。",
            "要注意：低位可能來自基本面走弱，高位也可能來自獲利成長；要和營收、獲利、估值適用性一起看。",
        ],
    )


def _profitability_section(financial_statement: FinancialStatement | None) -> dict[str, object]:
    if financial_statement is None:
        return _section(
            "profitability",
            "獲利能力",
            "unknown",
            [
                "數字：目前還沒有同步 EPS、ROE 或 ROA 等基本面資料。",
                "白話：這一格先不判斷公司賺不賺錢。",
                "為什麼：股價資料只能說市場成交，不等於公司本業賺錢能力。",
                "要注意：缺基本面時，所有估值與體質解讀都要降權看。",
            ],
        )
    metrics = calculate_financial_metrics(financial_statement)
    return _section(
        "profitability",
        "獲利能力",
        financial_tone(metrics),
        [
            (
                f"數字：{metrics.quarter_label} EPS 是 {_money(metrics.eps)}，"
                f"淨利率約 {_percent(metrics.net_margin_percent)}，"
                f"可先解讀為「{financial_title(metrics)}」。"
            ),
            (
                f"白話：這家公司最近一季的獲利狀態可先看成「{financial_title(metrics)}」。"
            ),
            (
                f"為什麼：EPS 看每股賺多少，淨利率看每 100 元營收留下多少利潤，"
                f"單季 ROE 約 {_percent(metrics.roe_percent)}、ROA 約 {_percent(metrics.roa_percent)}。"
            ),
            "要注意：這不是全年數字，且單季可能受到匯率、業外或一次性因素影響。",
        ],
    )


def _volatility_section(metrics: HealthMetrics) -> dict[str, object]:
    volatility = metrics.volatility
    if volatility.daily_return_std_percent is None:
        return _section(
            "volatility",
            "波動風險",
            "unknown",
            [
                "數字：本地資料不足，暫時無法計算日波動。",
                "白話：目前不知道這檔平常震盪大不大。",
                "為什麼：波動要用連續交易日的漲跌幅估算。",
                "要注意：缺波動資料時，短線風險可能被看輕。",
            ],
        )

    tone = "positive"
    label = "相對平穩"
    if volatility.daily_return_std_percent >= 2:
        tone = "caution"
        label = "波動偏大"
    elif volatility.daily_return_std_percent >= 1:
        tone = "neutral"
        label = "中等波動"

    return _section(
        "volatility",
        "波動風險",
        tone,
        [
            (
                f"數字：用 {volatility.sample_days} 個交易日估算，"
                f"日報酬標準差約 {_percent(volatility.daily_return_std_percent)}。"
            ),
            f"白話：整體可先視為「{label}」。",
            (
                f"為什麼：日報酬標準差越高，代表平常價格跳動越大；"
                f"期間最大單日波動約 {_percent(volatility.max_daily_move_percent)}。"
            ),
            "要注意：波動不是好壞判斷，只是在提醒你價格可能上下跳得多快。",
        ],
    )


def _dividend_stability_section(
    suitability: ValuationSuitability | None,
    valuation: ValuationResult | None,
) -> dict[str, object]:
    if valuation is None:
        return _section(
            "dividend_stability",
            "股利穩定性",
            "unknown",
            [
                "數字：目前沒有股利彙整資料。",
                "白話：暫時不能判斷配息是否穩定。",
                "為什麼：股利穩定性需要看多個年度的現金股利紀錄。",
                "要注意：沒有股利資料時，不要用殖利率反推做主要參考。",
            ],
        )

    summary = valuation.dividend_summary
    years_count = len(summary.years)
    average_cash = summary.average_cash_dividend
    latest_cash = summary.latest_cash_dividend
    tone = _confidence_tone(suitability.data_confidence if suitability else valuation.confidence)
    if suitability and suitability.state == "not_applicable":
        tone = "caution"

    if years_count <= 0 or average_cash is None:
        return _section(
            "dividend_stability",
            "股利穩定性",
            "unknown",
            [
                "數字：目前沒有可年化的現金股利。",
                "白話：這檔不能靠股利資料解讀報酬來源。",
                "為什麼：配息資料不足或沒有連續年度，平均值會失真。",
                "要注意：先看營收、獲利與風險標籤，不要硬套股利情境。",
            ],
        )

    reasons = _reason_sentence(suitability.reasons if suitability else [])
    confidence_label = _confidence_label(suitability.data_confidence if suitability else valuation.confidence)
    return _section(
        "dividend_stability",
        "股利穩定性",
        tone,
        [
            (
                f"數字：目前有 {years_count} 個發放年度，"
                f"平均現金股利約 {_money(average_cash)}，最新一筆約 {_money(latest_cash)}。"
            ),
            f"白話：股利資料信心屬於「{confidence_label}」。",
            f"為什麼：系統看的是近年配息筆數、是否有缺口，以及配息是否忽高忽低。{reasons}",
            "要注意：股利是過去分配紀錄，不保證未來維持；股票股利與稅務也可能影響實際報酬。",
        ],
    )


def _valuation_suitability_section(
    suitability: ValuationSuitability | None,
    metrics: HealthMetrics,
) -> dict[str, object]:
    if suitability is None:
        return _section(
            "valuation_suitability",
            "估值適用性",
            "unknown",
            [
                "數字：目前沒有估值適用性判斷。",
                "白話：暫時不知道該用哪種方法看這家公司。",
                "為什麼：不同公司適合看的方法不同，不能只拿一個公式套所有股票。",
                "要注意：缺適用性判斷時，估值情境只當資料整理，不當結論。",
            ],
        )

    tone = {
        "applicable": "positive",
        "low_confidence": "neutral",
        "not_applicable": "caution",
    }.get(suitability.state, "unknown")
    primary = _method_name(suitability.recommended_primary)
    secondary = "、".join(_method_name(item) for item in suitability.recommended_secondary) or "暫無"
    avoid = "、".join(_method_name(item) for item in suitability.recommended_avoid) or "暫無"
    position_note = _position_cross_note(metrics, suitability)
    return _section(
        "valuation_suitability",
        "估值適用性",
        tone,
        [
            (
                f"數字：公司類型判斷為「{suitability.company_type_label}」，"
                f"股利法狀態是「{suitability.headline}」。"
            ),
            f"白話：主要先看「{primary}」，輔助看「{secondary}」。",
            f"為什麼：系統依照獲利穩定、配息穩定、產業特性與上市時間分流；目前不適合強看的方法是「{avoid}」。",
            f"要注意：{position_note}",
        ],
    )


def _section(
    section_id: str,
    title: str,
    tone: str,
    sentences: list[str],
) -> dict[str, object]:
    return {
        "id": section_id,
        "title": title,
        "tone": tone,
        "sentences": sentences,
    }


def _money(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _percent(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}%".replace(".00%", "%")


def _signed_percent(value: float | None) -> str:
    if value is None:
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{_percent(value)}"


def _confidence_tone(confidence: str | None) -> str:
    if confidence == "high":
        return "positive"
    if confidence == "low":
        return "caution"
    return "neutral"


def _confidence_label(confidence: str | None) -> str:
    return {
        "high": "較高",
        "medium": "中等",
        "low": "偏低",
    }.get(confidence or "", "待補")


def _reason_sentence(reasons: list[str]) -> str:
    if not reasons:
        return ""
    labels = {
        "yield_too_low": "殖利率太低",
        "loss_history": "近年曾虧損",
        "insufficient_data": "資料年數不足",
        "newly_listed": "上市時間短",
        "unstable_dividend": "配息不穩",
        "cyclical": "景氣循環特性",
        "growth_stock": "較像成長股",
        "low_yield": "殖利率偏低",
        "high_payout": "配息率偏高",
        "one_off_dividend": "可能有一次性股利",
        "short_history": "樣本年數較短",
        "etf": "ETF 不適用個股股利法",
    }
    text = "、".join(labels.get(item, item) for item in reasons[:4])
    return f"目前主要限制：{text}。"


def _method_name(method: str) -> str:
    return {
        "yield": "股利殖利率情境",
        "pe_band": "本益比敏感度",
        "pb_band": "本淨比敏感度",
        "revenue_momentum": "營收動能",
        "gross_margin_trend": "毛利率趨勢",
        "roe": "ROE",
        "distribution_yield_band": "配息殖利率區間",
        "premium_discount": "折溢價",
        "peer_pe_pb": "同業倍數比較",
        "pe_single": "單一本益比",
        "none": "暫不估價",
    }.get(method, method)


def _position_cross_note(metrics: HealthMetrics, suitability: ValuationSuitability) -> str:
    position = metrics.price_position.position
    if position is not None and position <= 0.25 and suitability.state != "applicable":
        return "價格位階偏低時，更要確認是不是基本面或資料限制造成，不能只看位置。"
    if position is not None and position >= 0.75 and suitability.company_type in {"growth", "cyclical"}:
        return "價格位階偏高時，要搭配獲利與營收確認市場期待是否有資料支撐。"
    if suitability.state == "not_applicable":
        return "這檔目前先看營收、獲利與風險標籤，估值數字要降權。"
    return "估值情境只是把假設攤開，仍需回到營收、獲利、股利與波動一起檢查。"
