"""法人賣壓 proxy（純函數，可單元測試，不碰網路）。

⚠️ 資料串接待辦（本檔目前只有「算法」，還沒有資料來源）：
    - TWSE 三大法人買賣超日報（上市）：每日外資/投信/自營商買賣超股數。
    - TPEx 三大法人買賣明細（上櫃）。
    串好後，把每日 (外資, 投信, 自營商) 淨買賣超股數與當日成交量餵進下列函式即可。

紅線（《09》R11 精神）：只用公開資料的 proxy 描述「法人在買還是在賣」這個事實，
**不臆測「敏感型投控／高風險投控」等標籤、不預測股價、不給買賣建議**。
正值代表淨賣超（賣壓），負值代表淨買超。
"""
from __future__ import annotations

# 各法人別的中性說明（描述性，不臆測公司屬性）。
PROXY_NOTES: dict[str, str] = {
    "foreign": "外資：常被視為外部/快錢資金，連續賣超是資金撤退的訊號之一。",
    "trust": "投信：本土法人，偏中長線；連續賣超代表本土法人轉趨保守。",
    "dealer": "自營商：以短線/避險為主，單日波動大，單看參考性較低。",
    "all_three": "三大法人同步賣超：代表盤面資金共識偏保守。",
}


def selling_pressure(net_sell_shares: float | None, volume: float | None) -> float | None:
    """單一法人別賣壓比 = 淨賣超股數 / 當日成交量（量化『賣得多兇』）。

    net_sell_shares 正值＝淨賣超；負值（淨買超）回 0（沒有賣壓）。量缺漏回 None。
    """
    if not volume or volume <= 0 or net_sell_shares is None:
        return None
    return max(0.0, float(net_sell_shares)) / float(volume)


def total_institutional_pressure(
    foreign_net_sell: float | None,
    trust_net_sell: float | None,
    dealer_net_sell: float | None,
    volume: float | None,
) -> float | None:
    """三大法人合計賣壓 = (外資+投信+自營商 淨賣超，只算賣方) / 當日成交量。"""
    if not volume or volume <= 0:
        return None
    total = sum(max(0.0, float(x or 0)) for x in (foreign_net_sell, trust_net_sell, dealer_net_sell))
    return total / float(volume)


def consecutive_sell_days(net_sell_recent_first: list[float]) -> int:
    """從最近一天往回數，連續『淨賣超』的天數。輸入以最近日在前排序。"""
    days = 0
    for value in net_sell_recent_first:
        if (value or 0) > 0:
            days += 1
        else:
            break
    return days


def pressure_accelerating(net_sell_recent_first: list[float]) -> bool | None:
    """賣壓加速：近 3 天平均賣超 > 近 20 天平均賣超。資料不足 20 天回 None。"""
    series = net_sell_recent_first
    if len(series) < 20:
        return None
    recent3 = sum(max(0.0, float(x or 0)) for x in series[:3]) / 3
    recent20 = sum(max(0.0, float(x or 0)) for x in series[:20]) / 20
    return recent3 > recent20


_CHIPS_DISCLAIMER = "法人籌碼只呈現三大法人近期買賣超的事實，不預測股價、不構成買賣建議。"


def _lots(shares: float) -> int:
    """股數換算成『張』（1 張 = 1000 股），四捨五入。"""
    return int(round(float(shares) / 1000.0))


def _chips_level(consec_total, consec_foreign, all_three_sell, sum_total, latest_total):
    reasons: list[str] = []
    if consec_total >= 2:
        reasons.append(f"三大法人連續 {consec_total} 天站在賣方。")
    if consec_foreign >= 2:
        reasons.append(f"外資連續 {consec_foreign} 天賣超。")
    if all_three_sell:
        reasons.append("最新一日外資、投信、自營商同步賣超。")
    if sum_total < 0:
        reasons.append(f"近期合計淨賣超 {_lots(abs(sum_total))} 張。")
    elif sum_total > 0:
        reasons.append(f"近期合計淨買超 {_lots(sum_total)} 張。")

    if consec_total >= 5 or consec_foreign >= 6:
        level = "警戒"
    elif consec_total >= 3 or consec_foreign >= 4 or all_three_sell:
        level = "注意"
    elif latest_total < 0:
        level = "留意"
    else:
        level = "無"
    if level == "無" and not reasons:
        reasons.append("近期三大法人偏買方或中性，暫無明顯籌碼賣壓。")
    return level, reasons


def _chips_headline(latest_total, consec_total, consec_foreign, sum_total, window_days):
    if latest_total < 0:
        latest_phrase = f"最新一日三大法人合計淨賣超 {_lots(abs(latest_total))} 張"
    elif latest_total > 0:
        latest_phrase = f"最新一日三大法人合計淨買超 {_lots(latest_total)} 張"
    else:
        latest_phrase = "最新一日三大法人合計買賣超持平"
    tail = ""
    if consec_total >= 3:
        tail = f"，且已連續 {consec_total} 天偏賣方"
    elif consec_foreign >= 3:
        tail = f"，外資連續 {consec_foreign} 天賣超"
    window_word = "淨賣超" if sum_total < 0 else ("淨買超" if sum_total > 0 else "持平")
    return f"{latest_phrase}{tail}；近 {window_days} 日合計{window_word}。"


_CHIPS_ANALYSIS_NOTE = (
    "以上為依買賣超數字的中性解讀；法人也可能因避險、調節、換股而進出，不代表股價方向。"
)


