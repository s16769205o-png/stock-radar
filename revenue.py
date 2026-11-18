"""TWSE official listed-company monthly operating revenue (observation only).

The monthly snapshot endpoint supplies latest available company filing month,
not historical backfill. Data is retained for future observations. This module
never assigns 30-point fundamental scores or claims future returns.
"""
from __future__ import annotations
import csv
import html
import json
import statistics
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SOURCE = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
BACKUP = "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv"
ARCHIVE = Path(__file__).resolve().parent / "data" / "monthly_revenue.csv"
FIELDS = ["資料年月", "公司代號", "公司名稱", "月營收千元", "月增率", "年增率", "累計年增率", "資料來源"]


def _pct(value):
    if value is None:
        return None
    s = str(value).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "--", "N/A", "null", "不適用", "nan"):
        return None
    try:
        n = float(s)
        return n if abs(n) < 1e8 else None
    except (ValueError, TypeError):
        return None


def _month(value):
    """Convert ROC year-month (11510) into Gregorian ISO month (2026-10)."""
    s = str(value or "").strip().replace("/", "").replace("-", "")
    if not s.isdigit() or len(s) not in (4, 5, 6):
        return None
    yy, mm = int(s[:-2]), int(s[-2:])
    if not (1 <= mm <= 12):
        return None
    year = yy if yy >= 1900 else yy + 1911
    if not (2000 <= year <= datetime.now().year):
        return None
    return f"{year:04d}-{mm:02d}"


def _fetch_rows():
    """Try official JSON then official CSV; never fail the price scanner."""
    problems = []
    for url, format_ in ((SOURCE, "json"), (BACKUP, "csv")):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "StockRadarResearch/1.9 (public monthly revenue; contact via GitHub)",
                "Accept": "application/json,text/csv,*/*",
            })
            with urllib.request.urlopen(request, timeout=16) as response:
                payload = response.read(7_000_000)
            raw = payload.decode("utf-8-sig")
            if format_ == "json":
                rows = json.loads(raw)
            else:
                rows = list(csv.DictReader(raw.splitlines()))
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return rows, url, None
            problems.append(f"{format_} 格式不符")
        except Exception as exc:
            problems.append(f"{format_} {type(exc).__name__}")
    return [], "", "；".join(problems)


def _normalize(raw_rows, allowed, origin):
    best = {}
    for r in raw_rows:
        code = str(r.get("公司代號", "")).strip()
        period = _month(r.get("資料年月"))
        if code not in allowed or not period:
            continue
        yoy = _pct(r.get("營業收入-去年同月增減(%)"))
        mom = _pct(r.get("營業收入-上月比較增減(%)"))
        cumulative = _pct(r.get("累計營業收入-前期比較增減(%)"))
        revenue = _pct(r.get("營業收入-當月營收"))
        if all(x is None for x in (yoy, mom, cumulative, revenue)):
            continue
        best[(period, code)] = {
            "資料年月": period,
            "公司代號": code,
            "公司名稱": str(r.get("公司名稱", "")).strip(),
            "月營收千元": "" if revenue is None else revenue,
            "月增率": "" if mom is None else round(mom, 4),
            "年增率": "" if yoy is None else round(yoy, 4),
            "累計年增率": "" if cumulative is None else round(cumulative, 4),
            "資料來源": origin,
        }
    return best


def _merge_archive(new_rows):
    all_rows = {}
    if ARCHIVE.exists():
        with ARCHIVE.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("資料年月") and r.get("公司代號"):
                    all_rows[(r["資料年月"], r["公司代號"])] = {
                        key: r.get(key, "") for key in FIELDS
                    }
    all_rows.update(new_rows)
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for key in sorted(all_rows):
            writer.writerow(all_rows[key])
    return all_rows


