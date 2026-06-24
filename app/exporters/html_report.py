from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from app.analyze.range_stats import compute_range_stats
from app.glossary.service import load_glossary
from app.news.classifier import contains_forbidden, sanitize_summary


REPORT_DISCLAIMER = "本報告只整理已同步資料與公開新聞關鍵字，不預測股價、不構成投資建議。"
SOURCE_NOTE = "資料來源：本機已同步資料；新聞為公開 RSS 關鍵字歸類。"
_GLOSSARY_TERMS = ("收盤價", "成交量", "本益比", "殖利率", "股價淨值比", "ROE", "VWAP")


def build_stock_report_html(
    payload: dict[str, Any],
    *,
    news_payload: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> str:
    generated = generated_at or datetime.now(timezone.utc)
    profile = payload.get("profile") or {}
    summary = payload.get("summary") or {}
    price_window = payload.get("price_window") or {}
    stock_id = _text(profile.get("stock_id") or _safe_stock_id(payload) or "")
    short_name = _text(profile.get("short_name") or profile.get("name") or stock_id or "個股")
    market = _text(profile.get("market") or "TWSE")
    data_date = _data_date(summary, price_window)
    title = f"{stock_id} {short_name} 個股研究報告".strip()

    body = "\n".join(
        [
            _hero(title, market, summary, data_date, generated),
            _assessment_section(payload.get("assessment"), payload.get("report"), data_date),
            _chips_section(payload.get("chips"), data_date),
            _valuation_section(payload.get("valuation"), data_date),
            _news_section(news_payload, data_date),
            _price_section(payload, data_date),
            _annotations_section(payload, data_date),
            _glossary_section(),
        ]
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-Hant">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{_escape(title)}</title>",
            f"  <style>{_stylesheet()}</style>",
            "</head>",
            "<body>",
            '  <main class="report-page">',
            body,
            "  </main>",
            "</body>",
            "</html>",
        ]
    )


def assert_report_has_no_forbidden(html: str) -> None:
    hits = contains_forbidden(html)
    if hits:
        raise ValueError("Report contains forbidden text: " + ", ".join(hits))


def _hero(
    title: str,
    market: str,
    summary: dict[str, Any],
    data_date: str,
    generated: datetime,
) -> str:
    latest = _fmt_number(summary.get("latest_close"))
    change = _fmt_signed(summary.get("change"))
    change_percent = _fmt_percent(summary.get("change_percent"))
    range_text = _join_nonempty(
        [
            f"最高 {_fmt_number(summary.get('highest') if summary.get('highest') is not None else summary.get('high'))}" if (summary.get("highest") is not None or summary.get("high") is not None) else "",
            f"最低 {_fmt_number(summary.get('lowest') if summary.get('lowest') is not None else summary.get('low'))}" if (summary.get("lowest") is not None or summary.get("low") is not None) else "",
            f"價格位階 {_fmt_position(summary.get('price_position'))}" if summary.get("price_position") is not None else "",
        ],
        " · ",
    )
    return f"""
    <header class="report-hero">
      <div>
        <p class="eyebrow">一鍵個股研究報告 · {_escape(market)}</p>
        <h1>{_escape(title)}</h1>
        <p class="meta">資料日 {_escape(data_date)} · 產生時間 {_escape(_fmt_datetime(generated))}</p>
      </div>
      <div class="hero-price">
        <span>最近收盤</span>
        <strong>{_escape(latest)}</strong>
        <em>{_escape(_join_nonempty([change, change_percent], " / ") or "--")}</em>
      </div>
      <p class="hero-note">{_escape(range_text or SOURCE_NOTE)}</p>
      <p class="disclaimer">{_escape(REPORT_DISCLAIMER)}</p>
    </header>
    """


