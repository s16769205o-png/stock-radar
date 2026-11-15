"""小G 股票雷達：技術趨勢與成交量觀察（研究用途，不下單）。"""
from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / 'data' / 'history.csv'
SITE_FILE = ROOT / 'index.html'
VOLUME_THRESHOLD = 1.5
UNIVERSE = {
    '台股': ['2330.TW', '2454.TW', '2317.TW', '2882.TW', '1303.TW'],
    '美股': ['AAPL', 'MSFT', 'GOOGL', 'JPM', 'XOM'],
}
FIELDS = ['交易日期', '市場', '股票', '調整收盤價', 'MA20', 'MA60', '成交量', '量比', '單日漲跌幅', '量價訊號', '符合趨勢']


def classify_volume_price(volume_ratio, daily_change):
    if volume_ratio is None:
        return '量能資料不足'
    if volume_ratio >= VOLUME_THRESHOLD:
        if daily_change > 0:
            return '放量上漲'
        if daily_change < 0:
            return '放量下跌'
        return '放量持平'
    if daily_change > 0:
        return '一般量能・上漲'
    if daily_change < 0:
        return '一般量能・下跌'
    return '一般量能・持平'


def latest_snapshot():
    records, errors = [], []
    for market, codes in UNIVERSE.items():
        for code in codes:
            try:
                data = yf.Ticker(code).history(period='6mo', auto_adjust=True)
                data = data.dropna(subset=['Close', 'Volume'])
                if len(data) < 61:
                    errors.append(f'{code}：資料少於 61 筆')
                    continue
                closes = data['Close'].astype(float)
                volumes = data['Volume'].astype(float)
                price = float(closes.iloc[-1])
                previous_close = float(closes.iloc[-2])
                ma20 = float(closes.iloc[-20:].mean())
                ma60 = float(closes.iloc[-60:].mean())
                # 20個「之前」交易日：不含訊號日，避免基準被放量當日拉高。
                baseline = float(volumes.iloc[-21:-1].mean())
                latest_volume = int(volumes.iloc[-1])
                ratio_raw = latest_volume / baseline if baseline > 0 else None
                day_change = 100 * (price / previous_close - 1) if previous_close > 0 else 0.0
                signal = classify_volume_price(ratio_raw, day_change)
                record = {
                    '交易日期': data.index[-1].strftime('%Y-%m-%d'),
                    '市場': market,
                    '股票': code,
                    '調整收盤價': round(price, 2),
                    'MA20': round(ma20, 2),
                    'MA60': round(ma60, 2),
                    '成交量': latest_volume,
                    '量比': round(ratio_raw, 2) if ratio_raw is not None else '',
                    '單日漲跌幅': round(day_change, 2),
                    '量價訊號': signal,
                    '符合趨勢': '是' if price > ma20 > ma60 else '否',
                }
                records.append(record)
                print(f'{code} {record["交易日期"]}：{signal}，趨勢{record["符合趨勢"]}')
            except Exception as exc:
                errors.append(f'{code}: {type(exc).__name__}: {str(exc)[:100]}')
    return records, errors


