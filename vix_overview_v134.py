"""Read-only, source-dated VIX snapshot for the stock radar overview.

VIX is an implied 30-day annualized volatility measure inferred from S&P 500
options, NOT a guaranteed forecast, future index direction, or a trading signal.
We use Yahoo Finance daily snapshots for convenience; we DO NOT scrape Cboe
quote pages, which prohibit automated extraction. Missing/stale data stays missing.
"""
from __future__ import annotations

from datetime import datetime, date
from html import escape
from math import isfinite
from zoneinfo import ZoneInfo

SOURCE_LINK = "https://www.cboe.com/tradable_products/vix/vix_historical_data/"
REFERENCE_LINK = "https://finance.yahoo.com/quote/%5EVIX/history/"
SYMBOL = "^VIX"


def _finite_positive(value):
    try:
        n = float(value)
        return n if isfinite(n) and 0 < n < 1000 else None
    except (TypeError, ValueError):
        return None


def observation_from_frame(frame, asof=None):
    """Return a validated dated snapshot or None. No live-quote claim."""
    if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
        return None
    if asof is None:
        asof = datetime.now(ZoneInfo("Asia/Taipei"))
    limit = asof.date() if isinstance(asof, datetime) else asof
    observations = {}
    for timestamp, raw in frame["Close"].items():
        try:
            # Index timestamps are market-local dates; do not convert them to
            # Taiwan calendar days (that would shift overnight US sessions).
            raw_day = str(timestamp)[:10]
            day = date.fromisoformat(raw_day)
        except (ValueError, TypeError):
            continue
        val = _finite_positive(raw)
        if val is not None and day <= limit:
            observations[day] = val
    items = sorted(observations.items())
    if not items:
        return None
    day, level = items[-1]
    previous = items[-2][1] if len(items) >= 2 else None
    change = round(level - previous, 2) if previous is not None else None
    return {
        "date": day.isoformat(), "value": round(level, 2),
        "change_points": change,
        "age_days": (limit - day).days,
    }


def fetch_vix(asof=None):
    """Best effort; no source update can stop the main 100-stock scan."""
    try:
        import yfinance as yf
        frame = yf.Ticker(SYMBOL).history(period="10d", auto_adjust=False)
        return observation_from_frame(frame, asof=asof)
    except Exception as exc:
        print("VIX 資料暫缺：" + type(exc).__name__)
        return None


def render_vix_card(observation):
    """Compact mobile-friendly static HTML for one published scan snapshot."""
    valid = isinstance(observation, dict)
    if valid:
        try:
            level = _finite_positive(observation.get("value"))
            day = date.fromisoformat(str(observation.get("date", "")))
            age = int(observation.get("age_days", 999))
            change = observation.get("change_points")
            change = float(change) if change is not None else None
            if change is not None and not isfinite(change):
                change = None
            valid = level is not None and age >= 0 and day.year >= 2000
        except (ValueError, TypeError):
            valid = False
    else:
        valid = False
    if not valid:
        headline = '<strong class="vix134-value">—</strong>'
        stamp = "本次未取得可核對的 VIX 資料"
        change_text = "無法計算日變化"
    else:
        headline = '<strong class="vix134-value">' + f"{level:.2f}" + '</strong>'
        stamp = "美國市場日期：" + escape(day.isoformat())
        if age > 5:
            stamp += "（資料較舊，請勿當作最新行情）"
        change_text = (
            "較前次交易日 " + f"{change:+.2f}" + " 點"
            if change is not None else "前次交易日資料不足"
        )
    return (
        '<section id="vix-overview-v134" class="vix134" aria-label="VIX 波動指數觀察">'
        '<div class="vix134-top"><div><span class="vix134-kicker">美股市場溫度</span>'
        '<h2>🌡️ VIX 波動指數</h2></div><span class="vix134-notlive">非即時行情</span></div>'
        '<div class="vix134-main">' + headline + '<div><b>' + escape(change_text)
        + '</b><small>' + stamp + '</small></div></div>'
        '<p class="vix134-description">衡量 S&amp;P 500 選擇權市場對未來約 30 天'
        '年化波動的預期；數字越高代表預期波動通常越大，'
        '<b>不代表必然下跌</b>。此卡顯示最近一次掃描取得的日資料，'
        '不提供盤中即時報價，也不將 VIX 納入選股分數。</p>'
        '<p class="vix134-links">資料：Yahoo Finance ^VIX 歷史報價｜'
        '<a href="' + REFERENCE_LINK + '" target="_blank" rel="noopener noreferrer">'
        '查看報價日期</a> · '
        '<a href="' + SOURCE_LINK + '" target="_blank" rel="noopener noreferrer">'
        'Cboe 指數資料與說明</a></p>'
        '<style>'
        '#vix-overview-v134{border:1px solid #d7e2ed;border-radius:14px;'
        'background:white;padding:13px 16px;margin:12px 0;max-width:100%;}'
        '.vix134-top{display:flex;justify-content:space-between;align-items:start;'
        'gap:8px;flex-wrap:wrap}.vix134-kicker{font-size:.72rem;color:#63748a;'
        'font-weight:750}.vix134-top h2{font-size:1.08rem;margin:3px 0 7px;}'
        '.vix134-notlive{font-size:.72rem;background:#eef2f7;color:#4f6379;'
        'padding:5px 9px;border-radius:12px}.vix134-main{display:flex;'
        'align-items:center;gap:15px;flex-wrap:wrap;padding:5px 0 7px;}'
        '.vix134-value{font-size:2rem;color:#263f62;letter-spacing:-.03em;}'
        '.vix134-main b{display:block;font-size:.81rem;color:#3c5772;}'
        '.vix134-main small{display:block;margin-top:5px;color:#667992;'
        'overflow-wrap:anywhere;font-size:.76rem}.vix134-description,'
        '.vix134-links{line-height:1.6;margin:7px 0 0;font-size:.78rem;'
        'color:#66778a}.vix134-links a{color:#285e96;}'
        '</style></section>'
    )
