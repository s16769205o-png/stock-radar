"""Conservative SEC XBRL 10-Q cross-check for the US fundamentals pilot.

Nothing claims to be SEC verified unless the matched facts are the same issuer,
the same quarterly start/end date, same filing accession, and filed <= scan date.
Only standalone quarters in 10-Q are accepted; 10-K/Q4 and YTD cannot pass.
SEC requests are opt-in and require a truthful identifying SEC_USER_AGENT;
in its absence the output says '未啟用', NEVER 'confirmed'.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import os
import re
import time
from urllib.request import Request, urlopen

PILOT = ("NVDA", "MSFT", "AAPL", "AMZN", "META", "COST", "LLY", "XOM")
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
NET_CONCEPT = "NetIncomeLoss"
TOLERANCE_PP = 0.25  # Rounded, descriptive percentages only; not an investment signal.


def _day(raw):
    try:
        return date.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None


def _facts_for_concept(obj, concept, asof):
    """Return valid *single-quarter* 10-Q USD facts only."""
    if not isinstance(obj, dict):
        return []
    values = (obj.get("facts", {}).get("us-gaap", {})
              .get(concept, {}).get("units", {}).get("USD", []))
    found = []
    cutoff = asof.date() if isinstance(asof, datetime) else asof
    for row in values:
        if not isinstance(row, dict) or row.get("form") != "10-Q":
            continue
        start, end, filed = (_day(row.get(k)) for k in ("start", "end", "filed"))
        accession = row.get("accn")
        value = row.get("val")
        if not all((start, end, filed)) or not isinstance(accession, str):
            continue
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            continue
        days = (end - start).days + 1
        if days < 65 or days > 112 or filed > cutoff or end > cutoff:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not (-1e16 < float(value) < 1e16):
            continue
        found.append({"start": start, "end": end, "filed": filed,
                      "accession": accession, "value": float(value)})
    return found


def _matched_quarters(obj, asof):
    profits = _facts_for_concept(obj, NET_CONCEPT, asof)
    results = []
    for tag in REVENUE_CONCEPTS:
        for rev in _facts_for_concept(obj, tag, asof):
            if rev["value"] <= 0:
                continue
            match = [
                p for p in profits
                if p["start"] == rev["start"] and p["end"] == rev["end"]
                and p["accession"] == rev["accession"]
                and p["filed"] == rev["filed"]
            ]
            for profit in match:
                results.append({**rev, "profit": profit["value"], "tag": tag})
    return results


def compare_sec_facts(symbol, yahoo_row, obj, asof):
    """Return an audit status, never silently replace Yahoo with another figure."""
    if not yahoo_row or not yahoo_row.get("quarter_end"):
        return {"state": "unverifiable", "reason": "Yahoo 季報缺資料"}
    current_end = _day(yahoo_row.get("quarter_end"))
    if current_end is None:
        return {"state": "unverifiable", "reason": "Yahoo 季度日期無效"}
    if obj.get("entityName") is None or not isinstance(obj.get("cik"), int):
        return {"state": "unverifiable", "reason": "SEC 公司身分資料不足"}
    quarters = _matched_quarters(obj, asof)
    current = [x for x in quarters if x["end"] == current_end]
    if not current:
        return {"state": "unverifiable", "reason": "SEC 缺同口徑單季 10-Q"}
    # Use only the most recently FILED matched facts for that exact period.
    chosen = max(current, key=lambda x: (x["filed"], x["accession"]))
    year_before = [
        x for x in quarters if x["tag"] == chosen["tag"]
        and x["end"].year == current_end.year - 1
        and abs((x["end"] - current_end.replace(year=current_end.year - 1)).days) <= 10
    ]
    if not year_before:
        return {"state": "unverifiable", "reason": "SEC 缺去年同季可比營收"}
    prior = max(year_before, key=lambda x: (x["filed"], x["accession"]))
    if yahoo_row.get("prior_end") != prior["end"].isoformat():
        return {"state": "unverifiable", "reason": "Yahoo 與 SEC 去年季度日期不符"}
    if yahoo_row.get("revenue_yoy") is None or yahoo_row.get("margin") is None:
        return {"state": "unverifiable", "reason": "Yahoo 缺比較指標"}
    try:
        yahoo_yoy, yahoo_margin = float(yahoo_row["revenue_yoy"]), float(yahoo_row["margin"])
        if not all((-1e6 < v < 1e6) for v in (yahoo_yoy, yahoo_margin)):
            raise ValueError("nonfinite")
    except (TypeError, ValueError):
        return {"state": "unverifiable", "reason": "Yahoo 指標無效"}
    sec_yoy = (chosen["value"] / prior["value"] - 1) * 100
    sec_margin = chosen["profit"] / chosen["value"] * 100
    same = (abs(sec_yoy - yahoo_yoy) <= TOLERANCE_PP
            and abs(sec_margin - yahoo_margin) <= TOLERANCE_PP)
    return {
        "state": "matched" if same else "different",
        "reason": "SEC 數據一致" if same else "SEC 與整理資料不同",
        "quarter_end": current_end.isoformat(),
        "filing_date": chosen["filed"].isoformat(),
        "accession": chosen["accession"],
        "cik": obj["cik"],
    }


def _download_json(url, user_agent):
    request = Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    })
    with urlopen(request, timeout=12) as response:
        data = response.read(12_000_001)
    if len(data) > 12_000_000:
        raise ValueError("SEC JSON 超過大小限制")
    return json.loads(data)


def audit_pilot(rows, asof):
    """Opt-in read-only SEC check; no identifying header => no HTTP requests."""
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent or len(user_agent) < 10 or "@" not in user_agent:
        return {s: {"state": "disabled", "reason": "SEC 核對未啟用"}
                for s in PILOT}
    data = {r["symbol"]: r for r in rows or []
            if isinstance(r, dict) and r.get("symbol") in PILOT}
    result = {}
    try:
        raw = _download_json(TICKERS_URL, user_agent)
        ticker_map = {
            str(x["ticker"]): int(x["cik_str"])
            for x in raw.values()
            if isinstance(x, dict) and "ticker" in x and "cik_str" in x
        }
    except Exception as exc:
        print("SEC 核對暫缺：" + type(exc).__name__)
        return {s: {"state": "unverifiable", "reason": "SEC 公司清單不可用"}
                for s in PILOT}
    for symbol in PILOT:
        cik = ticker_map.get(symbol)
        if cik is None:
            result[symbol] = {"state": "unverifiable", "reason": "SEC 無相符股票代碼"}
            continue
        try:
            # Intentionally below SEC 10 requests/sec limit; no retries or caching
            # with fabricated publication times.
            time.sleep(0.55)
            obj = _download_json(FACTS_URL.format(cik), user_agent)
            if obj.get("cik") != cik:
                raise ValueError("CIK 身分不符")
            result[symbol] = compare_sec_facts(symbol, data.get(symbol), obj, asof)
        except Exception as exc:
            print("SEC " + symbol + " 暫缺：" + type(exc).__name__)
            result[symbol] = {"state": "unverifiable", "reason": "SEC 原始資料暫不可用"}
    return result