def persist(records):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = {}
    if DATA_FILE.exists():
        with DATA_FILE.open('r', encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                if row.get('交易日期') and row.get('股票'):
                    merged[(row['交易日期'], row['股票'])] = {k: row.get(k, '') for k in FIELDS}
    for row in records:
        merged[(row['交易日期'], row['股票'])] = row
    with DATA_FILE.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow(merged[key])


def stock_card(row):
    esc = lambda v: html.escape(str(v))
    selected = row['符合趨勢'] == '是'
    vol = row['量比']
    vol_label = f'{float(vol):.2f} 倍' if vol != '' else '無資料'
    change = f'{float(row["單日漲跌幅"]):+.2f}%'
    signal = esc(row['量價訊號'])
    return f'''<article class="card">
      <div class="heading"><div><strong>{esc(row['股票'])}</strong><small>{esc(row['市場'])} · {esc(row['交易日期'])}</small></div><span class="tag {'green' if selected else ''}">{'符合均線趨勢' if selected else '未符合均線趨勢'}</span></div>
      <div class="price">{float(row['調整收盤價']):,.2f} <small>{'TWD' if row['市場']=='台股' else 'USD'}</small></div>
      <div class="metrics"><div><small>MA20</small><b>{float(row['MA20']):,.2f}</b></div><div><small>MA60</small><b>{float(row['MA60']):,.2f}</b></div><div><small>量比（前 20 日）</small><b>{vol_label}</b></div><div><small>當日漲跌</small><b>{change}</b></div></div>
      <p class="signal">量價訊號：<strong>{signal}</strong></p></article>'''


def render(records, errors):
    updated = datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')
    total_trend = sum(r['符合趨勢'] == '是' for r in records)
    total_volume = sum(str(r['量價訊號']).startswith('放量') for r in records)
    tw = [r for r in records if r['市場'] == '台股']
    us = [r for r in records if r['市場'] == '美股']
    error_text = f'<p class="alert">有 {len(errors)} 檔資料未更新，請查看 Actions 日誌。</p>' if errors else ''
    page = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小G股票雷達</title>
<style>*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif;background:#f4f6fb;color:#1a2538}}main{{max-width:950px;margin:auto;padding:25px 16px 60px}}h1{{font-size:2rem;margin:8px 0}}h2{{margin:30px 0 13px}}.muted,small{{color:#718095}}.muted{{line-height:1.7}}.stats,.weights,.grid{{display:grid;gap:12px}}.stats{{grid-template-columns:repeat(3,1fr);margin:25px 0}}.stats>div,.weights>div,.card,.note{{background:white;border:1px solid #e2e7f0;border-radius:16px;padding:16px}}.stats b{{display:block;font-size:1.65rem}}.weights{{grid-template-columns:repeat(4,1fr)}}.weights strong{{display:block;font-size:1.3rem}}.weights small{{display:block;line-height:1.5}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.heading{{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}}.heading strong{{font-size:1.25rem}}.heading small{{display:block;margin-top:4px}}.tag{{font-size:.75rem;border-radius:99px;background:#eef0f4;color:#526071;padding:6px 9px;white-space:nowrap}}.green{{background:#dcf5e8;color:#137b4b}}.price{{font-size:1.6rem;font-weight:700;margin:18px 0}}.price small{{font-size:.75rem;font-weight:400}}.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:13px}}.metrics small{{display:block;font-size:.75rem}}.metrics b{{display:block;margin-top:5px}}.signal{{border-top:1px solid #edf0f4;padding-top:12px;margin:15px 0 0;font-size:.9rem}}.note{{line-height:1.8;color:#526071}}a{{color:#245f9f}}.alert{{background:#fff0d6;padding:13px;border-radius:10px}}@media(max-width:680px){{.grid{{grid-template-columns:1fr}}.weights{{grid-template-columns:1fr 1fr}}.stats>div{{padding:11px}}.stats b{{font-size:1.3rem}}}}</style></head><body><main>
<div class="muted">STOCK RESEARCH LAB · 1.1</div><h1>📡 小G股票雷達</h1><div class="muted">台股＋美股 · 台灣時間產生：{updated}<br>每檔股票實際交易日請看卡片日期。</div>
<div class="stats"><div><small>成功掃描</small><b>{len(records)}</b></div><div><small>符合均線</small><b>{total_trend}</b></div><div><small>明顯放量</small><b>{total_volume}</b></div></div>
<h2>四大引擎的預定權重</h2><div class="weights"><div><strong>30%</strong>技術分析<small>均線＋量價觀察；未評分</small></div><div><strong>30%</strong>產業前景<small>尚未接入</small></div><div><strong>25%</strong>法人買賣<small>尚未接入</small></div><div><strong>15%</strong>國際新聞<small>尚未接入</small></div></div>
{error_text}<h2>🇹🇼 台股（{len(tw)} 檔）</h2><section class="grid">{''.join(stock_card(r) for r in tw) or '暫無台股資料'}</section><h2>🇺🇸 美股（{len(us)} 檔）</h2><section class="grid">{''.join(stock_card(r) for r in us) or '暫無美股資料'}</section>
<h2>資料說明</h2><div class="note">量比＝最新一個完整交易日成交量 ÷ <strong>此前 20 個交易日</strong>（不含當日）的平均成交量。<strong>量比 ≥ 1.5</strong> 才視為明顯放量，並依當日調整後價格的漲跌區分放量上漲與放量下跌。<br>量價目前只是附加觀察訊號，不是買入條件，也沒有改動原先 30／30／25／15 的規劃權重。<br>此處價格為調整後歷史價，可能不同於券商畫面。放量可能是突破也可能是賣壓，請勿視作保證漲跌。本系統不會下單。<br><a href="data/history.csv">查看歷史紀錄 CSV</a>（舊紀錄缺少的新欄位會保持空白）。</div></main></body></html>'''
    SITE_FILE.write_text(page, encoding='utf-8')


def main():
    records, errors = latest_snapshot()
    for error in errors:
        print('資料問題：', error)
    if not records:
        raise RuntimeError('所有股價下載失敗；不覆寫既有網站及紀錄')
    persist(records)
    render(records, errors)
    print(f'完成：{len(records)} 檔，符合均線 {sum(r["符合趨勢"] == "是" for r in records)} 檔')


if __name__ == '__main__':
    main()