def _assessment_section(assessment: Any, report: Any, data_date: str) -> str:
    if isinstance(assessment, dict) and assessment.get("summary"):
        title = _text(assessment.get("title") or "體質總評")
        summary = _text(assessment.get("summary"))
        counts = assessment.get("counts") or {}
        count_line = _join_nonempty(
            [
                f"偏多解讀 {counts.get('bull')}" if counts.get("bull") is not None else "",
                f"中性 {counts.get('neutral')}" if counts.get("neutral") is not None else "",
                f"偏空解讀 {counts.get('bear')}" if counts.get("bear") is not None else "",
            ],
            " · ",
        )
        factors = _factor_cards(assessment.get("factors"), limit=6)
        return _section(
            "體質總評",
            data_date,
            f"""
            <p class="lead">{_escape(title)}：{_escape(summary)}</p>
            <p class="muted">{_escape(count_line or "體質因子依已同步價量、籌碼、估值與基本面整理。")}</p>
            {factors}
            """,
        )

    sections = (report or {}).get("sections") if isinstance(report, dict) else []
    items = []
    for item in (sections or [])[:6]:
        if not isinstance(item, dict):
            continue
        items.append(
            f"""
            <article class="mini-card">
              <h3>{_escape(_text(item.get('title') or '項目'))}</h3>
              <p>{_escape(_text(item.get('summary') or item.get('hero') or '--'))}</p>
            </article>
            """
        )
    return _section(
        "體質總評",
        data_date,
        '<div class="card-grid">' + "\n".join(items or [_empty_card("目前沒有體質資料")]) + "</div>",
    )


def _factor_cards(factors: Any, *, limit: int) -> str:
    cards: list[str] = []
    for factor in list(factors or [])[:limit]:
        if not isinstance(factor, dict):
            continue
        cards.append(
            f"""
            <article class="mini-card">
              <h3>{_escape(_text(factor.get('label') or factor.get('key') or '因子'))}</h3>
              <p>{_escape(_text(factor.get('reading') or '--'))}</p>
              <span>{_escape(_text(factor.get('lean') or '中性'))}</span>
            </article>
            """
        )
    if not cards:
        cards.append(_empty_card("目前沒有體質因子"))
    return '<div class="card-grid">' + "\n".join(cards) + "</div>"


def _chips_section(chips: Any, data_date: str) -> str:
    payload = chips if isinstance(chips, dict) else {}
    as_of = _text(payload.get("as_of") or data_date)
    headline = _text(payload.get("headline") or "尚未同步三大法人買賣超資料。")
    level = _text(payload.get("level") or "無")
    reasons = [_text(item) for item in payload.get("reasons") or []]
    latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else {}
    rows = []
    for label, key in (("外資", "foreign_net"), ("投信", "trust_net"), ("自營商", "dealer_net"), ("合計", "total_net")):
        if key in latest:
            rows.append([label, _fmt_lots(latest.get(key))])
    table = _simple_table(["法人", "最新買賣超"], rows) if rows else ""
    return _section(
        "三大法人",
        as_of,
        f"""
        <p class="lead">籌碼燈號：{_escape(level)}。{_escape(headline)}</p>
        {_bullet_list(reasons)}
        {table}
        <p class="muted">{_escape(_text(payload.get('disclaimer') or '法人籌碼只呈現買賣超事實。'))}</p>
        """,
    )


def _valuation_section(valuation: Any, data_date: str) -> str:
    payload = valuation if isinstance(valuation, dict) else {}
    suitability = payload.get("suitability") if isinstance(payload.get("suitability"), dict) else {}
    relative = payload.get("relative") if isinstance(payload.get("relative"), dict) else {}
    bands = payload.get("bands") if isinstance(payload.get("bands"), dict) else {}
    rows = [
        ["適用狀態", _text(suitability.get("state_label") or "--")],
        ["資料信心", _text(suitability.get("data_confidence_label") or "--")],
        ["公司類型", _text(suitability.get("company_type_label") or "--")],
    ]
    recommended = suitability.get("recommended") if isinstance(suitability.get("recommended"), dict) else {}
    if recommended:
        rows.append(["主參考方法", _text(recommended.get("primary_label") or "--")])

    method_cards = []
    for method in relative.get("methods") or []:
        if not isinstance(method, dict):
            continue
        estimates = [
            f"{_text(item.get('label'))}: {_fmt_number(item.get('price'))}"
            for item in method.get("estimates") or []
            if isinstance(item, dict)
        ][:3]
        method_cards.append(
            f"""
            <article class="mini-card">
              <h3>{_escape(_text(method.get('title') or '敏感度'))}</h3>
              <p>{_escape(_text(method.get('warning') or relative.get('headline') or '情境數字只呈現假設差異。'))}</p>
              {_bullet_list(estimates)}
            </article>
            """
        )
    band_rows = _band_rows(bands)
    return _section(
        "估值情境",
        data_date,
        f"""
        {_simple_table(["項目", "內容"], rows)}
        <p class="muted">{_escape(_text(relative.get('headline') or '估值情境是 what-if，不是預測。'))}</p>
        <div class="card-grid">{''.join(method_cards or [_empty_card('目前沒有相對估值情境')])}</div>
        {_simple_table(["河流圖", "目前倍數", "歷史百分位", "樣本"], band_rows) if band_rows else ""}
        """,
    )


