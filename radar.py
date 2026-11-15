"""Mobile-friendly TW/US stock radar. Research only; no brokerage access."""
from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "history.csv"
SITE_FILE = ROOT / "index.html"

# These are a small, fixed test universe, NOT personalized buy recommendations.
UNIVERSE = {
    "台股": ["2330.TW", "2454.TW", "2317.TW", "2882.TW", "1303.TW"],
    "美股": ["AAPL", "MSFT", "GOOGL", "JPM", "XOM"],
}
FIELDS = ["交易日期", "市場", "股票", "調整收盤價", "MA20", "MA60", "成交量", "量比", "符合趨勢"]


def latest_snapshot() -> tuple[list[dict], list[str]]:
    records, errors = [], []
    for market, symbols in UNIVERSE.items():
        for symbol in symbols:
            try:
                df = yf.Ticker(symbol).history(period="6mo", auto_adjust=True)
                df = df.dropna(subset=["Close", "Volume"])
                if len(df) < 60:
                    errors.append(f"{symbol}: 交易日資料少於 60 筆")
                    continue
                closes = df["Close"].astype(float)
                volumes = df["Volume"].astype(float)
                price = float(closes.iloc[-1])
                ma20 = float(closes.tail(20).mean())
                ma60 = float(closes.tail(60).mean())
                volume = int(volumes.iloc[-1])
                avg_volume = float(volumes.tail(20).mean())
                ratio = round(volume / avg_volume, 2) if avg_volume > 0 else None
                date = df.index[-1].strftime("%Y-%m-%d")
                records.append({
                    "交易日期": date,
                    "市場": market,
                    "股票": symbol,
                    "調整收盤價": round(price, 2),
                    "MA20": round(ma20, 2),
                    "MA60": round(ma60, 2),
                    "成交量": volume,
                    "量比": ratio,
                    "符合趨勢": "是" if price > ma20 > ma60 else "否",
                })
                print(f"{symbol} {date}: {'符合' if price > ma20 > ma60 else '觀察'}")
            except Exception as exc:
                # One failed symbol must not prevent all others from being reported.
                errors.append(f"{symbol}: {type(exc).__name__}: {str(exc)[:90]}")
    return records, errors


