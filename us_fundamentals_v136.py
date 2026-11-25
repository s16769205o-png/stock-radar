"""1.36 US quarterly-fundamentals pilot, descriptive only (not an SEC filing).

Eight US-stock snapshots from yfinance's published quarterly income statements.
No filling historical blanks, no P/E/forecast, no hindsight backtest, no score.
Never use a stock price as a substitute for financial statements. The snapshot
is transient and NOT point-in-time evidence for past trading decisions.
"""
from __future__ import annotations

from datetime import datetime, date
from html import escape
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import pandas as pd

PILOT = ("NVDA", "MSFT", "AAPL", "AMZN", "META", "COST", "LLY", "XOM")
MAX_AGE_DAYS = 220
SEC_SEARCH = "https://www.sec.gov/edgar/search/"


def _valid(value):
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _date(value):
    try:
        d = pd.Timestamp(value)
        return d.date()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_statement(ticker, frame, asof):
    """Compare one fiscal quarter only with its own year-earlier fiscal quarter.

    Use reported 'Total Revenue' and 'Net Income' line items exactly.
    Some issuers label these differently; then state 'unavailable' rather
    than combine incomparable accounting concepts. Never backfill Q4 from FY.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    if "Total Revenue" not in frame.index or "Net Income" not in frame.index:
        return None
    today = (asof.date() if isinstance(asof, datetime) else asof)
    items = []
    for col in frame.columns:
        day = _date(col)
        if day is None or day > today:
            continue
        try:
            revenue = _valid(frame.at["Total Revenue", col])
            profit = _valid(frame.at["Net Income", col])
        except (KeyError, TypeError, ValueError):
            continue
        if revenue is not None and revenue > 0 and profit is not None:
            items.append((day, revenue, profit))
    if not items:
        return None
    items.sort(reverse=True)
    day, revenue, profit = items[0]
    age = (today - day).days
    # Quarter end is NOT filing date. Do not imply financials were public then.
    target_year = day.year - 1
    older = [
        (d, rev) for d, rev, _ in items[1:]
        if d.year == target_year and abs((d.month - day.month) * 30 + d.day - day.day) <= 15
    ]
    prior = max(older, default=None, key=lambda row: row[0])
    yoy = round((revenue / prior[1] - 1) * 100, 1) if prior and prior[1] > 0 else None
    return {
        "symbol": ticker,
        "quarter_end": day.isoformat(),
        "prior_end": prior[0].isoformat() if prior else None,
        "revenue_yoy": yoy,
        "margin": round(profit / revenue * 100, 1),
        "age_days": age,
    }


def fetch_pilot(asof=None):
    """Best-effort low-volume pilot; each missing line stays missing."""
    if asof is None:
        asof = datetime.now(ZoneInfo("Asia/Taipei"))
    import yfinance as yf
    result = []
    for symbol in PILOT:
        try:
            statement = yf.Ticker(symbol).get_income_stmt(freq="quarterly")
            parsed = parse_statement(symbol, statement, asof)
        except Exception as exc:
            print("美股季度財報暫缺：" + symbol + " " + type(exc).__name__)
            parsed = None
        result.append(parsed if parsed else {"symbol": symbol, "quarter_end": None})
    return result


def _pct(number):
    v = _valid(number)
    return "—" if v is None else f"{v:+.1f}%"


def _link(symbol):
    # Symbols come from PILOT rather than uncontrolled user input.
    return "https://finance.yahoo.com/quote/" + symbol + "/financials/"


def render_pilot(rows):
    by_symbol = {
        row["symbol"]: row for row in rows or []
        if isinstance(row, dict) and row.get("symbol") in PILOT
    }
    available = sum(
        1 for symbol in PILOT if by_symbol.get(symbol, {}).get("quarter_end")
    )
    cards = []
    for symbol in PILOT:
        row = by_symbol.get(symbol, {})
        date_text = row.get("quarter_end")
        try:
            date.fromisoformat(str(date_text))
            valid = True
        except (ValueError, TypeError):
            valid = False
        if valid:
            age = row.get("age_days")
            age = int(age) if isinstance(age, (int, float)) and isfinite(age) else 999
            stale = "（較舊，請核對公告）" if age > MAX_AGE_DAYS else ""
            quarter = "會計季度截止：" + escape(str(date_text)) + stale
            growth = _pct(row.get("revenue_yoy"))
            margin = _pct(row.get("margin"))
        else:
            quarter = "本次季度財報缺漏"
            growth, margin = "—", "—"
        cards.append(
            '<article class="uf136-company"><div class="uf136-top"><strong>' +
            escape(symbol) + '</strong><span>' + quarter + '</span></div>'
            '<dl><div><dt>單季營收年增</dt><dd>' + growth + '</dd></div>'
            '<div><dt>單季淨利率</dt><dd>' + margin + '</dd></div></dl>'
            '<a href="' + _link(symbol) + '" target="_blank" '
            'rel="noopener noreferrer">查閱 Yahoo 財報資料</a></article>'
        )
    return (
        '<section id="us-fundamentals-v136" class="uf136" aria-label="美股季度財報試驗觀察">'
        '<details><summary>📘 美股季度財報研究・8 檔樣本'
        '<span class="uf136-count">有資料 ' + str(available) + '/8</span></summary>'
        '<p class="uf136-info">選定 8 檔跨科技、消費、醫療、能源的觀察樣本，'
        '僅顯示可取得的<b>單季營收年增率</b>和<b>單季淨利率</b>。'
        '不是全美股排名、產業景氣指數或 100 分打分表。</p>'
        '<div class="uf136-grid">' + "".join(cards) + '</div>'
        '<p class="uf136-info"><b>口徑與限制：</b>'
        '單季營收年增須有同公司、上年相近季度的可比資料；'
        '沒有就顯示「—」。淨利率＝同季淨利÷同季營收。'
        '不同企業、財年及會計口徑不保證可比，尤其不能把淨利率'
        '當作股價報酬或投資勝率。這些數字由 Yahoo Finance 的'
        '季度財報整理資料提供，<b>未逐筆核對 SEC 原始申報</b>。'
        '「季度截止日」不是公開發布日，因此不可拿目前整理的資料'
        '假裝當時投資人已經知道，也不能直接用於歷史回測。</p>'
        '<p class="uf136-info">核對官方申報：'
        '<a href="' + SEC_SEARCH + '" target="_blank" '
        'rel="noopener noreferrer">SEC EDGAR 查詢</a>。'
        '任何一檔若資料不足或來源連線失敗，會保留缺漏，不編造數字。</p>'
        '</details></section>'
    )


CSS = """
/* stock-radar-us-fundamentals-v136 */
#us-fundamentals-v136{background:#fff;border:1px solid #dbe5f0;
 border-radius:14px;padding:12px 13px;max-width:100%;margin:12px 0 17px}