def _band_rows(bands: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for key, label in (("pe", "本益比"), ("pb", "股價淨值比")):
        item = bands.get(key)
        if not isinstance(item, dict):
            continue
        if item.get("available"):
            rows.append(
                [
                    label,
                    _fmt_number(item.get("current")),
                    _fmt_percent(item.get("current_percentile")),
                    str(item.get("sample_size") or "--"),
                ]
            )
        elif item.get("note"):
            rows.append([label, "--", _text(item.get("note")), str(item.get("sample_size") or "--")])
    return rows


def _news_section(news_payload: Any, data_date: str) -> str:
    payload = news_payload if isinstance(news_payload, dict) else {}
    news_date = _text(payload.get("generated_at") or data_date)[:10] or data_date
    overall = _text(payload.get("overall") or "目前沒有可整理的新聞資料。")
    risk = payload.get("risk_summary") if isinstance(payload.get("risk_summary"), dict) else {}
    risk_line = _join_nonempty(
        [
            f"風險分數 {risk.get('score')}" if risk.get("score") is not None else "",
            f"等級 {risk.get('level')}" if risk.get("level") else "",
            "近 7 天升溫" if risk.get("heating") else "",
        ],
        " · ",
    )
    rows = []
    for item in payload.get("items") or payload.get("top") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                _text(item.get("published") or "--"),
                _text(item.get("label") or "--"),
                _text(item.get("title") or "--"),
            ]
        )
        if len(rows) >= 5:
            break
    return _section(
        "消息 / 地雷雷達",
        news_date,
        f"""
        <p class="lead">{_escape(overall)}</p>
        <p class="muted">{_escape(risk_line or '新聞風險矩陣目前無明顯資料。')}</p>
        {_bullet_list([_text(item) for item in risk.get('reasons') or []][:4])}
        {_simple_table(["日期", "標籤", "標題"], rows) if rows else '<p class="empty">沒有新聞列可顯示。</p>'}
        <p class="muted">{_escape(_text(payload.get('disclaimer') or '消息整理為關鍵字歸類，僅供快速了解。'))}</p>
        """,
    )


def _price_section(payload: dict[str, Any], data_date: str) -> str:
    prices = list(payload.get("prices") or [])
    stats = compute_range_stats(prices, max(0, len(prices) - 60), max(0, len(prices) - 1)) if prices else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    rows = [
        ["最近收盤", _fmt_number(summary.get("latest_close"))],
        ["日漲跌", _join_nonempty([_fmt_signed(summary.get("change")), _fmt_percent(summary.get("change_percent"))], " / ") or "--"],
        ["價格位階", _fmt_position(summary.get("price_position"))],
        ["資料筆數", str(summary.get("rows") or len(prices) or "--")],
    ]
    if stats.get("available"):
        rows.extend(
            [
                ["區間", f"{_text(stats.get('start_date'))} 至 {_text(stats.get('end_date'))}"],
                ["區間交易日", str(stats.get("trading_days") or "--")],
                ["區間漲跌幅", _fmt_percent(stats.get("price_change_percent"))],
                ["區間高低振幅", _fmt_percent(stats.get("amplitude_percent"))],
                ["平均成交量", _fmt_shares(stats.get("average_volume"))],
                ["VWAP", _fmt_number(stats.get("vwap"))],
                ["年化波動度", _fmt_percent(stats.get("annualized_volatility_percent"))],
            ]
        )
    return _section(
        "價量摘要",
        data_date,
        f"""
        {_simple_table(["項目", "數字"], rows)}
        <p class="muted">區間統計預設整理最近 60 筆日線；只呈現歷史資料，不推論未來。</p>
        """,
    )


