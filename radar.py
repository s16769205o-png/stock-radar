"""小G 股票雷達 1.22：1.5 的績效追蹤＋前十名升降榜。

免費 GitHub Actions、無券商連線，僅供研究。5/10/20 個交易日績效是
「訊號當日調整收盤價 -> 第 N 個後續交易日調整收盤價」的紙上觀察報酬，
不能假裝在訊號收盤價真的成交，也不代表回測勝率或未來報酬。
"""
from __future__ import annotations

import csv
import html
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from revenue import monthly_revenue_section
from profitability import quarterly_profit_section
from fundamental_crosscheck import fundamental_crosscheck_section
from industry_readiness import industry_readiness_section
from industry_lens import industry_lens_section
from industry_briefs import add_industry_briefs
from mobile_tabs import install_mobile_tabs
from villa_hub import install_villa_hub
from famous_13f import install_famous_room
from villa_search import install_stock_search
from sector_indices import install_sector_indices
from site_quality import verify_site
from system_health import health_section

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "history.csv"
SITE_FILE = ROOT / "index.html"
VOLUME_THRESHOLD = 1.5
MIN_SUCCESS = 70
BATCH_SIZE = 10
HORIZONS = (5, 10, 20)
BENCHMARKS = {"台股": ("0050.TW", "0050 台灣50 ETF"), "美股": ("SPY", "SPY 標普500 ETF")}

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
    '2330':'台積電','2454':'聯發科','2317':'鴻海','2308':'台達電','2382':'廣達',
    '2303':'聯電','2327':'國巨','2357':'華碩','2376':'技嘉','2377':'微星',
    '2408':'南亞科','2409':'友達','2412':'中華電','3008':'大立光','3017':'奇鋐',
    '3034':'聯詠','3231':'緯創','3443':'創意','3532':'台勝科','3661':'世芯-KY',
    '3711':'日月光投控','4938':'和碩','4958':'臻鼎-KY','5269':'祥碩','1301':'台塑',
    '1303':'南亞','1326':'台化','2002':'中鋼','1101':'台泥','1102':'亞泥',
    '1216':'統一','2207':'和泰車','2603':'長榮','2609':'陽明','2615':'萬海',
    '2610':'華航','2618':'長榮航','2634':'漢翔','1476':'儒鴻','1519':'華城',
    '1590':'亞德客-KY','2881':'富邦金','2882':'國泰金','2884':'玉山金',
    '2885':'元大金','2886':'兆豐金','2891':'中信金','2892':'第一金',
    '5871':'中租-KY','5880':'合庫金',
}
# 研究用粗分類，不是交易所或 GICS 正式分類。
INDUSTRY_GROUPS = {
    '台股': {
        '半導體': '2330 2454 2303 2408 3034 3443 3532 3661 3711 5269',
        '電腦／伺服器': '2317 2382 2357 2376 2377 3231 4938',
        '電力／散熱／電子零組件': '2308 2327 3017 4958',
        '面板／光學': '2409 3008','電信': '2412','塑化': '1301 1303 1326',
        '鋼鐵': '2002','水泥': '1101 1102','食品': '1216','汽車': '2207',
        '海運': '2603 2609 2615','航空／航太': '2610 2618 2634',
        '紡織': '1476','重電／機械': '1519 1590',
        '金融': '2881 2882 2884 2885 2886 2891 2892 5871 5880',
    },
    '美股': {
        '半導體／設備': 'NVDA AVGO AMD MU INTC AMAT LRCX KLAC QCOM TXN ADI',
        '軟體／雲端／網路': 'AAPL MSFT GOOGL META ORCL CRM ADBE PLTR NOW ANET',
        '網路安全': 'PANW CRWD','電商／平台': 'AMZN UBER','汽車': 'TSLA GM',
        '工業／設備': 'CAT DE GE GEV BA','醫療／製藥': 'LLY UNH JNJ ABBV MRK PFE',
        '金融／支付': 'JPM BAC GS V MA','民生消費': 'COST WMT KO PG',
        '能源': 'XOM CVX','公用事業': 'NEE',
    },
}
INDUSTRY = {}
for _market, _groups in INDUSTRY_GROUPS.items():
    for _group, _symbols in _groups.items():
        for _symbol in _symbols.split():
            _code = _symbol + '.TW' if _market == '台股' else _symbol
            if _code in INDUSTRY:
                raise ValueError('產業分類重複：' + _code)
            INDUSTRY[_code] = _group
for _market, _codes in UNIVERSE.items():
    for _code in _codes:
        if _code not in INDUSTRY:
            raise ValueError('未分類股票：' + _code)

# 完全沿用既有歷史 CSV 欄位；新版績效直接從已存的每日紀錄還原，不需要多上傳檔案。
FIELDS = [
    '交易日期','市場','股票','調整收盤價','MA20','MA60','成交量','量比',
    '單日漲跌幅','量價訊號','符合趨勢','中文名稱','RSI14','五日動能',
    '均線分數','量價分數','動能分數','技術分數','產業','研究警示',
    '5日觀察報酬','5日基準報酬','10日觀察報酬','10日基準報酬',
    '20日觀察報酬','20日基準報酬',
]
PERFORMANCE_FIELDS = {h:(f'{h}日觀察報酬',f'{h}日基準報酬') for h in HORIZONS}


