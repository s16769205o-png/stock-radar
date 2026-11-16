"""小G股票雷達 1.3：台美各 50 檔，均線與量價觀察。研究用途，不下單。"""
from __future__ import annotations

import csv
import html
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "history.csv"
SITE_FILE = ROOT / "index.html"
VOLUME_THRESHOLD = 1.5
# 固定的跨產業「測試」名單，不是完整市場成分股，也非投資建議。
UNIVERSE = {
    "台股": [
        "2330.TW", "2454.TW", "2317.TW", "2308.TW", "2382.TW", "2303.TW", "2327.TW", "2357.TW", "2376.TW", "2377.TW",
        "2408.TW", "2409.TW", "2412.TW", "3008.TW", "3017.TW", "3034.TW", "3231.TW", "3443.TW", "3532.TW", "3661.TW",
        "3711.TW", "4938.TW", "4958.TW", "5269.TW", "1301.TW", "1303.TW", "1326.TW", "2002.TW", "1101.TW", "1102.TW",
        "1216.TW", "2207.TW", "2603.TW", "2609.TW", "2615.TW", "2610.TW", "2618.TW", "2634.TW", "1476.TW", "1519.TW",
        "1590.TW", "2881.TW", "2882.TW", "2884.TW", "2885.TW", "2886.TW", "2891.TW", "2892.TW", "5871.TW", "5880.TW",
    ],
    "美股": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "AMD", "ORCL", "CRM",
        "ADBE", "PLTR", "MU", "INTC", "AMAT", "LRCX", "KLAC", "QCOM", "TXN", "ADI",
        "PANW", "CRWD", "NOW", "ANET", "UBER", "TSLA", "GM", "CAT", "DE", "GE",
        "GEV", "BA", "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "JPM", "BAC",
        "GS", "V", "MA", "COST", "WMT", "KO", "PG", "XOM", "CVX", "NEE",
    ],
}
TW_NAMES = {
    '2330': '台積電',
    '2454': '聯發科',
    '2317': '鴻海',
    '2308': '台達電',
    '2382': '廣達',
    '2303': '聯電',
    '2327': '國巨',
    '2357': '華碩',
    '2376': '技嘉',
    '2377': '微星',
    '2408': '南亞科',
    '2409': '友達',
    '2412': '中華電',
    '3008': '大立光',
    '3017': '奇鋐',
    '3034': '聯詠',
    '3231': '緯創',
    '3443': '創意',
    '3532': '台勝科',
    '3661': '世芯-KY',
    '3711': '日月光投控',
    '4938': '和碩',
    '4958': '臻鼎-KY',
    '5269': '祥碩',
    '1301': '台塑',
    '1303': '南亞',
    '1326': '台化',
    '2002': '中鋼',
    '1101': '台泥',
    '1102': '亞泥',
    '1216': '統一',
    '2207': '和泰車',
    '2603': '長榮',
    '2609': '陽明',
    '2615': '萬海',
    '2610': '華航',
    '2618': '長榮航',
    '2634': '漢翔',
    '1476': '儒鴻',
    '1519': '華城',
    '1590': '亞德客-KY',
    '2881': '富邦金',
    '2882': '國泰金',
    '2884': '玉山金',
    '2885': '元大金',
    '2886': '兆豐金',
    '2891': '中信金',
    '2892': '第一金',
    '5871': '中租-KY',
    '5880': '合庫金',
}

FIELDS = ["交易日期", "市場", "股票", "調整收盤價", "MA20", "MA60", "成交量", "量比", "單日漲跌幅", "量價訊號", "符合趨勢", "中文名稱", "RSI14", "五日動能", "均線分數", "量價分數", "動能分數", "技術分數"]
MIN_SUCCESS = 70  # 大量資料異常時不覆蓋既有報告。
BATCH_SIZE = 10


def classify_volume_price(ratio: float | None, daily_change: float) -> str:
    if ratio is None:
        return "量能資料不足"
    if ratio >= VOLUME_THRESHOLD:
        return "放量上漲" if daily_change > 0 else "放量下跌" if daily_change < 0 else "放量持平"
    return "一般量能・上漲" if daily_change > 0 else "一般量能・下跌" if daily_change < 0 else "一般量能・持平"



def rsi_14(closes: pd.Series) -> float:
    """Wilder-style 14 day RSI using historical closing prices only."""
    delta = closes.diff()
    up = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    average_up = up.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1]
    average_down = down.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1]
    if average_down == 0:
        return 100.0 if average_up > 0 else 50.0
    rs = average_up / average_down
    return float(100.0 - 100.0 / (1.0 + rs))


