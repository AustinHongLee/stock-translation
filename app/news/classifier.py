"""規則式新聞傾向分類（純函數，可單元測試，不接 AI、不碰網路）。

延續《09》支柱一「消息面 AI 歸類」與《15》工作流 D「先不接 LLM」的紀律：
此模組只用關鍵字把一則新聞標題標為『利多 / 利空 / 中性』並附理由，
**不預測股價、不下買賣建議**。所有對外輸出的整體摘要會經過 guardrail 過濾。

關鍵字庫採「可調設定檔」：優先讀 data/news_keywords.json（使用者覆蓋）→ 再讀套件內
app/news/keywords.json → 都讀不到才用本檔內建 fallback。weight 2 = 強訊號、1 = 一般。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

LABEL_POSITIVE = "利多"
LABEL_NEGATIVE = "利空"
LABEL_NEUTRAL = "中性"

# guardrail：對外『整體摘要』與『理由』絕不可出現的字眼（買賣/目標價/漲跌預測）。
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "建議買", "建議賣", "該買", "該賣", "買進", "賣出", "加碼", "減碼操作",
    "目標價", "會漲", "會跌", "將漲", "將跌", "抄底", "逢低", "放空", "進場", "出場",
    "便宜價", "合理價", "昂貴價", "低估", "高估",
)

# 內建 fallback（精簡版；完整且可調的字庫在 keywords.json）。
_EMBEDDED_POSITIVE: dict[str, int] = {
    "漲停": 2, "創新高": 2, "大漲": 2, "轉虧為盈": 2, "轉盈": 2, "接獲大單": 2, "庫藏股": 2,
    "成長": 1, "回升": 1, "好轉": 1, "受惠": 1, "看好": 1, "樂觀": 1, "擴產": 1, "量產": 1,
    "訂單": 1, "旺季": 1, "亮眼": 1, "優於預期": 1, "上修": 1, "調升": 1, "得標": 1, "配息": 1,
    "高殖利率": 1, "填息": 1, "外資買超": 1, "法人買超": 1,
}
_EMBEDDED_NEGATIVE: dict[str, int] = {
    "跌停": 2, "崩跌": 2, "重挫": 2, "大跌": 2, "創新低": 2, "虧損": 2, "由盈轉虧": 2,
    "認列損失": 2, "掏空": 2, "下市": 2, "終止上市": 2, "全額交割": 2, "變更交易方法": 2,
    "暫停交易": 2, "分盤集合競價": 2, "淨值轉負": 2, "淨值為負": 2, "淨值低於": 2,
    "重大財務挑戰": 2, "跳票": 2, "砍單": 2,
    "衰退": 1, "下滑": 1, "下修": 1, "調降": 1, "降評": 1, "看壞": 1, "保守": 1, "庫存": 1,
    "減產": 1, "裁員": 1, "罰款": 1, "訴訟": 1, "示警": 1, "警示": 1, "減資": 1, "現金增資": 1,
    "外資賣超": 1, "法人賣超": 1, "不如預期": 1, "逆風": 1,
}

# 事件類型關鍵字（中性歸類「公司在幹嘛」，不判斷好壞、不預測）。可自行增修。
EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "重大訊息": ("重大訊息", "重訊", "重大訊息待公布", "重大訊息記者會", "暫停交易發布重大訊息"),
    "交易限制": (
        "變更交易方法", "分盤集合競價", "分盤交易", "加採分盤", "全額交割", "停止交易", "暫停交易",
        "停止買賣", "注意股", "列注意", "處置股", "監視處置", "暫停融資", "暫停融券",
    ),
    "退場風險": (
        "下市", "下櫃", "終止上市", "終止上櫃", "終止櫃檯買賣", "退場", "停止上市買賣",
        "淨值為負", "淨值轉負", "淨值低於", "股本十分之三", "股本二分之一",
    ),
    "財務危機": (
        "淨值為負", "淨值轉負", "淨值低於", "每股淨值", "重大財務挑戰", "資金缺口", "現金流",
        "債務壓力", "償債", "跳票", "違約交割", "會計師無法表示意見", "無法表示意見",
        "繼續經營疑慮", "鉅額虧損", "累積虧損", "認列損失", "認列虧損",
    ),
    "資產處分": (
        "處分資產", "資產處分", "出售資產", "出售持股", "處分持股", "賣股", "出售", "變賣",
        "活化資產", "售後租回",
    ),
    "併購": ("併購", "收購", "合併", "入主", "公開收購", "參股", "策略投資", "整併"),
    "轉型": ("轉型", "跨足", "切入", "新事業", "新布局", "轉骨", "多角化", "進軍"),
    "擴產": ("擴產", "擴廠", "建廠", "新廠", "新產能", "投資設廠", "加碼投資", "擴大投資"),
    "買回": ("庫藏股", "買回", "實施庫藏"),
    "增減資": ("現金增資", "增資", "減資", "私募", "可轉債", "募資"),
    "法說財測": ("法說", "法說會", "財測", "展望", "營運說明", "業績發表"),
    "訴訟裁罰": ("訴訟", "求償", "開罰", "裁罰", "違約", "起訴", "遭調查", "搜索"),
    "人事": ("董事長", "總經理", "執行長", "請辭", "接任", "人事異動", "改選董事"),
    "董監治理": ("董事辭任", "法人董事", "代表人異動", "持股轉讓", "申報轉讓", "內線交易", "掏空"),
    "合作訂單": ("合作", "簽約", "結盟", "得標", "大單", "訂單", "供應鏈", "認證通過"),
    "股利": ("配息", "股利", "除息", "填息", "現金股利", "配股"),
    "工程履約": (
        "工程延宕", "工程款", "追加預算", "工程會調解", "調解", "合意解約", "履約爭議",
        "承攬", "標案", "停工", "趕工", "驗收", "交付延遲",
    ),
    "營運異常": ("停工", "停產", "關廠", "裁員", "資遣", "無薪假", "召回", "工安意外", "火災", "爆炸"),
    "政策法規": ("政策", "法規", "補助", "關稅", "制裁", "禁令", "許可", "環評", "主管機關", "證交所", "櫃買中心"),
    "供需價格": ("報價", "漲價", "降價", "殺價", "價格戰", "供過於求", "供不應求", "庫存", "缺貨"),
}


def detect_events(title: str) -> list[str]:
    """偵測新聞屬於哪些『公司動向/大事件』類型；可同時命中多類。"""
    text = str(title or "")
    return [event for event, keywords in EVENT_KEYWORDS.items() if any(kw in text for kw in keywords)]


def _load_keyword_file(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    positive = {str(k): int(v) for k, v in (data.get("positive") or {}).items() if not str(k).startswith("_")}
    negative = {str(k): int(v) for k, v in (data.get("negative") or {}).items() if not str(k).startswith("_")}
    if not positive or not negative:
        raise ValueError("keyword lexicon is empty")
    return positive, negative


def load_lexicon(path: str | Path | None = None) -> tuple[dict[str, int], dict[str, int]]:
    """載入加權關鍵字庫；任何失敗都退回內建 fallback，不丟例外。"""
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    try:  # 使用者可在 data/news_keywords.json 覆蓋（與其他設定檔一致）
        from app.runtime_paths import data_path

        candidates.append(data_path("news_keywords.json"))
    except Exception:  # noqa: BLE001
        pass
    candidates.append(Path(__file__).with_name("keywords.json"))
    for candidate in candidates:
        try:
            if candidate and Path(candidate).is_file():
                return _load_keyword_file(candidate)
        except Exception:  # noqa: BLE001 - 壞檔就試下一個
            continue
    return dict(_EMBEDDED_POSITIVE), dict(_EMBEDDED_NEGATIVE)


POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS = load_lexicon()


@dataclass(frozen=True, slots=True)
class HeadlineVerdict:
    label: str
    score: int
    matched_positive: list[str] = field(default_factory=list)
    matched_negative: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.label == LABEL_POSITIVE:
            return "出現偏正面字眼：" + "、".join(self.matched_positive)
        if self.label == LABEL_NEGATIVE:
            return "出現偏負面字眼：" + "、".join(self.matched_negative)
        if self.matched_positive or self.matched_negative:
            return "正反字眼互見，傾向不明確"
        return "未偵測到明顯利多或利空字眼"


def _dedupe_overlaps(keywords: list[str]) -> list[str]:
    """移除被更長關鍵字包含的短關鍵字，避免重複計分（如「創新高」不再加計「新高」）。"""
    return [
        kw
        for kw in keywords
        if not any(other != kw and kw in other for other in keywords)
    ]


def _match(text: str, lexicon: dict[str, int]) -> tuple[list[str], int]:
    matched = _dedupe_overlaps([kw for kw in lexicon if kw in text])
    weight = sum(int(lexicon.get(kw, 1)) for kw in matched)
    return matched, weight


def classify_headline(
    title: str,
    *,
    positive: dict[str, int] | None = None,
    negative: dict[str, int] | None = None,
) -> HeadlineVerdict:
    """把單一新聞標題標為利多/利空/中性（加權），固定輸入→固定輸出。"""
    text = str(title or "")
    pos_lex = positive if positive is not None else POSITIVE_KEYWORDS
    neg_lex = negative if negative is not None else NEGATIVE_KEYWORDS
    matched_pos, pos_weight = _match(text, pos_lex)
    matched_neg, neg_weight = _match(text, neg_lex)
    score = pos_weight - neg_weight
    if score > 0:
        label = LABEL_POSITIVE
    elif score < 0:
        label = LABEL_NEGATIVE
    else:
        label = LABEL_NEUTRAL
    return HeadlineVerdict(
        label=label,
        score=score,
        matched_positive=matched_pos,
        matched_negative=matched_neg,
    )


def contains_forbidden(text: str) -> list[str]:
    """回傳命中的禁止字眼（用於測試與防線驗證）。"""
    source = str(text or "")
    return [phrase for phrase in FORBIDDEN_PHRASES if phrase in source]


def sanitize_summary(text: str) -> str:
    """最後一道防線：把對外整體摘要裡的禁止字眼遮成中性字，避免越線。"""
    safe = str(text or "")
    for phrase in FORBIDDEN_PHRASES:
        safe = safe.replace(phrase, "（已略）")
    return safe


def build_overall_sentence(
    *,
    positive: int,
    negative: int,
    neutral: int,
    days: int,
) -> str:
    """從各傾向則數產生白話整體摘要（中性、不預測、附免責）。"""
    total = positive + negative + neutral
    if total == 0:
        return f"近 {days} 天沒有抓到相關新聞，無法整理消息面。"

    if positive > negative and positive >= max(1, total * 0.4):
        tilt = "偏正面消息較多"
    elif negative > positive and negative >= max(1, total * 0.4):
        tilt = "偏負面消息較多"
    else:
        tilt = "消息正反互見、沒有一面倒"

    sentence = (
        f"近 {days} 天共 {total} 則新聞，"
        f"其中 {positive} 則偏利多、{negative} 則偏利空、{neutral} 則中性，{tilt}。"
        "這是用關鍵字做的粗略歸類，僅供快速了解消息面，非投資建議，也不預測股價。"
    )
    return sanitize_summary(sentence)