def classify_volume_price(ratio, day_change):
    if ratio is None: return '量能資料不足'
    if ratio >= VOLUME_THRESHOLD:
        return '放量上漲' if day_change > 0 else '放量下跌' if day_change < 0 else '放量持平'
    return '一般量能・上漲' if day_change > 0 else '一般量能・下跌' if day_change < 0 else '一般量能・持平'


def rsi_14(closes):
    delta = closes.diff()
    up, down = delta.clip(lower=0), (-delta).clip(lower=0)
    gain = float(up.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1])
    loss = float(down.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1])
    if loss == 0: return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1 + gain / loss)


def technique_points(price, ma20, ma60, ratio, change, rsi, momentum5):
    if price > ma20 > ma60: trend = 12
    elif price > ma20 and price > ma60: trend = 8
    elif price > ma20 or price > ma60: trend = 4
    else: trend = 0
    if ratio is not None and ratio >= VOLUME_THRESHOLD:
        volume = 10 if change > 0 else 0 if change < 0 else 3
    else: volume = 5 if change > 0 else 2 if change < 0 else 3
    strength = 5 if 50 <= rsi <= 70 else 3 if 40 <= rsi < 50 or 70 < rsi <= 80 else 1
    return trend, volume, strength + (3 if momentum5 > 0 else 0)


def research_alert(price, ma20, ma60, ratio, change, rsi, momentum5):
    alerts = []
    if ratio is not None and ratio >= VOLUME_THRESHOLD and change < 0: alerts.append('放量下跌')
    if price < ma20 and price < ma60: alerts.append('位於20/60日均線下')
    if rsi >= 80: alerts.append('RSI偏高')
    elif rsi <= 30: alerts.append('RSI偏低')
    if momentum5 <= -8: alerts.append('5日跌幅較大')
    return '、'.join(alerts)


def calculate(data, market, code):
    if data is None or data.empty or not {'Close','Volume'}.issubset(data.columns):
        raise ValueError('缺少收盤價或成交量')
    data = data.dropna(subset=['Close','Volume'])
    if len(data) < 61: raise ValueError('交易日資料不足 61 筆')
    closes, volumes = data['Close'].astype(float), data['Volume'].astype(float)
    price = float(closes.iloc[-1]); previous = float(closes.iloc[-2])
    ma20 = float(closes.iloc[-20:].mean()); ma60 = float(closes.iloc[-60:].mean())
    avg_vol = float(volumes.iloc[-21:-1].mean())
    ratio = float(volumes.iloc[-1]) / avg_vol if avg_vol > 0 else None
    change = 100 * (price/previous - 1) if previous > 0 else 0.0
    rsi = rsi_14(closes)
    mom5 = 100 * (price / float(closes.iloc[-6]) - 1) if closes.iloc[-6] > 0 else 0.0
    trend, vol, momentum = technique_points(price,ma20,ma60,ratio,change,rsi,mom5)
    return {
        '交易日期':data.index[-1].strftime('%Y-%m-%d'), '市場':market, '股票':code,
        '調整收盤價':round(price,2), 'MA20':round(ma20,2), 'MA60':round(ma60,2),
        '成交量':int(volumes.iloc[-1]),'量比':round(ratio,2) if ratio is not None else '',
        '單日漲跌幅':round(change,2),'量價訊號':classify_volume_price(ratio,change),
        '符合趨勢':'是' if price>ma20>ma60 else '否',
        '中文名稱':TW_NAMES.get(code.split('.')[0],'') if market=='台股' else '',
        'RSI14':round(rsi,1),'五日動能':round(mom5,2),
        '均線分數':trend,'量價分數':vol,'動能分數':momentum,'技術分數':trend+vol+momentum,
        '產業':INDUSTRY[code], '研究警示':research_alert(price,ma20,ma60,ratio,change,rsi,mom5),
    }


def get_bulk(codes):
    return yf.download(tickers=codes,period='6mo',interval='1d',group_by='ticker',
                       auto_adjust=True,progress=False,threads=True,timeout=25)


def frame_for(bulk, code):
    if isinstance(bulk.columns,pd.MultiIndex):
        if code in bulk.columns.get_level_values(0): return bulk[code].copy()
        if code in bulk.columns.get_level_values(1): return bulk.xs(code,axis=1,level=1).copy()
    raise ValueError('批次資料缺少此股票')


def latest_snapshot():
    records, errors, histories = [], [], {}
    for market,codes in UNIVERSE.items():
        for start in range(0,len(codes),BATCH_SIZE):
            chunk=codes[start:start+BATCH_SIZE]
            try: bulk=get_bulk(chunk)
            except Exception as exc:
                bulk=pd.DataFrame()
                print('批次資料問題：',type(exc).__name__,str(exc)[:90])
            for code in chunk:
                try:
                    try:
                        frame=frame_for(bulk,code)
                        row=calculate(frame,market,code)
                    except (ValueError,KeyError,TypeError):
                        frame=yf.Ticker(code).history(period='6mo',auto_adjust=True)
                        row=calculate(frame,market,code)
                    histories[code]=frame
                    records.append(row)
                    print(f'{code} {row["交易日期"]}：技術{row["技術分數"]}/30；{row["量價訊號"]}')
                except Exception as exc:
                    errors.append(f'{code}: {type(exc).__name__}: {str(exc)[:90]}')
            time.sleep(0.4)
    return records,errors,histories