def _chips_analysis(recent_first, consec_total, consec_foreign, sum_total):
    """把買賣超數字翻成幾條『可能的解讀』（中性、不預測股價、不給買賣建議）。"""
    if not recent_first:
        return []
    latest = recent_first[0]
    f, t, d = int(latest.foreign_net), int(latest.trust_net), int(latest.dealer_net)
    out: list[str] = []

    # 1) 方向一致或分歧
    if f < 0 and t < 0 and d < 0:
        out.append("外資、投信、自營商同步站在賣方，三大法人近期看法一致、籌碼面壓力較集中。")
    elif f > 0 and t > 0 and d >= 0:
        out.append("外資與投信同步買超，本土與外資法人近期同步偏積極。")
    elif f < 0 and t > 0:
        out.append("外資賣超、投信買超：外資與本土法人看法分歧，籌碼沒有一面倒，要留意誰的力道大。")
    elif f > 0 and t < 0:
        out.append("外資買超、投信賣超：外資與本土法人看法分歧，要留意誰的力道大。")
    else:
        out.append("三大法人方向不一致，籌碼面訊號較不明確。")

    # 2) 主導者
    mags = {"外資": (abs(f), f), "投信": (abs(t), t), "自營商": (abs(d), d)}
    dom = max(mags, key=lambda k: mags[k][0])
    if mags[dom][0] > 0:
        side = "買超" if mags[dom][1] > 0 else "賣超"
        out.append(f"今日買賣超主要由{dom}主導（{side} {_lots(mags[dom][0])} 張），另兩者影響相對小。")

    # 3) 賣壓是否加速
    total_rf = [int(x.total_net) for x in recent_first]
    acc = pressure_accelerating([-x for x in total_rf])
    if consec_total >= 1 and acc is True:
        out.append("近 3 日賣超較近 20 日平均放大，賣壓有加速跡象，值得多留意。")
    elif consec_total >= 2 and acc is False:
        out.append("雖然連續賣超，但近 3 日賣超沒有明顯大於近 20 日平均，壓力暫時沒有加速。")

    # 4) 整體
    if consec_total >= 3:
        out.append(f"已連續 {consec_total} 天賣超，籌碼面短線偏保守；建議搭配上方 K 線與消息面一起看。")
    elif sum_total > 0:
        out.append("近 20 日三大法人合計仍是買超，籌碼面暫時偏穩。")
    return out


def build_institutional_summary(trades) -> dict:
    """把三大法人近 N 日買賣超整理成 UI／地雷雷達『籌碼面』摘要。

    輸入 trades 由舊到新（chronological）。固定輸入→固定輸出，純函數、可單元測試。
    所有對外字串只描述買賣超事實，不預測股價、不給買賣建議。
    """
    items = [t for t in (trades or []) if t is not None]
    if not items:
        return {
            "available": False,
            "level": "無",
            "headline": "尚未同步三大法人買賣超資料；按『同步』後即可顯示近 20 日法人籌碼。",
            "reasons": [],
            "trend": [],
            "proxy_notes": dict(PROXY_NOTES),
            "disclaimer": _CHIPS_DISCLAIMER,
        }

    recent_first = list(reversed(items))
    latest = recent_first[0]
    total_rf = [int(t.total_net) for t in recent_first]
    foreign_rf = [int(t.foreign_net) for t in recent_first]

    consec_total = consecutive_sell_days([-x for x in total_rf])
    consec_foreign = consecutive_sell_days([-x for x in foreign_rf])

    window = recent_first[:20]
    sum_total = sum(int(t.total_net) for t in window)
    sum_foreign = sum(int(t.foreign_net) for t in window)
    sum_trust = sum(int(t.trust_net) for t in window)
    sum_dealer = sum(int(t.dealer_net) for t in window)
    all_three_sell = (
        int(latest.foreign_net) < 0
        and int(latest.trust_net) < 0
        and int(latest.dealer_net) < 0
    )

    level, reasons = _chips_level(
        consec_total, consec_foreign, all_three_sell, sum_total, int(latest.total_net)
    )
    headline = _chips_headline(
        int(latest.total_net), consec_total, consec_foreign, sum_total, len(window)
    )
    trend = [
        {"date": t.date.isoformat(), "value": int(t.total_net)} for t in items[-20:]
    ]

    return {
        "available": True,
        "as_of": latest.date.isoformat(),
        "days": len(items),
        "level": level,
        "latest": {
            "foreign_net": int(latest.foreign_net),
            "trust_net": int(latest.trust_net),
            "dealer_net": int(latest.dealer_net),
            "total_net": int(latest.total_net),
        },
        "consecutive_total_sell_days": consec_total,
        "consecutive_foreign_sell_days": consec_foreign,
        "all_three_sell": all_three_sell,
        "sum_20": {
            "foreign_net": sum_foreign,
            "trust_net": sum_trust,
            "dealer_net": sum_dealer,
            "total_net": sum_total,
            "days": len(window),
        },
        "trend": trend,
        "headline": headline,
        "reasons": reasons,
        "analysis": _chips_analysis(recent_first, consec_total, consec_foreign, sum_total),
        "analysis_note": _CHIPS_ANALYSIS_NOTE,
        "proxy_notes": dict(PROXY_NOTES),
        "disclaimer": _CHIPS_DISCLAIMER,
    }