def monthly_revenue_section(universe, industry, names):
    """HTML fragment. The stock radar must continue if the remote API is down."""
    tw_codes = {c.split(".")[0] for c in universe["台股"]}
    try:
        raw, origin, issue = _fetch_rows()
        new_rows = _normalize(raw, tw_codes, origin)
        stored = _merge_archive(new_rows)
        current = list(stored.values())
    except Exception as exc:
        # In particular, bad network data must never interrupt the 100-stock scan.
        issue = f"儲存或解析失敗：{type(exc).__name__}"
        current = []
    opening = '''<h2>📊 台股月營收研究室・第一期</h2>
    <p class="muted">來源：<a href="https://openapi.twse.com.tw/v1/opendata/t187ap05_L">臺灣證券交易所官方月營收</a>。
    採用公司申報的資料年月及月增／年增率；月營收不等於獲利，亦非產業前景30分。
    目前只涵蓋本雷達的台灣上市股票；美股基本面尚未接入。不同月份不混合比較。</p>'''
    if not current:
        return opening + '<p class="warning">官方營收暫時無法使用，既有股票雷達照常運作。</p>'
    latest = max(r["資料年月"] for r in current)
    eligible = {r["公司代號"]: r for r in current if r["資料年月"] == latest}
    by_sector = defaultdict(list)
    counts = defaultdict(int)
    for code in universe["台股"]:
        sector = industry[code]
        counts[sector] += 1
        stock = eligible.get(code.split(".")[0])
        if stock:
            by_sector[sector].append(stock)
    result = []
    for sector in counts:
        rows = by_sector[sector]
        yoy = [_pct(r["年增率"]) for r in rows]
        yoy = [v for v in yoy if v is not None]
        mom = [_pct(r["月增率"]) for r in rows]
        mom = [v for v in mom if v is not None]
        yoy_mid = statistics.median(yoy) if yoy else None
        mom_mid = statistics.median(mom) if mom else None
        positive = 100*sum(v>0 for v in yoy)/len(yoy) if yoy else None
        result.append((sector, len(rows), counts[sector], yoy_mid, mom_mid, positive, len(yoy)))
    result.sort(key=lambda v: (v[3] is None, -(v[3] or 0), v[0]))
    def fmt(val, suffix="%"):
        return "—" if val is None else f"{val:+.1f}{suffix}"
    lines = []
    for sector, covered, total, yoy, mom, positive, n in result:
        coverage = f"{covered}/{total}"
        note = "樣本少" if total < 3 else "營收資料不足" if n < total else "—"
        lines.append("<tr><td>"+html.escape(sector)+"</td><td>"+coverage+"</td>"
                     f"<td>{fmt(yoy)}</td><td>{fmt(mom)}</td>"
                     f"<td>{'—' if positive is None else f'{positive:.0f}%'}"
                     f"</td><td>{note}</td></tr>")
    has = len(eligible)
    alert = (f'<p class="warning">本次無法取得新資料：{html.escape(issue)}；使用已保存的最近營收月份。</p>' if issue else '')
    details = ''.join(
        f'<tr><td>{html.escape(names.get(code, code))}</td><td>{code}</td><td>{fmt(_pct(row["年增率"]))}</td>'
        f'<td>{fmt(_pct(row["月增率"]))}</td></tr>'
        for code, row in sorted(eligible.items(), key=lambda x: -(_pct(x[1]["年增率"]) if _pct(x[1]["年增率"]) is not None else -1e8))
    )
    return (opening + alert + f'<p class="muted">目前展示的營收資料月份：<b>{latest}</b>（不是網頁更新時間）。'
            f'本股票池同月份有 {has}/{len(tw_codes)} 檔可參考。族群數字採中位數，以避免單一巨型企業主導；金融股月營收與一般產業可比性有限。</p>'
            '<div class="table-wrap"><table><thead><tr><th>產業群</th><th>檔數</th><th>營收年增中位數</th><th>月增中位數</th><th>年增為正比率</th><th>提醒</th></tr></thead><tbody>'
            + ''.join(lines) + '</tbody></table></div>'
            '<details class="rest"><summary>查看上市個股月營收資料</summary><div class="table-wrap"><table><thead><tr><th>公司</th><th>代碼</th><th>營收年增</th><th>營收月增</th></tr></thead><tbody>'
            + details + '</tbody></table></div></details>'
            '<p class="muted">資料已存入 data/monthly_revenue.csv，讓後續月分得以比較。不同產業適用的成長指標不同，且月營收可能受季節性、併購或基期影響；不代表未來股票報酬。</p>')