def technique_points(price: float, ma20: float, ma60: float,
                     ratio: float | None, change: float,
                     rsi: float, momentum5: float) -> tuple[int, int, int]:
    """Transparent initial experimental heuristic: 12 trend + 10 volume + 8 momentum."""
    if price > ma20 > ma60:
        trend = 12
    elif price > ma20 and price > ma60:
        trend = 8
    elif price > ma20 or price > ma60:
        trend = 4
    else:
        trend = 0

    if ratio is not None and ratio >= VOLUME_THRESHOLD:
        volume = 10 if change > 0 else 0 if change < 0 else 3
    else:
        volume = 5 if change > 0 else 2 if change < 0 else 3

    strength = 5 if 50 <= rsi <= 70 else 3 if 40 <= rsi < 50 or 70 < rsi <= 80 else 1
    momentum = strength + (3 if momentum5 > 0 else 0)
    return trend, volume, momentum


def calculate(data: pd.DataFrame, market: str, code: str) -> dict:
    if data is None or data.empty or not {"Close", "Volume"}.issubset(data.columns):
        raise ValueError("缺少收盤價或成交量")
    data = data.dropna(subset=["Close", "Volume"])
    if len(data) < 61:
        raise ValueError("交易日資料不足 61 筆")
    closes = data["Close"].astype(float)
    volumes = data["Volume"].astype(float)
    price = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    ma20, ma60 = float(closes.iloc[-20:].mean()), float(closes.iloc[-60:].mean())
    # 先前完整的 20 個交易日，不將訊號日放進平均值裡。
    avg_prev_vol = float(volumes.iloc[-21:-1].mean())
    last_vol = int(volumes.iloc[-1])
    ratio = last_vol / avg_prev_vol if avg_prev_vol > 0 else None
    change = 100 * (price / prev_close - 1) if prev_close > 0 else 0.0
    rsi = rsi_14(closes)
    momentum5 = 100 * (price / float(closes.iloc[-6]) - 1) if closes.iloc[-6] > 0 else 0.0
    trend_points, volume_points, momentum_points = technique_points(price, ma20, ma60, ratio, change, rsi, momentum5)
    return {
        "交易日期": data.index[-1].strftime("%Y-%m-%d"), "市場": market, "股票": code,
        "調整收盤價": round(price, 2), "MA20": round(ma20, 2), "MA60": round(ma60, 2),
        "成交量": last_vol, "量比": round(ratio, 2) if ratio is not None else "",
        "單日漲跌幅": round(change, 2), "量價訊號": classify_volume_price(ratio, change),
        "符合趨勢": "是" if price > ma20 > ma60 else "否",
        "中文名稱": TW_NAMES.get(code.split(".")[0], "") if market == "台股" else "",
        "RSI14": round(rsi, 1), "五日動能": round(momentum5, 2),
        "均線分數": trend_points, "量價分數": volume_points,
        "動能分數": momentum_points, "技術分數": trend_points + volume_points + momentum_points,
    }


def get_bulk(codes: list[str]) -> pd.DataFrame:
    return yf.download(tickers=codes, period="6mo", interval="1d", group_by="ticker",
                       auto_adjust=True, progress=False, threads=True, timeout=25)


def frame_for(bulk: pd.DataFrame, code: str) -> pd.DataFrame:
    if isinstance(bulk.columns, pd.MultiIndex):
        if code in bulk.columns.get_level_values(0):
            return bulk[code].copy()
        if code in bulk.columns.get_level_values(1):
            return bulk.xs(code, axis=1, level=1).copy()
        raise ValueError("批次資料缺少此股票")
    raise ValueError("批次回傳欄位格式無法辨識")


def latest_snapshot() -> tuple[list[dict], list[str]]:
    records, errors = [], []
    for market, all_codes in UNIVERSE.items():
        for start in range(0, len(all_codes), BATCH_SIZE):
            chunk = all_codes[start:start + BATCH_SIZE]
            try:
                bulk = get_bulk(chunk)
            except Exception as exc:
                bulk = pd.DataFrame()
                print("批次資料問題：", type(exc).__name__, str(exc)[:100])
            for code in chunk:
                try:
                    try:
                        frame = frame_for(bulk, code)
                        record = calculate(frame, market, code)
                    except (ValueError, KeyError, TypeError):
                        # 單檔補抓，避免某檔批次漏資料導致整批失效。
                        frame = yf.Ticker(code).history(period="6mo", auto_adjust=True)
                        record = calculate(frame, market, code)
                    records.append(record)
                    print(f'{code} {record["交易日期"]}：{record["量價訊號"]}，趨勢{record["符合趨勢"]}')
                except Exception as exc:
                    errors.append(f"{code}: {type(exc).__name__}: {str(exc)[:90]}")
            time.sleep(0.4)
    return records, errors