def persist(records):
    DATA_FILE.parent.mkdir(parents=True,exist_ok=True)
    merged={}
    if DATA_FILE.exists():
        with DATA_FILE.open('r',encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row.get('交易日期') and row.get('股票'):
                    merged[(row['交易日期'],row['股票'])]={field:row.get(field,'') for field in FIELDS}
    for row in records:
        key=(row['交易日期'],row['股票'])
        if key in merged:
            for stock_field,bench_field in PERFORMANCE_FIELDS.values():
                for field in (stock_field,bench_field):
                    if merged[key].get(field,'')!='' and row.get(field,'')=='':
                        row[field]=merged[key][field]
        merged[key]=row
    rows=list(merged.values())
    save_history(rows)
    return rows


def save_history(rows):
    """Re-save all archive rows, including matured forward observations, without duplicates."""
    DATA_FILE.parent.mkdir(parents=True,exist_ok=True)
    with DATA_FILE.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        for row in sorted(rows,key=lambda r:(r['交易日期'],r['股票'])):
            writer.writerow({field:row.get(field,'') for field in FIELDS})


def rank(row):
    return (-int(row['技術分數']),row['符合趨勢']!='是',-float(row['量比'] or 0),row['股票'])


def show_name(row): return row.get('中文名稱','') or row['股票']
def esc(value): return html.escape(str(value),quote=True)


def stock_card(row, position):
    name=esc(show_name(row)); score=int(row['技術分數'])
    selected=row['符合趨勢']=='是'; alert=row.get('研究警示','')
    ratio=f"{float(row['量比']):.2f} 倍" if row['量比']!='' else '無資料'
    alert_line=f'<p class="alert-line">⚠️ 研究提醒：{esc(alert)}</p>' if alert else ''
    return f'''<article class="card"><div class="heading"><div><span class="ranking">#{position}</span>
    <strong>{name}</strong><small>{esc(row['股票'])} · {esc(row['產業'])} · {esc(row['交易日期'])}</small></div>
    <span class="tag {'green' if selected else ''}">{'符合均線趨勢' if selected else '未符合均線趨勢'}</span></div>
    <div class="scoreline"><b>{score} / 30 分</b><small>實驗性技術分數</small></div>
    <div class="price">{float(row['調整收盤價']):,.2f} <small>{'TWD' if row['市場']=='台股' else 'USD'}</small></div>
    <div class="metrics"><div><small>MA20</small><b>{float(row['MA20']):,.2f}</b></div>
    <div><small>MA60</small><b>{float(row['MA60']):,.2f}</b></div>
    <div><small>量比（前20日）</small><b>{ratio}</b></div>
    <div><small>當日漲跌</small><b>{float(row['單日漲跌幅']):+.2f}%</b></div>
    <div><small>RSI14</small><b>{float(row['RSI14']):.1f}</b></div>
    <div><small>5日動能</small><b>{float(row['五日動能']):+.2f}%</b></div></div>
    <p class="signal">量價訊號：<b>{esc(row['量價訊號'])}</b></p>{alert_line}
    <details class="carddetail"><summary>查看分數拆解</summary><p>均線 {row['均線分數']}/12 · 量價 {row['量價分數']}/10 · RSI／5日動能 {row['動能分數']}/8</p></details>
    </article>'''



def observed_return(frame, asof, trading_days):
    """Adjusted close return as of the stock's actual completed trading date."""
    if frame is None or frame.empty or 'Close' not in frame.columns:
        return None
    prices = []
    for ts, close in frame['Close'].items():
        try:
            v = float(close)
            if pd.notna(v) and v > 0:
                prices.append((ts.strftime('%Y-%m-%d'), v))
        except (ValueError, TypeError, AttributeError):
            continue
    positions = [i for i, (date, _) in enumerate(prices) if date == asof]
    if not positions or positions[-1] < trading_days:
        return None
    end = positions[-1]
    return 100 * (prices[end][1] / prices[end - trading_days][1] - 1)


def industry_strength_section(records, histories, benchmarks):
    """Sector PRICE/BREADTH observations only, never an industry-fundamental score."""
    sections = ['<h2>🏗️ 產業研究室・第一期：族群強弱</h2>',
        '<p class="muted">只用目前固定100檔樣本：比較族群內股票近20／60個交易日的平均調整收盤價變化、20日均線上方比例，及20日平均報酬相對0050或SPY的差距。這些是等權價格動能與廣度觀察，<b>不是產業營收、獲利、資本支出或未來前景的30分評分</b>。成分太少的族群僅作參考。</p>']
    for market, flag in (('台股', '🇹🇼'), ('美股', '🇺🇸')):
        market_rows = [r for r in records if r.get('市場') == market and r.get('交易日期')]
        if not market_rows:
            sections.append(f'<h3>{flag} {market}</h3><p class="muted">本次沒有有效資料。</p>')
            continue
        current_date = max(r['交易日期'] for r in market_rows)
        market_rows = [r for r in market_rows if r['交易日期'] == current_date]
        benchmark_frame = benchmarks.get(market)
        bench20 = observed_return(benchmark_frame, current_date, 20)
        bench60 = observed_return(benchmark_frame, current_date, 60)
        grouped = defaultdict(list)
        for row in market_rows:
            code = row['股票']
            frame = histories.get(code)
            ret20 = observed_return(frame, current_date, 20)
            ret60 = observed_return(frame, current_date, 60)
            if ret20 is not None and ret60 is not None:
                grouped[row['產業']].append((row, ret20, ret60))
        result = []
        for name, members in grouped.items():
            n = len(members)
            avg20 = sum(x[1] for x in members) / n
            avg60 = sum(x[2] for x in members) / n
            breadth = 100 * sum(float(x[0]['調整收盤價']) > float(x[0]['MA20']) for x in members) / n
            rel20 = avg20 - bench20 if bench20 is not None else None
            rel60 = avg60 - bench60 if bench60 is not None else None
            if n < 3:
                signal = '樣本少'
            elif rel20 is None or rel60 is None:
                signal = '基準缺資料'
            elif rel20 > 0 and rel60 > 0 and breadth >= 60:
                signal = '價格與廣度偏強'
            else:
                signal = '混合／待觀察'
            result.append((name, n, avg20, avg60, breadth, rel20, signal))
        result.sort(key=lambda r: (r[5] is None, -(r[5] if r[5] is not None else r[2]), r[0]))
        lines = []
        for name, n, avg20, avg60, breadth, rel20, signal in result:
            relative = f'{rel20:+.1f} 百分點' if rel20 is not None else '—'
            lines.append(f'<tr><td>{esc(name)}</td><td>{n}</td><td>{avg20:+.1f}%</td>'
                         f'<td>{avg60:+.1f}%</td><td>{breadth:.0f}%</td><td>{relative}</td><td>{esc(signal)}</td></tr>')
        bench_name = esc(BENCHMARKS[market][1])
        sections.append(f'<h3>{flag} {market}｜{esc(current_date)}｜對照 {bench_name}</h3>'
                        '<div class="table-wrap"><table><thead><tr><th>研究族群</th><th>樣本</th>'
                        '<th>20日平均</th><th>60日平均</th><th>站上MA20</th><th>相對基準20日</th><th>觀察訊號</th>'
                        '</tr></thead><tbody>' + ''.join(lines) + '</tbody></table></div>'
                        + ('<p class="muted">基準價格日期不同或資料不足；相對強弱暫不計算。</p>' if bench20 is None or bench60 is None else ''))
    return ''.join(sections)

def sector_table(rows):
    by_sector=defaultdict(list)
    for row in rows:by_sector[row['產業']].append(row)
    items=[]
    for sector,members in by_sector.items():
        ordered=sorted(members,key=rank)
        mean_score=sum(int(m['技術分數']) for m in members)/len(members)
        top=', '.join(f"{show_name(v)}（{v['技術分數']}分）" for v in ordered[:3])
        items.append((mean_score,sector,len(members),top))
    items.sort(key=lambda x:(-x[0],x[1]))
    lines=''.join(f'<tr><td>{esc(sector)}</td><td>{count}</td><td>{score:.1f}/30</td><td>{esc(top)}</td></tr>'
                  for score,sector,count,top in items)
    return ('<div class="table-wrap"><table><thead><tr><th>產業群</th><th>檔數</th>'
            '<th>平均技術分</th><th>群內前三名</th></tr></thead><tbody>'+lines+'</tbody></table></div>')


def historic_top10(history_rows):
    """Use only archived historical scores, never recalculate old scores using today's data.

    Need >=40 valid observations per market-date to avoid ranking a partial download.
    Later observations of the same market/date are deduplicated by (date,symbol) in CSV.
    """
    groups=defaultdict(list)
    for r in history_rows:
        if r.get('市場') not in UNIVERSE or r.get('股票') not in UNIVERSE[r['市場']]:continue
        if not r.get('技術分數') or not r.get('交易日期'): continue
        try:
            int(r['技術分數'])
            if float(r['調整收盤價'])<=0:continue
        except (ValueError,TypeError):continue
        groups[(r['市場'],r['交易日期'])].append(r)
    all_signals=[]
    for (market,date),rows in sorted(groups.items()):
        if len(rows)<40:continue
        top=sorted(rows,key=rank)[:10]
        for i,r in enumerate(top,1):
            all_signals.append({'市場':market,'交易日期':date,'股票':r['股票'],
                                '中文名稱':r.get('中文名稱',''),'名次':i,
                                '技術分數':int(r['技術分數']),'_archive':r})
    return all_signals


def ranking_changes(records, history_rows, market):
    # Compare full market days while distinguishing score changes from tie order.
    current_rows = [r for r in records if r.get('市場') == market and
                    r.get('交易日期') and r.get('技術分數') not in ('', None)]
    if not current_rows:
        return {'status':'no_current'}
    latest_date = max(r['交易日期'] for r in current_rows)
    today_rows = [r for r in current_rows if r['交易日期'] == latest_date]
    if len({r['股票'] for r in today_rows}) < len(UNIVERSE[market]):
        return {'status':'partial','current_date':latest_date}
    today_top = sorted(today_rows, key=rank)[:10]
    by_date = defaultdict(dict)
    for row in history_rows:
        if row.get('市場') != market or not row.get('交易日期') or row['交易日期'] >= latest_date:
            continue
        symbol = row.get('股票')
        if symbol not in UNIVERSE[market] or row.get('技術分數') in ('', None):
            continue
        try:
            int(row['技術分數'])
            if float(row['調整收盤價']) <= 0: continue
        except (ValueError, TypeError, KeyError):
            continue
        by_date[row['交易日期']][symbol] = row
    prior_dates = [day for day, symbols in by_date.items() if len(symbols) >= len(UNIVERSE[market])]
    if not prior_dates:
        return {'status':'waiting', 'current_date':latest_date, 'current':today_top}
    previous_date = max(prior_dates)
    old_pool = by_date[previous_date]
    prior_top = sorted(old_pool.values(), key=rank)[:10]
    prior_positions = {r['股票']: i for i, r in enumerate(prior_top, 1)}
    prior_scores = {symbol: int(r['技術分數']) for symbol, r in old_pool.items()}
    score_counts = {}
    for r in today_rows:
        score = int(r['技術分數'])
        score_counts[score] = score_counts.get(score, 0) + 1
    current_set = {r['股票'] for r in today_top}
    updates = []
    for i, row in enumerate(today_top, 1):
        prev = prior_positions.get(row['股票'])
        delta = prev - i if prev is not None else None
        score = int(row['技術分數'])
        old_score = prior_scores.get(row['股票'])
        point_change = score - old_score if old_score is not None else None
        same_group = score_counts[score] > 1
        if prev is None:
            label = '新進前十'
            if point_change is not None:
                label += f' · 分數{point_change:+d}' if point_change else ' · 分數持平'
        elif point_change == 0:
            movement = f'排序↑{delta}' if delta > 0 else f'排序↓{-delta}' if delta < 0 else '排序不變'
            label = ('同分群・' if same_group else '分數持平・') + movement
        else:
            movement = f' · 排序↑{delta}' if delta > 0 else f' · 排序↓{-delta}' if delta < 0 else ''
            label = (f'分數{point_change:+d}' if point_change is not None else '分數未知') + movement
        updates.append({'position': i, 'symbol': row['股票'], 'name': show_name(row),
                        'score': score, 'previous': prev, 'delta': delta,
                        'score_delta': point_change, 'same_score_group': same_group, 'label': label})
    exited = [{'symbol': r['股票'], 'name': show_name(r), 'previous': i}
              for i, r in enumerate(prior_top, 1) if r['股票'] not in current_set]
    return {'status':'ok','current_date': latest_date,'previous_date':previous_date,
            'updates':updates,'exited':exited}

def ranking_changes_section(records, history_rows):
    sections=[]
    for market,flag in (('台股','🇹🇼'),('美股','🇺🇸')):
        result=ranking_changes(records,history_rows,market)
        status=result['status']
        if status=='no_current':
            sections.append(f'<h3>{flag} {market}</h3><p class="muted">這次沒有可用的完整股價資料。</p>')
            continue
        if status=='partial':
            sections.append(f'<h3>{flag} {market}</h3><p class="muted">本次 {esc(result["current_date"])} 有效股票未滿 50 檔，不比較排行榜，以免誤判。</p>')
            continue
        if status=='waiting':
            sections.append(f'<h3>{flag} {market}</h3><p class="muted">本次 {esc(result["current_date"])} 已保存；還沒有另一個完整的較早交易日可比較。累積下一個交易日後會開始顯示升降。</p>')
            continue
        line_items=[]
        for item in result['updates']:
            delta=item['delta']
            change = item['score_delta']
            cls = 'up' if change is not None and change > 0 else 'down' if change is not None and change < 0 else 'same'
            line_items.append(f'<li class="moveitem"><span class="movename">#{item["position"]} <b>{esc(item["name"])}</b> '
                              f'<small>{esc(item["symbol"])} · {item["score"]}/30</small></span>'
                              f'<span class="movetag {cls}">{esc(item["label"])}</span></li>')
        exittext=', '.join(f'{esc(x["name"])}（原 #{x["previous"]}）' for x in result['exited'])
        exitline=f'<p class="muted">離開前十：{exittext}</p>' if exittext else '<p class="muted">本次前十名名單沒有股票退出。</p>'
        sections.append(f'<h3>{flag} {market}｜{esc(result["current_date"])} vs {esc(result["previous_date"])}</h3>'
                        f'<ol class="movelist">{"".join(line_items)}</ol>{exitline}')
    return '<h2>📈 排行榜變動室</h2><p class="muted">使用相同技術評分，比較各市場最新完整交易日與前一次有完整存檔的交易日（可能不是昨天）。新進前十表示上次不在前十；並非第一次被選到。同分群的名次可能因量比等次要條件互換，請同時看分數變化；名次與分數都不是股價報酬或買入訊號。</p>'+''.join(sections)


def close_prices(frame):
    """Return {YYYY-mm-dd: adjusted close} and chronological dates, excluding missing/zero values."""
    if frame is None or frame.empty or 'Close' not in frame.columns:return {},[]
    closes={}
    for timestamp,price in frame['Close'].items():
        try:
            date=timestamp.strftime('%Y-%m-%d')
            value=float(price)
            if value>0 and pd.notna(value):closes[date]=value
        except (ValueError,TypeError,AttributeError):pass
    return closes,sorted(closes)


def evaluate_signals(history_rows, hist_frames, benchmark_frames):
    """Descriptive forward close-to-close observations; not trade execution or independent trials."""
    signals=historic_top10(history_rows)
    caches={code:close_prices(frame) for code,frame in hist_frames.items()}
    benchmarks={market:close_prices(benchmark_frames.get(market)) for market in BENCHMARKS}
    by_market=defaultdict(lambda:{h:[] for h in HORIZONS})
    immature=defaultdict(lambda:{h:0 for h in HORIZONS})
    missing=defaultdict(lambda:{h:0 for h in HORIZONS})
    for sig in signals:
        market=sig['市場'];code=sig['股票'];day=sig['交易日期']
        stock_map,stock_days=caches.get(code,({},[]))
        bench_map,_=benchmarks.get(market,({},[]))
        archive=sig['_archive']
        for h in HORIZONS:
            stock_field,bench_field=PERFORMANCE_FIELDS[h]
            # Persisted outcomes survive beyond the six-month Yahoo download window.
            try:
                if archive.get(stock_field,'')!='' and archive.get(bench_field,'')!='':
                    gain=float(archive[stock_field]);bench_gain=float(archive[bench_field])
                    by_market[market][h].append({'代碼':code,'起始日':day,'到期日':'已歸檔',
                                                 '股票報酬':gain,'基準報酬':bench_gain,'超額':gain-bench_gain})
                    continue
            except (TypeError,ValueError):pass
            if day not in stock_map or day not in bench_map:
                missing[market][h]+=1
                continue
            start_index=stock_days.index(day)
            idx=start_index+h
            if idx>=len(stock_days):
                immature[market][h]+=1
                continue
            end_date=stock_days[idx]
            if end_date not in bench_map:
                missing[market][h]+=1
                continue
            gain=100*(stock_map[end_date]/stock_map[day]-1)
            bench_gain=100*(bench_map[end_date]/bench_map[day]-1)
            archive[stock_field]=round(gain,5)
            archive[bench_field]=round(bench_gain,5)
            by_market[market][h].append({'代碼':code,'起始日':day,'到期日':end_date,
                                         '股票報酬':gain,'基準報酬':bench_gain,'超額':gain-bench_gain})
    return signals,by_market,immature,missing


def performance_section(market,signals,results,immature,missing):
    count_dates=len({x['交易日期'] for x in signals if x['市場']==market})
    bench=BENCHMARKS[market][1]
    if not count_dates:
        return (f'<h3>{esc(market)}｜對照 {esc(bench)}</h3>'
                '<p class="muted">尚無完整的歷史前十名存檔。從本版開始保存訊號，未來才有可追蹤的樣本。</p>')
    lines=[]
    for h in HORIZONS:
        rows=results[market][h]
        n=len(rows)
        if n:
            avg=sum(x['股票報酬'] for x in rows)/n
            bench_avg=sum(x['基準報酬'] for x in rows)/n
            excess=avg-bench_avg
            better=sum(x['超額']>0 for x in rows)/n*100
            color='pos' if excess>=0 else 'neg'
            lines.append(f'<tr><td>{h} 日</td><td>{n}</td><td>{avg:+.2f}%</td><td>{bench_avg:+.2f}%</td>'
                         f'<td class="{color}">{excess:+.2f} 百分點</td><td>{better:.0f}%</td></tr>')
        else:
            lines.append(f'<tr><td>{h} 日</td><td>0</td><td colspan="4">尚無到期且資料齊全的樣本</td></tr>')
    pending='、'.join(f'{h} 日尚待成熟 {immature[market][h]} 筆' for h in HORIZONS)
    unavailable=sum(missing[market].values())
    details=f'；無法比對資料 {unavailable} 個期限觀察' if unavailable else ''
    return (f'<h3>{esc(market)}｜對照 {esc(bench)}</h3>'
            f'<p class="muted">歷史排名已記錄 {count_dates} 個交易日，每次僅取該市場前十名。{pending}{details}。</p>'
            '<div class="table-wrap"><table><thead><tr><th>觀察期</th><th>到期筆數</th><th>股票平均</th>'
            '<th>基準平均</th><th>平均超額</th><th>跑贏基準</th></tr></thead><tbody>'
            +''.join(lines)+'</tbody></table></div>')


def render(records,errors,history_rows,history_frames,benchmark_frames,benchmark_errors):
    updated=datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')
    tw=sorted([r for r in records if r['市場']=='台股'],key=rank)
    us=sorted([r for r in records if r['市場']=='美股'],key=rank)
    alert_rows=sorted((r for r in records if r['研究警示']),key=lambda r:(r['市場'],rank(r)))
    top_alerts=''.join(f'<li><b>{esc(show_name(r))}</b>（{esc(r["股票"])}）：{esc(r["研究警示"])}</li>' for r in alert_rows[:12])
    warning=f'<p class="warning">本次有 {len(errors)} 檔無法取得資料，請查看 Actions 日誌。</p>' if errors else ''
    signals,results,immature,missing=evaluate_signals(history_rows,history_frames,benchmark_frames)
    warning_bench=('<p class="warning">績效比較基準下載有問題：'+esc('；'.join(benchmark_errors))+'</p>') if benchmark_errors else ''

    def market_section(rows,label):
        primary=''.join(stock_card(r,i) for i,r in enumerate(rows[:10],1))
        rest=''.join(stock_card(r,i) for i,r in enumerate(rows[10:],11))
        return f'''<h2>{label}｜技術排名前10</h2><p class="muted">僅此固定測試池內的排名，非全市場名次。</p>
        <section class="grid">{primary}</section><details class="rest"><summary>展開其餘 {len(rows[10:])} 檔</summary><section class="grid">{rest}</section></details>'''

    page=f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>小G股票雷達 1.22</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f5f7fb;color:#202a3c;font-family:system-ui,-apple-system,'Noto Sans TC',sans-serif}}
    main{{max-width:1010px;margin:auto;padding:28px 16px 64px}}h1{{font-size:2.1rem;margin:8px 0}}h2{{margin:32px 0 12px;font-size:1.35rem}}h3{{margin:20px 0 10px}}
    .muted,small{{color:#6b7789}}.muted{{line-height:1.7;font-size:.92rem}}.eyebrow{{font-size:.79rem;letter-spacing:.07em;color:#325e96;font-weight:750}}
    .stats,.weights,.grid{{display:grid;gap:12px}}.stats{{grid-template-columns:repeat(3,minmax(0,1fr));margin:23px 0}}.weights{{grid-template-columns:repeat(4,minmax(0,1fr))}}
    .stats>div,.weights>div,.card,.note,.table-wrap{{background:white;border:1px solid #e0e6f0;border-radius:15px;padding:15px}}.stats strong{{display:block;font-size:1.55rem}}
    .weights b{{display:block;font-size:1.2rem}}.weights small{{display:block;line-height:1.6}}
    .grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.card{{min-width:0}}.heading{{display:flex;justify-content:space-between;gap:9px}}.heading strong{{font-size:1.15rem}}
    .heading small{{display:block;margin-top:4px;line-height:1.5;font-size:.76rem}}.ranking{{font-weight:800;color:#396da0}}.tag{{background:#eef1f5;color:#566270;border-radius:30px;padding:5px 8px;white-space:nowrap;font-size:.69rem;height:fit-content}}
    .tag.green{{background:#e1f5e9;color:#176a42}}.scoreline{{background:#eef5ff;margin:14px 0;padding:10px;border-radius:10px;display:flex;justify-content:space-between;align-items:center}}.scoreline b{{font-size:1.2rem}}
    .price{{font-size:1.65rem;font-weight:720;margin:12px 0}}.price small{{font-size:.8rem;font-weight:400}}.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:13px}}
    .metrics small{{display:block;font-size:.75rem}}.metrics b{{display:block;margin-top:3px}}.signal,.alert-line{{font-size:.86rem;border-top:1px solid #ecf0f5;margin:14px 0 0;padding-top:11px}}.alert-line{{color:#994b2b}}
    details.carddetail{{margin-top:12px}}summary{{cursor:pointer}}details.rest{{margin-top:16px}}details.rest>summary{{background:#e8ecf4;padding:14px;border-radius:10px;font-weight:680;margin-bottom:14px}}
    .note{{line-height:1.8;font-size:.9rem}}.warning{{background:#fff4d8;color:#8c560e;padding:11px;border-radius:10px}}
    .table-wrap{{padding:0;overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:.87rem}}th,td{{text-align:left;padding:13px;border-bottom:1px solid #edf0f5;vertical-align:top}}
    th{{background:#f3f6fb;white-space:nowrap}}td:nth-child(3){{white-space:nowrap}}a{{color:#225d9f}}
    .pos{{color:#137b4b;font-weight:750}}.neg{{color:#a43b3b;font-weight:750}}
    .movelist{{list-style:none;margin:10px 0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}}
    .moveitem{{border:1px solid #e0e6f0;border-radius:12px;background:#fff;padding:11px 13px;display:flex;justify-content:space-between;gap:10px;align-items:center}}
    .movename{{min-width:0}}.movename small{{display:block;font-size:.74rem;margin-top:3px}}
    .movetag{{border-radius:20px;padding:5px 9px;white-space:nowrap;font-size:.76rem;font-weight:700}}
    .movetag.up{{color:#176f4a;background:#e2f6ea}}.movetag.down{{color:#a64d36;background:#feede7}}.movetag.same{{color:#576476;background:#edf0f5}}
    @media(max-width:640px){{.movelist{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr}}.weights{{grid-template-columns:repeat(2,1fr)}}.stats strong{{font-size:1.3rem}}.stats>div{{padding:11px}}}}
    </style></head><body><main>
    <div class="eyebrow">STOCK RESEARCH LAB · 1.22</div><h1>📡 小G股票雷達</h1>
    <p class="muted">台股50＋美股50｜產業一句話、營收、獲利、技術排名及績效追蹤<br>台灣時間產生：{updated}。各股票請以卡片上的交易日為準。</p>
    <div class="stats"><div><small>成功掃描</small><strong>{len(records)}</strong></div><div><small>符合均線</small><strong>{sum(r['符合趨勢']=='是' for r in records)}</strong></div>
    <div><small>明顯放量</small><strong>{sum(str(r['量價訊號']).startswith('放量') for r in records)}</strong></div></div>
    <h2>四大引擎（目前開發狀態）</h2><div class="weights"><div><b>30%</b>技術分析<small>均線／量價／RSI動能：試驗評分已啟用</small></div>
    <div><b>30%</b>產業前景<small>建置中：加入官方資料跨期可比性觀察，30分評分尚未啟用</small></div>
    <div><b>25%</b>法人買賣<small>尚未接入</small></div><div><b>15%</b>國際新聞<small>尚未接入</small></div></div>
    {warning}
    {ranking_changes_section(records,history_rows)}
    <h2>🏊 績效游泳池（前十名追蹤）</h2>
    <div class="note"><b>做法：</b>從歷史 CSV 找出每個市場每個交易日「當時」的技術分數前十名，觀察之後 5／10／20 個交易日的調整收盤價變化，再和同期間 ETF 比較。<br>
    <b>重要：</b>這是紙上觀察，假設能在訊號日收盤價比較，不代表真實成交或策略可獲利。不同日觀察可能重疊、同一檔會重複出現；不含稅費、滑價和買賣限制，尚非嚴格回測。已成熟結果會寫回歷史 CSV；若早期日期已超出可下載行情範圍，可能無法補算。</div>
    {warning_bench}
    {performance_section('台股',signals,results,immature,missing)}
    {performance_section('美股',signals,results,immature,missing)}
    {industry_strength_section(records,history_frames,benchmark_frames)}
    {monthly_revenue_section(UNIVERSE, INDUSTRY, TW_NAMES)}
    {industry_lens_section(UNIVERSE, INDUSTRY, TW_NAMES, records)}
    {quarterly_profit_section(UNIVERSE, INDUSTRY, TW_NAMES)}
    {fundamental_crosscheck_section(UNIVERSE, INDUSTRY, TW_NAMES)}
    {industry_readiness_section(UNIVERSE, INDUSTRY)}
    {health_section(records,errors,history_rows,UNIVERSE,INDUSTRY)}
    <h2>🏭 產業觀察大廳</h2><p class="muted">依各群組在本測試池的平均技術分排序；不是資金流向、產業成長率或未來漲幅。</p>
    <h3>🇹🇼 台股產業群</h3>{sector_table(tw)}<h3>🇺🇸 美股產業群</h3>{sector_table(us)}
    <h2>⚠️ 風險研究提示</h2><p class="muted">由單日量價與技術指標產生，不代表即時警報、交易建議或異常事件的根本原因。</p>
    <div class="note">{'<ul>'+top_alerts+'</ul>' if alert_rows else '本次沒有觸發預設研究提示。'}
    {f'<p class="muted">本次共 {len(alert_rows)} 檔觸發，僅顯示前 12 檔；其餘可在股票卡片查看。</p>' if alert_rows else ''}</div>
    {market_section(tw,'🇹🇼 台股')}{market_section(us,'🇺🇸 美股')}
    <h2>📘 系統說明</h2><div class="note">技術分數最高30分：均線12、量價10、RSI／5日動能8。這些是實驗性規則，未完成足夠的歷史回測及樣本外驗證。<br>
    明顯放量＝當日量達到<strong>前20個交易日（不含當日）平均量的1.5倍</strong>；放量下跌也會提示。<br>
    產業分類是手工整理的研究群組，不是官方產業分類；某些企業跨多個領域。產業平均技術分較高，不代表該產業前景更好。<br>
    預定四大權重30／30／25／15未變，目前只有技術面提供分數；尚無產業前景、法人、新聞完整量化評分。<br>
    此網站使用調整後歷史價格，非保證即時；未連接券商，不下單。<br>
    <a href="data/history.csv">查看CSV歷史紀錄</a>（既有紀錄保留，新增欄位在舊日期可留空）。</div>
    </main></body></html>'''
    # Build in a temporary file. A broken add-on must not replace a good report.
    stage_file = ROOT / 'index.stage.html'
    stage_file.write_text(page,encoding='utf-8')
    add_industry_briefs(stage_file, UNIVERSE, INDUSTRY, records)
    install_mobile_tabs(stage_file)
    install_villa_hub(stage_file, records)
    install_famous_room(stage_file)
    install_stock_search(stage_file)
    install_sector_indices(stage_file)
    verify_site(stage_file, records)
    stage_file.replace(SITE_FILE)


def main():
    records,errors,histories=latest_snapshot()
    for err in errors:print('資料問題：',err)
    if len(records)<MIN_SUCCESS:
        raise RuntimeError(f'僅成功下載 {len(records)}/100 檔，低於安全門檻 {MIN_SUCCESS}，不覆寫舊網頁。')
    benchmark_frames={};benchmark_errors=[]
    for market,(ticker,_) in BENCHMARKS.items():
        try:
            f=yf.Ticker(ticker).history(period='6mo',auto_adjust=True)
            if f.empty or 'Close' not in f.columns:raise ValueError('無收盤價')
            benchmark_frames[market]=f
        except Exception as exc:
            benchmark_errors.append(f'{ticker}: {type(exc).__name__}: {str(exc)[:100]}')
    history_rows=persist(records)
    render(records,errors,history_rows,histories,benchmark_frames,benchmark_errors)
    # render() computes and archives any newly matured outcomes on the same dictionaries.
    save_history(history_rows)
    print(f'完成：{len(records)}/100 檔；升降榜、績效追蹤及原本功能已產生。')


if __name__=='__main__':
    main()

# Legacy weekly archive compatibility (features present; not the current version):
# STOCK RESEARCH LAB · 1.9
# STOCK RESEARCH LAB · 1.10

# STOCK RESEARCH LAB · 1.11

# STOCK RESEARCH LAB · 1.13