def _annotations_section(payload: dict[str, Any], data_date: str) -> str:
    annotations = [item for item in payload.get("annotations") or [] if isinstance(item, dict)]
    if not annotations:
        return ""
    rows = [
        [
            _annotation_kind_label(item.get("kind")),
            _annotation_anchor(item),
            _text(item.get("text")),
        ]
        for item in annotations[:80]
    ]
    return _section(
        "圖表標註",
        data_date,
        f"""
        {_simple_table(["類型", "位置", "文字"], rows)}
        <p class="muted">標註來自本機圖表工作區，作為複盤註記；不是系統產生的買賣建議。</p>
        """,
    )


def _glossary_section() -> str:
    entries = {entry.term: entry for entry in load_glossary()}
    cards = []
    for term in _GLOSSARY_TERMS:
        entry = entries.get(term)
        if entry is None:
            continue
        cards.append(
            f"""
            <article class="mini-card">
              <h3>{_escape(_text(entry.term))}</h3>
              <p>{_escape(_text(entry.plain))}</p>
              <span>{_escape(_text(entry.how_to_read))}</span>
            </article>
            """
        )
    return _section(
        "重點名詞教學",
        "固定教學資料",
        '<div class="card-grid">' + "\n".join(cards or [_empty_card("目前沒有名詞資料")]) + "</div>",
    )


def _section(title: str, data_date: str, content: str) -> str:
    return f"""
    <section class="report-section">
      <div class="section-head">
        <h2>{_escape(title)}</h2>
        <span>資料日 {_escape(data_date)}</span>
      </div>
      {content}
    </section>
    """