#us-fundamentals-v136 summary{cursor:pointer;color:#244465;font-weight:750;
 font-size:.98rem;line-height:1.7}
#us-fundamentals-v136 .uf136-count{font-size:.72rem;float:right;font-weight:500;
 background:#eaf1f8;border-radius:12px;padding:3px 8px;color:#536a81}
#us-fundamentals-v136 .uf136-info{color:#536b80;line-height:1.7;
 font-size:.77rem;margin:11px 0}
#us-fundamentals-v136 .uf136-grid{display:grid;gap:9px;
 grid-template-columns:repeat(2,minmax(0,1fr));margin:12px 0}
#us-fundamentals-v136 .uf136-company{padding:11px;min-width:0;
 border:1px solid #e0e7ee;border-radius:12px}
#us-fundamentals-v136 .uf136-top{display:flex;flex-wrap:wrap;
 gap:5px;justify-content:space-between}
#us-fundamentals-v136 .uf136-top strong{color:#233d61;font-size:.93rem}
#us-fundamentals-v136 .uf136-top span{font-size:.68rem;color:#637991}
#us-fundamentals-v136 dl{margin:9px 0}
#us-fundamentals-v136 dl>div{display:flex;justify-content:space-between;
 flex-wrap:wrap;gap:6px;margin-top:7px;font-size:.75rem}
#us-fundamentals-v136 dt{color:#52677b}
#us-fundamentals-v136 dd{font-weight:750;margin:0;font-variant-numeric:tabular-nums}
#us-fundamentals-v136 a{font-size:.72rem}
@media(max-width:510px){#us-fundamentals-v136 .uf136-grid{grid-template-columns:1fr}}
"""


def install_us_fundamentals(path: Path, rows):
    """Mount inside the pre-existing US tab after the hours guide."""
    path = Path(path)
    page = path.read_text(encoding="utf-8")
    if "/* stock-radar-us-fundamentals-v136 */" in page:
        return
    if page.count("</head>") != 1 or page.count("</body>") != 1:
        raise ValueError("美股季度財報研究：HTML 結構不完整")
    if "/* us-hours-v135 */" not in page:
        raise ValueError("美股季度財報研究：缺少美股時段入口")
    safe = json.dumps(render_pilot(rows), ensure_ascii=False)
    safe = safe.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    script = (
        "/* stock-radar-us-fundamentals-v136 */"
        "(function(){const p=document.getElementById('panel-us');"
        "if(!p||document.getElementById('us-fundamentals-v136'))return;"
        "const t=document.createElement('div');t.innerHTML=" + safe + ";"
        "const s=t.firstElementChild;const h=p.querySelector('#us-hours-v135');"
        "if(h)h.after(s);else p.insertBefore(s,p.firstChild);})();"
    )
    page = page.replace("</head>", "<style>" + CSS + "</style></head>", 1)
    page = page.replace("</body>", "<script>" + script + "</script></body>", 1)
    path.write_text(page, encoding="utf-8")