def persist(records: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    previous = {}
    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("交易日期") and row.get("股票"):
                    previous[(row["交易日期"], row["股票"])] = row
    for record in records:
        previous[(record["交易日期"], record["股票"])] = record
    with DATA_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for _, record in sorted(previous.items(), key=lambda item: item[0]):
            writer.writerow(record)


def card(row: dict) -> str:
    market = html.escape(row["市場"])
    symbol = html.escape(row["股票"])
    date = html.escape(row["交易日期"])
    is_selected = row["符合趨勢"] == "是"
    status = "符合趨勢條件" if is_selected else "未符合趨勢條件"
    cls = "pass" if is_selected else "watch"
    ratio = f'{row["量比"]:.2f} 倍' if row["量比"] is not None else "無資料"
    return f'''<article class="stock-card">
      <div class="card-top"><div><div class="symbol">{symbol}</div><div class="meta">{market} · {date}</div></div><span class="pill {cls}">{status}</span></div>
      <div class="price">{float(row["調整收盤價"]):,.2f} <span>{'TWD' if market == '台股' else 'USD'}</span></div>
      <div class="metrics"><div><small>MA20</small><strong>{float(row['MA20']):,.2f}</strong></div><div><small>MA60</small><strong>{float(row['MA60']):,.2f}</strong></div><div><small>成交量 / 20 日均量</small><strong>{ratio}</strong></div></div>
      <div class="reason">{'股價 > MA20 > MA60' if is_selected else '目前不滿足「股價 > MA20 > MA60」'}</div>
    </article>'''


def render(records: list[dict], errors: list[str]) -> None:
    tpe_now = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    selected = sum(row["符合趨勢"] == "是" for row in records)
    tw = [row for row in records if row["市場"] == "台股"]
    us = [row for row in records if row["市場"] == "美股"]
    warning = (f'<p class="alert">有 {len(errors)} 檔資料未能更新；請到 GitHub Actions 檢查執行紀錄。</p>'
               if errors else "")
    page = f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>小G股票雷達</title>
<style>
:root {{color-scheme:light; font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif;background:#f4f6fa;color:#192335}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1040px;margin:auto;padding:24px 15px 56px}}
header{{padding:18px 0 12px}}h1{{font-size:clamp(1.8rem,5vw,2.5rem);margin:4px 0}}h2{{font-size:1.28rem;margin:28px 0 12px}}.muted{{color:#677486;font-size:.91rem;line-height:1.6}}.eyebrow{{color:#28689e;font-size:.83rem;font-weight:700;letter-spacing:.08em}}
.overview{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}}.stat{{background:white;padding:15px 12px;border:1px solid #e6ebf2;border-radius:14px}}.stat strong{{display:block;font-size:1.55rem;margin-top:4px}}.stat span{{color:#677486;font-size:.8rem}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.stock-card{{background:white;border:1px solid #e6ebf2;border-radius:18px;padding:17px;min-width:0}}
.card-top{{display:flex;justify-content:space-between;gap:9px;align-items:flex-start}}.symbol{{font-weight:750;font-size:1.23rem}}.meta{{font-size:.78rem;color:#778294;margin-top:4px}}.pill{{border-radius:999px;font-size:.72rem;padding:5px 8px;white-space:nowrap}}.pass{{background:#e0f5e9;color:#187343}}.watch{{background:#eef1f6;color:#556273}}
.price{{font-size:1.7rem;font-weight:750;margin:17px 0}}.price span{{font-size:.77rem;font-weight:500;color:#677486}}.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.metrics small{{display:block;color:#677486;font-size:.73rem}}.metrics strong{{display:block;font-size:.97rem;margin-top:4px}}.reason{{border-top:1px solid #edf0f4;margin-top:16px;padding-top:12px;font-size:.83rem;color:#526177}}
.note{{background:#fff;border:1px solid #e6ebf2;border-radius:16px;padding:17px;line-height:1.8;color:#536177;font-size:.9rem}}.weights{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}}.weight{{background:#fff;border:1px solid #e6ebf2;padding:10px 8px;border-radius:11px;font-size:.76rem}}.weight strong{{display:block;font-size:1.06rem;color:#212b3a}}.weight span{{display:block;color:#7d8796;font-size:.69rem}}a{{color:#245f9f}}.alert{{color:#854d0e;background:#fff5da;padding:12px;border-radius:10px}}
@media(max-width:640px){{.grid{{grid-template-columns:1fr}}.overview{{gap:7px}}.stat{{padding:12px 8px}}.stat strong{{font-size:1.25rem}}.weights{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main><header><div class="eyebrow">STOCK RESEARCH LAB · 1.0</div><h1>📡 小G股票雷達</h1><div class="muted">自動掃描台股＋美股｜台灣時間更新：{tpe_now}<br>各檔股票的資料日期可能不同，請以卡片日期為準。</div></header>
<div class="overview"><div class="stat"><span>成功掃描</span><strong>{len(records)}</strong></div><div class="stat"><span>符合趨勢</span><strong>{selected}</strong></div><div class="stat"><span>市場</span><strong>TW + US</strong></div></div>
<h2>四大評分引擎：建置進度</h2><div class="weights"><div class="weight"><strong>30%</strong>技術分析<span>均線篩選啟用 · 尚未給分</span></div><div class="weight"><strong>30%</strong>產業前景<span>尚未接入</span></div><div class="weight"><strong>25%</strong>法人買賣<span>尚未接入</span></div><div class="weight"><strong>15%</strong>國際新聞<span>尚未接入</span></div></div>
{warning}
<h2>🇹🇼 台股 <span class="muted">{len(tw)} 檔</span></h2><section class="grid">{''.join(card(r) for r in tw) or '<p>暫無台股資料</p>'}</section>
<h2>🇺🇸 美股 <span class="muted">{len(us)} 檔</span></h2><section class="grid">{''.join(card(r) for r in us) or '<p>暫無美股資料</p>'}</section>
<h2>說明</h2><div class="note">目前只採用「調整後收盤價 > MA20 > MA60」作為研究用趨勢篩選，尚未執行完整 30／30／25／15 綜合評分。價格是用於分析的歷史調整價格，可能不同於券商顯示的當日實際收盤價。<br>入選不代表可以買入、報酬保證或自動交易。本系統沒有連接券商，也不會下單。<br><a href="data/history.csv">查看歷史 CSV 紀錄</a>（同一檔同一交易日只保存一筆）。</div>
</main></body></html>'''
    SITE_FILE.write_text(page, encoding="utf-8")


def main() -> None:
    records, errors = latest_snapshot()
    for error in errors:
        print("資料問題：", error)
    if not records:
        raise RuntimeError("全部股票下載失敗；保留舊網頁與紀錄，不覆寫")
    persist(records)
    render(records, errors)
    print(f"完成：{len(records)} 檔，符合 {sum(r['符合趨勢']=='是' for r in records)} 檔")


if __name__ == "__main__":
    main()