def _simple_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    header_html = "".join(f"<th>{_escape(_text(item))}</th>" for item in headers)
    row_html = []
    for row in rows:
        cells = "".join(f"<td>{_escape(_text(item))}</td>" for item in row)
        row_html.append(f"<tr>{cells}</tr>")
    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(row_html)}</tbody>
      </table>
    </div>
    """


def _bullet_list(items: list[str]) -> str:
    clean = [item for item in (_text(item) for item in items) if item]
    if not clean:
        return ""
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in clean) + "</ul>"


def _empty_card(text: str) -> str:
    return f'<article class="mini-card is-empty"><p>{_escape(_text(text))}</p></article>'


def _annotation_kind_label(value: Any) -> str:
    labels = {
        "note": "文字",
        "line": "線段",
        "arrow": "箭頭",
        "range": "區間",
        "gap": "缺口",
    }
    return labels.get(str(value or "note"), str(value or "文字"))


def _annotation_anchor(item: dict[str, Any]) -> str:
    start = _join_nonempty(
        [_text(item.get("anchor_date")), _fmt_number(item.get("anchor_price"))],
        " @ ",
    )
    end = _join_nonempty(
        [_text(item.get("anchor_date2")), _fmt_number(item.get("anchor_price2"))],
        " @ ",
    )
    return _join_nonempty([start, end], " -> ") or "--"


def _safe_stock_id(payload: dict[str, Any]) -> str:
    quote = payload.get("quote")
    if isinstance(quote, dict):
        return str(quote.get("stock_id") or "")
    return ""


def _data_date(summary: dict[str, Any], price_window: dict[str, Any]) -> str:
    return _text(summary.get("end_date") or price_window.get("actual_end") or price_window.get("requested_end") or "未標示")


def _text(value: Any) -> str:
    return sanitize_summary(str(value or "").strip())


def _escape(value: Any) -> str:
    return escape(_text(value), quote=True)


def _fmt_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _fmt_number(value: Any, *, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    if not _is_finite(number):
        return "--"
    if abs(number) >= 100:
        return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _fmt_signed(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not _is_finite(number):
        return ""
    return f"{number:+,.2f}".rstrip("0").rstrip(".")


def _fmt_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    if not _is_finite(number):
        return "--"
    return f"{number:+.1f}%" if number < 0 else f"{number:.1f}%"


def _fmt_position(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    if not _is_finite(number):
        return "--"
    percent = number * 100 if -1 <= number <= 1 else number
    return f"{percent:.0f}%"


def _fmt_lots(value: Any) -> str:
    try:
        shares = float(value)
    except (TypeError, ValueError):
        return "--"
    if not _is_finite(shares):
        return "--"
    return f"{shares / 1000:,.0f} 張"


def _fmt_shares(value: Any) -> str:
    try:
        shares = float(value)
    except (TypeError, ValueError):
        return "--"
    if not _is_finite(shares):
        return "--"
    return f"{shares:,.0f} 股"


def _join_nonempty(parts: list[str], separator: str) -> str:
    return separator.join(part for part in parts if part)


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def _stylesheet() -> str:
    return """
    :root {
      color-scheme: light;
      --ink: #132238;
      --muted: #637389;
      --line: #d8e2ea;
      --surface: #ffffff;
      --soft: #f5f8fb;
      --brand: #176b87;
      --brand-soft: #e6f3f7;
      --warn: #a56a13;
      font-family: "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; color: var(--ink); background: #edf3f7; }
    .report-page { max-width: 1080px; margin: 0 auto; padding: 32px 22px 48px; }
    .report-hero, .report-section {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 16px;
      box-shadow: 0 10px 24px rgba(19, 34, 56, .07);
    }
    .report-hero { display: grid; grid-template-columns: 1fr auto; gap: 16px 22px; }
    .eyebrow { margin: 0 0 6px; color: var(--brand); font-size: 12px; font-weight: 800; letter-spacing: .04em; }
    h1 { margin: 0; font-size: 30px; line-height: 1.2; }
    h2 { margin: 0; font-size: 20px; }
    h3 { margin: 0 0 8px; font-size: 15px; }
    p { margin: 0; line-height: 1.65; }
    .meta, .muted, .disclaimer { color: var(--muted); font-size: 12.5px; }
    .hero-price { min-width: 150px; text-align: right; }
    .hero-price span { display: block; color: var(--muted); font-size: 12px; }
    .hero-price strong { display: block; font-size: 34px; line-height: 1.1; font-variant-numeric: tabular-nums; }
    .hero-price em { color: var(--muted); font-style: normal; font-size: 13px; }
    .hero-note, .disclaimer { grid-column: 1 / -1; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .section-head span { flex: 0 0 auto; color: var(--muted); font-size: 12px; }
    .lead { font-size: 15px; font-weight: 700; margin-bottom: 8px; }
    .card-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
    .mini-card { border: 1px solid var(--line); background: var(--soft); border-radius: 8px; padding: 13px; }
    .mini-card p, .mini-card li { color: #26384d; font-size: 13px; }
    .mini-card span { display: block; margin-top: 7px; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .is-empty { border-style: dashed; }
    ul { margin: 10px 0 0; padding-left: 20px; }
    li { margin: 4px 0; line-height: 1.55; }
    .table-wrap { width: 100%; overflow-x: auto; margin-top: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--line); padding: 9px 10px; text-align: left; vertical-align: top; }
    th { color: var(--muted); background: var(--soft); font-size: 12px; }
    .empty { color: var(--muted); font-size: 13px; }
    @media print {
      body { background: #fff; }
      .report-page { max-width: none; padding: 0; }
      .report-hero, .report-section { box-shadow: none; break-inside: avoid; }
    }
    @media (max-width: 720px) {
      .report-page { padding: 14px; }
      .report-hero { grid-template-columns: 1fr; }
      .hero-price { text-align: left; }
      .section-head { align-items: flex-start; flex-direction: column; }
      .card-grid { grid-template-columns: 1fr; }
    }
    """