def persist(records: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[tuple[str, str], dict] = {}
    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("交易日期") and row.get("股票"):
                    merged[(row["交易日期"], row["股票"])] = {field: row.get(field, "") for field in FIELDS}
    for row in records:
        merged[(row["交易日期"], row["股票"])] = row
    with DATA_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow(merged[key])



def stock_card(row: dict, position: int) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    selected = row["符合趨勢"] == "是"
    vol = row["量比"]
    label = f"{float(vol):.2f} 倍" if vol != "" else "無資料"
    day_change = f'{float(row["單日漲跌幅"]):+.2f}%'
    name = str(row.get("中文名稱", "")).strip() or row["股票"]
    code = row["股票"]
    score = int(row["技術分數"])
    return f'''<article class="card">
<div class="heading"><div><span class="ranking">#{position}</span> <strong>{esc(name)}</strong><small>{esc(code)} · {esc(row['市場'])} · {esc(row['交易日期'])}</small></div><span class="tag {'green' if selected else ''}">{'符合均線趨勢' if selected else '未符合均線趨勢'}</span></div>
<div class="scoreline"><b>{score} / 30 分</b><small>技術評分（試驗中）</small></div>
<div class="price">{float(row['調整收盤價']):,.2f} <small>{'TWD' if row['市場']=='台股' else 'USD'}</small></div>
<div class="metrics"><div><small>MA20</small><b>{float(row['MA20']):,.2f}</b></div><div><small>MA60</small><b>{float(row['MA60']):,.2f}</b></div><div><small>量比（前20交易日）</small><b>{label}</b></div><div><small>當日漲跌</small><b>{day_change}</b></div><div><small>RSI14</small><b>{float(row['RSI14']):.1f}</b></div><div><small>5日動能</small><b>{float(row['五日動能']):+.2f}%</b></div></div>
<p class="signal">量價訊號：<strong>{esc(row['量價訊號'])}</strong></p>
<p class="breakdown">均線 {row['均線分數']}/12 · 量價 {row['量價分數']}/10 · 動能 {row['動能分數']}/8</p></article>'''


def rank(row: dict) -> tuple:
    """Within each market, sort by TECHNICAL points only, never claim 100-point total."""
    return (-int(row["技術分數"]), row["符合趨勢"] != "是", -float(row["量比"] or 0), row["股票"])


def render(records: list[dict], errors: list[str]) -> None:
    updated = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    tw = sorted((r for r in records if r["市場"] == "台股"), key=rank)
    us = sorted((r for r in records if r["市場"] == "美股"), key=rank)
    trend_count = sum(r["符合趨勢"] == "是" for r in records)
    volume_count = sum(str(r["量價訊號"]).startswith("放量") for r in records)
    warning = f'<p class="alert">有 {len(errors)} 檔無法更新，請到 GitHub Actions 查閱日誌。</p>' if errors else ''

    def section(rows: list[dict], name: str, flag: str) -> str:
        first10, remainder = rows[:10], rows[10:]
        head = "".join(stock_card(r, i) for i, r in enumerate(first10, 1))
        extra = "".join(stock_card(r, i) for i, r in enumerate(remainder, 11))
        note = '<p class="muted">按技術分數由高至低排列，只是研究優先順序，不表示未來報酬排名。</p>'
        return (f'<h2>{flag} {name}（{len(rows)} 檔）</h2>'
                f'{note}<h3>技術觀察前 {len(first10)} 名</h3><section class="grid">{head}</section>'
                f'<details><summary>展開其餘 {len(remainder)} 檔股票（第 11 名起）</summary><section class="grid">{extra}</section></details>')

    page = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小G股票雷達</title>
<style>*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif;background:#f4f6fb;color:#1a2538}}main{{max-width:950px;margin:auto;padding:25px 16px 60px}}h1{{font-size:2rem;margin:8px 0}}h2{{margin:30px 0 13px}}.muted,small{{color:#718095}}.muted{{line-height:1.7}}.stats,.weights,.grid{{display:grid;gap:12px}}.stats{{grid-template-columns:repeat(3,1fr);margin:25px 0}}.stats>div,.weights>div,.card,.note{{background:white;border:1px solid #e2e7f0;border-radius:16px;padding:16px}}.stats b{{display:block;font-size:1.65rem}}.weights{{grid-template-columns:repeat(4,1fr)}}.weights strong{{display:block;font-size:1.3rem}}.weights small{{display:block;line-height:1.5}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.heading{{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}}.heading strong{{font-size:1.25rem}}.heading small{{display:block;margin-top:4px}}.tag{{font-size:.75rem;border-radius:99px;background:#eef0f4;color:#526071;padding:6px 9px;white-space:nowrap}}.green{{background:#dcf5e8;color:#137b4b}}.price{{font-size:1.6rem;font-weight:700;margin:18px 0}}.price small{{font-size:.75rem;font-weight:400}}.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:13px}}.metrics small{{display:block;font-size:.75rem}}.metrics b{{display:block;margin-top:5px}}.signal{{border-top:1px solid #edf0f4;padding-top:12px;margin:15px 0 0;font-size:.9rem}}.note{{line-height:1.8;color:#526071}}a{{color:#245f9f}}.alert{{background:#fff0d6;padding:13px;border-radius:10px}}.ranking{{display:inline-block;color:#3565a4;font-weight:800;margin-right:4px}}.scoreline{{background:#f0f6ff;border:1px solid #dceaff;border-radius:10px;padding:9px 12px;margin-top:13px;display:flex;justify-content:space-between;align-items:center;gap:10px}}.scoreline b{{font-size:1.18rem;color:#244b86}}.scoreline small{{font-size:.72rem}}.breakdown{{font-size:.8rem;color:#64748b;margin-bottom:0}}details{{margin-top:18px}}summary{{cursor:pointer;font-weight:650;background:#e5eaf2;padding:14px;border-radius:12px;margin-bottom:14px}}@media(max-width:680px){{.grid{{grid-template-columns:1fr}}.weights{{grid-template-columns:1fr 1fr}}.stats>div{{padding:11px}}.stats b{{font-size:1.3rem}}}}</style></head><body><main>
<div class="muted">STOCK RESEARCH LAB · 1.3</div><h1>📡 小G股票雷達</h1><div class="muted">中文名稱＋技術排名 · 台股 50＋美股 50 · 台灣時間產生：{updated}<br>個別股票實際交易日期請看卡片。</div>
<div class="stats"><div><small>成功掃描</small><b>{len(records)}</b></div><div><small>符合均線</small><b>{trend_count}</b></div><div><small>明顯放量</small><b>{volume_count}</b></div></div>
<h2>四大引擎預定權重</h2><div class="weights"><div><strong>30%</strong>技術分析<small>均線＋量價＋RSI 動能；已啟用技術 30 分試驗排名</small></div><div><strong>30%</strong>產業前景<small>尚未接入</small></div><div><strong>25%</strong>法人買賣<small>尚未接入</small></div><div><strong>15%</strong>國際新聞<small>尚未接入</small></div></div>
{warning}
{section(tw, '台股', '🇹🇼')}
{section(us, '美股', '🇺🇸')}
<h2>資料說明</h2><div class="note">量比＝最新完整交易日成交量 ÷ 前 20 交易日（不含當日）平均量，達到 1.5 倍才稱為明顯放量。目前技術分數最高 30 分：均線 12、量價 10、RSI 與 5 日動能 8；這是初步規則，尚未通過歷史回測及樣本外驗證，分數不代表上漲機率。<br>這是固定測試名單，不是完整台股或 S&amp;P 500 股票池；目前只對技術面給分；產業前景 30%、法人 25%、國際新聞 15% 尚未接入，所以不能稱為四因子總排名。<br>歷史價格為調整價，可能與券商報價不同；未評估交易成本，並非買賣建議，也不會下單。<br><a href="data/history.csv">檢視 CSV 歷史紀錄</a></div></main></body></html>'''
    SITE_FILE.write_text(page, encoding="utf-8")


def main() -> None:
    records, errors = latest_snapshot()
    for error in errors:
        print("資料異常：", error)
    if len(records) < MIN_SUCCESS:
        raise RuntimeError(f"僅成功取得 {len(records)}/100 檔資料，保留原報告；檢查抓價失敗原因。")
    persist(records)
    render(records, errors)
    print(f"完成 {len(records)}/100 檔，符合均線 {sum(r['符合趨勢']=='是' for r in records)} 檔")


if __name__ == "__main__":
    main()
