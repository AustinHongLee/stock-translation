"""地雷風險矩陣（分析層純函數，可單元測試，不接 AI、不碰網路）。

用「精準片語字典」而非斷詞（Jieba）——台股重訊與新聞標題以固定片語為主，
精準片語字典比斷詞更穩、更可解釋。每則新聞命中風險片語 → 各風險維度加權分 →
總分 + 等級 + 命中詞。

紅線：只描述「出現了什麼風險字眼、屬哪個面向」這個事實，
**不預測股價、不給買賣建議**；分數只反映新聞用詞密度，不是風險的精算。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# 風險維度（法人籌碼先預留，待接三大法人資料；其餘為消息面）。
DIMENSIONS: tuple[str, ...] = (
    "法律監管",
    "財務誠信",
    "財務危機",
    "交易限制",
    "退場風險",
    "董監治理",
    "營運異常",
    "工程履約",
    "資產處分",
    "法人籌碼",
)

# 嚴重維度：只要出現此維度的高嚴重度詞，整體就拉到最高警戒。
CRITICAL_DIMENSIONS: frozenset[str] = frozenset({"退場風險", "財務危機"})

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


@dataclass(frozen=True, slots=True)
class RiskTerm:
    term: str
    dimension: str
    weight: int
    severity: str = SEVERITY_MEDIUM
    aliases: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()

    def phrases(self) -> tuple[str, ...]:
        return (self.term,) + self.aliases


# 風險片語字典。weight 1~5、severity 高/中/低。可自行增修。
RISK_TERMS: tuple[RiskTerm, ...] = (
    # ── 交易限制 ──
    RiskTerm("變更交易方法", "交易限制", 4, SEVERITY_HIGH, ("改列變更交易", "改列變更交易方法", "列為變更交易方法")),
    RiskTerm("分盤集合競價", "交易限制", 4, SEVERITY_HIGH, ("分盤交易", "加採分盤", "改分盤")),
    RiskTerm("全額交割", "交易限制", 3, SEVERITY_MEDIUM, ("改列全額交割", "全額交割股")),
    RiskTerm("暫停交易", "交易限制", 4, SEVERITY_HIGH, ("停止交易", "暫停買賣", "停止買賣")),
    RiskTerm("處置股", "交易限制", 2, SEVERITY_LOW, ("列處置", "處置措施", "監視處置")),
    RiskTerm("注意股", "交易限制", 1, SEVERITY_LOW, ("列注意", "注意交易資訊")),
    RiskTerm("重大訊息待公布", "交易限制", 2, SEVERITY_MEDIUM, ("召開重大訊息", "重大訊息記者會", "暫停交易發布重大訊息")),
    # ── 退場風險 ──
    RiskTerm("終止上市", "退場風險", 5, SEVERITY_HIGH, ("終止上櫃", "終止櫃檯買賣", "停止上市買賣", "下市定案")),
    RiskTerm("下市", "退場風險", 5, SEVERITY_HIGH, ("打入下市",)),
    RiskTerm("下櫃", "退場風險", 4, SEVERITY_HIGH),
    RiskTerm("淨值低於", "退場風險", 4, SEVERITY_HIGH, ("每股淨值低於", "淨值跌破", "股本二分之一", "股本十分之三")),
    # ── 財務危機 ──
    RiskTerm("淨值轉負", "財務危機", 5, SEVERITY_HIGH, ("淨值為負", "每股淨值轉負", "淨值翻負", "淨值已為負")),
    RiskTerm("跳票", "財務危機", 5, SEVERITY_HIGH, ("退票", "存款不足退票")),
    RiskTerm("違約交割", "財務危機", 5, SEVERITY_HIGH, ("交割違約",)),
    RiskTerm("繼續經營疑慮", "財務危機", 5, SEVERITY_HIGH, ("繼續經營能力", "重大不確定性", "繼續經營假設")),
    RiskTerm("無法表示意見", "財務危機", 5, SEVERITY_HIGH, ("拒絕簽證", "無法表示查核意見")),
    RiskTerm("保留意見", "財務危機", 4, SEVERITY_MEDIUM, ("會計師保留意見", "出具保留意見")),
    RiskTerm("鉅額虧損", "財務危機", 3, SEVERITY_MEDIUM, ("巨額虧損", "大幅虧損")),
    RiskTerm("累積虧損", "財務危機", 2, SEVERITY_LOW, ("累計虧損", "虧損累累")),
    RiskTerm("資金缺口", "財務危機", 3, SEVERITY_MEDIUM, ("資金壓力", "周轉不靈", "周轉困難", "資金吃緊")),
    RiskTerm("償債壓力", "財務危機", 3, SEVERITY_MEDIUM, ("債務違約", "無力償還", "債務壓力")),
    RiskTerm("存貨跌價損失", "財務危機", 2, SEVERITY_LOW, ("存貨跌價", "庫存跌價損失")),
    # ── 財務誠信 ──
    RiskTerm("財報不實", "財務誠信", 5, SEVERITY_HIGH, ("財務報表不實", "不實財報", "財報造假")),
    RiskTerm("假帳", "財務誠信", 5, SEVERITY_HIGH, ("做假帳", "美化帳目", "虛增營收", "虛灌營收")),
    RiskTerm("掏空", "財務誠信", 5, SEVERITY_HIGH, ("淘空", "掏空資產", "掏空公司")),
    RiskTerm("重編財報", "財務誠信", 4, SEVERITY_MEDIUM, ("財報重編", "更正財報")),
    RiskTerm("財報延遲", "財務誠信", 3, SEVERITY_MEDIUM, ("延後公告財報", "未如期公告財報", "未如期申報財報", "財報遲交")),
    RiskTerm("內控缺失", "財務誠信", 3, SEVERITY_MEDIUM, ("重大內控缺失", "內部控制缺失", "內控異常")),
    RiskTerm("更換會計師", "財務誠信", 3, SEVERITY_MEDIUM, ("更換簽證會計師", "改聘會計師", "改聘簽證")),
    RiskTerm("會計師請辭", "財務誠信", 4, SEVERITY_MEDIUM, ("簽證會計師請辭", "會計師辭任", "會計師拒絕簽證")),
    RiskTerm("財務長請辭", "財務誠信", 3, SEVERITY_MEDIUM, ("財務主管請辭", "會計主管異動", "財務長異動", "財務長離職")),
    # ── 法律監管 ──
    RiskTerm("遭調查", "法律監管", 3, SEVERITY_MEDIUM, ("配合調查", "接受調查", "展開調查", "介入調查")),
    RiskTerm("搜索", "法律監管", 4, SEVERITY_HIGH, ("搜索約談", "大舉搜索", "進駐搜索")),
    RiskTerm("約談", "法律監管", 3, SEVERITY_MEDIUM, ("約談到案", "請回約談")),
    RiskTerm("起訴", "法律監管", 4, SEVERITY_HIGH, ("提起公訴", "遭起訴", "起訴求刑")),
    RiskTerm("函送", "法律監管", 3, SEVERITY_MEDIUM, ("函送檢調", "移送檢調", "移送法辦")),
    RiskTerm("裁罰", "法律監管", 2, SEVERITY_LOW, ("開罰", "處分書", "罰鍰", "遭罰")),
    RiskTerm("違反證交法", "法律監管", 3, SEVERITY_MEDIUM, ("違反證券交易法",)),
    # ── 董監治理 ──
    RiskTerm("內線交易", "董監治理", 5, SEVERITY_HIGH, ("內線交易疑雲",)),
    RiskTerm("董事請辭", "董監治理", 3, SEVERITY_MEDIUM, ("董事長請辭", "董事辭任", "獨董請辭", "獨立董事辭任", "獨董集體請辭")),
    RiskTerm("申報轉讓", "董監治理", 2, SEVERITY_LOW, ("大量轉讓", "申讓持股", "鉅額轉讓", "申報持股轉讓")),
    RiskTerm("經營權之爭", "董監治理", 3, SEVERITY_MEDIUM, ("經營權爭奪", "委託書徵求大戰", "經營權大戰")),
    RiskTerm("代表人異動", "董監治理", 1, SEVERITY_LOW, ("法人代表異動",)),
    # ── 營運異常 ──
    RiskTerm("停工", "營運異常", 3, SEVERITY_MEDIUM, ("停產", "全面停工", "被迫停工")),
    RiskTerm("關廠", "營運異常", 3, SEVERITY_MEDIUM, ("收掉廠", "結束營業", "熄燈")),
    RiskTerm("火災", "營運異常", 3, SEVERITY_MEDIUM, ("大火", "廠房火警")),
    RiskTerm("爆炸", "營運異常", 4, SEVERITY_HIGH, ("氣爆", "工廠爆炸")),
    RiskTerm("工安意外", "營運異常", 3, SEVERITY_MEDIUM, ("工安事故", "公安意外", "職災")),
    RiskTerm("召回", "營運異常", 3, SEVERITY_MEDIUM, ("瑕疵召回", "產品回收")),
    RiskTerm("裁員", "營運異常", 2, SEVERITY_LOW, ("資遣", "大裁員", "人力精簡")),
    RiskTerm("無薪假", "營運異常", 3, SEVERITY_MEDIUM, ("放無薪假", "減班休息")),
    RiskTerm("資安事件", "營運異常", 3, SEVERITY_MEDIUM, ("資安攻擊", "勒索軟體", "駭客攻擊", "資料外洩", "個資外洩", "系統遭入侵")),
    RiskTerm("訂單取消", "營運異常", 3, SEVERITY_MEDIUM, ("取消訂單", "客戶取消訂單", "客戶延後拉貨", "交期遞延", "出貨遞延")),
    # ── 工程履約 ──
    RiskTerm("履約爭議", "工程履約", 3, SEVERITY_MEDIUM, ("履約糾紛", "履約保證金遭沒收")),
    RiskTerm("合意解約", "工程履約", 3, SEVERITY_MEDIUM, ("終止合約", "解除契約", "遭解約", "中止合約")),
    RiskTerm("工程延宕", "工程履約", 2, SEVERITY_LOW, ("工程遲延", "進度落後", "工期延宕")),
    RiskTerm("工程會調解", "工程履約", 2, SEVERITY_LOW, ("提付仲裁", "聲請調解")),
    RiskTerm("追加預算", "工程履約", 2, SEVERITY_LOW, ("追加工程款", "成本超支")),
    # ── 資產處分 ──
    RiskTerm("變賣資產", "資產處分", 3, SEVERITY_MEDIUM, ("賤賣資產", "急售資產")),
    RiskTerm("處分資產", "資產處分", 2, SEVERITY_LOW, ("資產處分", "出售資產", "活化資產")),
    RiskTerm("出售持股", "資產處分", 2, SEVERITY_LOW, ("處分持股", "出脫持股", "申讓子公司")),
    RiskTerm("售後租回", "資產處分", 2, SEVERITY_LOW, ("售後租回交易",)),
)

_TERM_INDEX: dict[str, RiskTerm] = {rt.term: rt for rt in RISK_TERMS}

# 等級門檻（單篇）。
_LEVELS = ("無", "低", "中", "高", "極高")
# 整體（payload）等級。
_SUMMARY_LEVELS = ("無", "留意", "注意", "警戒")


def _single_level(score: int, has_high: bool) -> str:
    if score <= 0:
        return "無"
    if score >= 16:
        return "極高"
    base = "低" if score < 5 else "中" if score < 10 else "高"
    if has_high and base in ("低", "中"):
        base = "高"
    return base


def score_news(title: str, *, terms: tuple[RiskTerm, ...] = RISK_TERMS) -> dict[str, object]:
    """單篇新聞風險評分。同一詞每篇最多算一次；跨維度命中有 bonus。固定輸入→固定輸出。"""
    text = str(title or "")
    matched: list[RiskTerm] = []
    seen: set[str] = set()
    for rt in terms:
        if rt.term in seen:
            continue
        if rt.excludes and any(x in text for x in rt.excludes):
            continue
        if any(phrase in text for phrase in rt.phrases()):
            matched.append(rt)
            seen.add(rt.term)

    dimensions: dict[str, int] = {}
    for rt in matched:
        dimensions[rt.dimension] = dimensions.get(rt.dimension, 0) + rt.weight

    base = sum(rt.weight for rt in matched)
    distinct_dims = len(dimensions)
    bonus = (distinct_dims - 1) * 2 if distinct_dims >= 2 else 0  # 多面向同篇命中加乘
    score = base + bonus
    has_high = any(rt.severity == SEVERITY_HIGH for rt in matched)

    return {
        "risk_score": score,
        "risk_level": _single_level(score, has_high),
        "dimensions": dimensions,
        "matched_terms": [rt.term for rt in matched],
    }


def _summary_level(total: int, item_levels: list[str], critical: bool) -> str:
    if total <= 0:
        return "無"
    if critical or "極高" in item_levels:
        return "警戒"
    base = "留意" if total < 10 else "注意" if total < 30 else "警戒"
    if "高" in item_levels and base == "留意":
        base = "注意"
    return base


def build_risk_summary(item_risks: list[dict[str, object]]) -> dict[str, object]:
    """彙整多篇 → 整體地雷雷達。reasons 用命中詞（固定安全片語），不含買賣/股價字眼。"""
    dim_totals: dict[str, int] = {}
    item_levels: list[str] = []
    matched_terms: list[str] = []
    total = 0
    critical = False
    for risk in item_risks:
        total += int(risk.get("risk_score") or 0)
        level = str(risk.get("risk_level") or "無")
        item_levels.append(level)
        for dim, value in (risk.get("dimensions") or {}).items():
            dim_totals[dim] = dim_totals.get(dim, 0) + int(value)
        for term in risk.get("matched_terms") or []:
            matched_terms.append(str(term))
            rt = _TERM_INDEX.get(str(term))
            if rt and rt.severity == SEVERITY_HIGH and rt.dimension in CRITICAL_DIMENSIONS:
                critical = True

    top_dimensions = [dim for dim, _ in sorted(dim_totals.items(), key=lambda kv: -kv[1])][:3]

    unique_terms = {}
    for term in matched_terms:
        rt = _TERM_INDEX.get(term)
        if rt and term not in unique_terms:
            unique_terms[term] = rt
    ordered = sorted(unique_terms.values(), key=lambda rt: -rt.weight)
    top_terms = [rt.term for rt in ordered][:6]

    reasons: list[str] = []
    if top_terms:
        reasons.append("近期新聞命中：" + "、".join(top_terms) + "。")

    return {
        "score": total,
        "level": _summary_level(total, item_levels, critical),
        "top_dimensions": top_dimensions,
        "reasons": reasons,
    }


def rolling_risk(dated_scores: list[tuple[date, int]], ref_date: date) -> dict[str, object]:
    """近 7 / 14 / 45 天風險分數與『風險升溫』旗標（簡版，不用 pandas/numpy）。"""
    windows: dict[str, object] = {}
    for label, days in (("d7", 7), ("d14", 14), ("d45", 45)):
        windows[label] = sum(
            score
            for day, score in dated_scores
            if day is not None and 0 <= (ref_date - day).days < days
        )
    d7 = int(windows["d7"])
    d45 = int(windows["d45"])
    expected_7 = (d45 / 45) * 7 if d45 else 0
    windows["heating"] = bool(d7 >= 6 and d7 > expected_7 * 1.5)
    return windows
