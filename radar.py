"""小G 股票雷達 1.4 — 中文名稱、技術排行、產業分組、研究警示。

固定台股與美股各 50 檔測試池；不連券商、不自動交易、不構成買賣建議。
此版本仍僅使用技術指標；產業前景/法人/新聞模型尚未接入。
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

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / 'data' / 'history.csv'
SITE_FILE = ROOT / 'index.html'
VOLUME_THRESHOLD = 1.5
MIN_SUCCESS = 70
BATCH_SIZE = 10

UNIVERSE = {
    '台股': [
        '2330.TW', '2454.TW', '2317.TW', '2308.TW', '2382.TW', '2303.TW', '2327.TW', '2357.TW', '2376.TW', '2377.TW',
        '2408.TW', '2409.TW', '2412.TW', '3008.TW', '3017.TW', '3034.TW', '3231.TW', '3443.TW', '3532.TW', '3661.TW',
        '3711.TW', '4938.TW', '4958.TW', '5269.TW', '1301.TW', '1303.TW', '1326.TW', '2002.TW', '1101.TW', '1102.TW',
        '1216.TW', '2207.TW', '2603.TW', '2609.TW', '2615.TW', '2610.TW', '2618.TW', '2634.TW', '1476.TW', '1519.TW',
        '1590.TW', '2881.TW', '2882.TW', '2884.TW', '2885.TW', '2886.TW', '2891.TW', '2892.TW', '5871.TW', '5880.TW',
    ],
    '美股': [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'AVGO', 'AMD', 'ORCL', 'CRM',
        'ADBE', 'PLTR', 'MU', 'INTC', 'AMAT', 'LRCX', 'KLAC', 'QCOM', 'TXN', 'ADI',
        'PANW', 'CRWD', 'NOW', 'ANET', 'UBER', 'TSLA', 'GM', 'CAT', 'DE', 'GE',
        'GEV', 'BA', 'LLY', 'UNH', 'JNJ', 'ABBV', 'MRK', 'PFE', 'JPM', 'BAC',
        'GS', 'V', 'MA', 'COST', 'WMT', 'KO', 'PG', 'XOM', 'CVX', 'NEE',
    ],
}

TW_NAMES = {
    '2330':'台積電', '2454':'聯發科', '2317':'鴻海', '2308':'台達電', '2382':'廣達',
    '2303':'聯電', '2327':'國巨', '2357':'華碩', '2376':'技嘉', '2377':'微星',
    '2408':'南亞科', '2409':'友達', '2412':'中華電', '3008':'大立光', '3017':'奇鋐',
    '3034':'聯詠', '3231':'緯創', '3443':'創意', '3532':'台勝科', '3661':'世芯-KY',
    '3711':'日月光投控', '4938':'和碩', '4958':'臻鼎-KY', '5269':'祥碩', '1301':'台塑',
    '1303':'南亞', '1326':'台化', '2002':'中鋼', '1101':'台泥', '1102':'亞泥',
    '1216':'統一', '2207':'和泰車', '2603':'長榮', '2609':'陽明', '2615':'萬海',
    '2610':'華航', '2618':'長榮航', '2634':'漢翔', '1476':'儒鴻', '1519':'華城',
    '1590':'亞德客-KY', '2881':'富邦金', '2882':'國泰金', '2884':'玉山金',
    '2885':'元大金', '2886':'兆豐金', '2891':'中信金', '2892':'第一金',
    '5871':'中租-KY', '5880':'合庫金',
}

# 手工維護的「研究用粗分類」，不是證交所或 GICS 官方產業分類。
# 此處各股票僅列一個主題類別，以利比較；部分公司橫跨多個業務。
INDUSTRY_GROUPS = {
    '台股': {
        '半導體': '2330 2454 2303 2408 3034 3443 3532 3661 3711 5269',
        '電腦／伺服器': '2317 2382 2357 2376 2377 3231 4938',
        '電力／散熱／電子零組件': '2308 2327 3017 4958',
        '面板／光學': '2409 3008',
        '電信': '2412',
        '塑化': '1301 1303 1326',
        '鋼鐵': '2002',
        '水泥': '1101 1102',
        '食品': '1216',
        '汽車': '2207',
        '海運': '2603 2609 2615',
        '航空／航太': '2610 2618 2634',
        '紡織': '1476',
        '重電／機械': '1519 1590',
        '金融': '2881 2882 2884 2885 2886 2891 2892 5871 5880',
    },
    '美股': {
        '半導體／設備': 'NVDA AVGO AMD MU INTC AMAT LRCX KLAC QCOM TXN ADI',
        '軟體／雲端／網路': 'AAPL MSFT GOOGL META ORCL CRM ADBE PLTR NOW ANET',
        '網路安全': 'PANW CRWD',
        '電商／平台': 'AMZN UBER',
        '汽車': 'TSLA GM',
        '工業／設備': 'CAT DE GE GEV BA',
        '醫療／製藥': 'LLY UNH JNJ ABBV MRK PFE',
        '金融／支付': 'JPM BAC GS V MA',
        '民生消費': 'COST WMT KO PG',
        '能源': 'XOM CVX',
        '公用事業': 'NEE',
    },
}

INDUSTRY = {}
for _market, _groups in INDUSTRY_GROUPS.items():
    for _group, _symbols in _groups.items():
        for _symbol in _symbols.split():
            _code = _symbol + '.TW' if _market == '台股' else _symbol
            if _code in INDUSTRY:
                raise ValueError(f'產業分類重複：{_code}')
            INDUSTRY[_code] = _group
for _market, _symbols in UNIVERSE.items():
    for _symbol in _symbols:
        if _symbol not in INDUSTRY:
            raise ValueError(f'股票缺少產業分類：{_symbol}')

FIELDS = [
    '交易日期','市場','股票','調整收盤價','MA20','MA60','成交量','量比',
    '單日漲跌幅','量價訊號','符合趨勢','中文名稱','RSI14','五日動能',
    '均線分數','量價分數','動能分數','技術分數','產業','研究警示',
]


def classify_volume_price(ratio: float | None, day_change: float) -> str:
    if ratio is None:
        return '量能資料不足'
    if ratio >= VOLUME_THRESHOLD:
        return '放量上漲' if day_change > 0 else '放量下跌' if day_change < 0 else '放量持平'
    return '一般量能・上漲' if day_change > 0 else '一般量能・下跌' if day_change < 0 else '一般量能・持平'


def rsi_14(closes: pd.Series) -> float:
    delta = closes.diff()
    up, down = delta.clip(lower=0), (-delta).clip(lower=0)
    gain = float(up.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1])
    loss = float(down.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1])
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1 + gain / loss)


def technique_points(price: float, ma20: float, ma60: float, ratio: float | None,
                     change: float, rsi: float, momentum5: float) -> tuple[int,int,int]:
    # 沿用 1.3 的試驗性規則，不臨時修改已建立的技術分數標準。
    if price > ma20 > ma60: trend = 12
    elif price > ma20 and price > ma60: trend = 8
    elif price > ma20 or price > ma60: trend = 4
    else: trend = 0
    if ratio is not None and ratio >= VOLUME_THRESHOLD:
        volume = 10 if change > 0 else 0 if change < 0 else 3
    else:
        volume = 5 if change > 0 else 2 if change < 0 else 3
    strength = 5 if 50 <= rsi <= 70 else 3 if 40 <= rsi < 50 or 70 < rsi <= 80 else 1
    momentum = strength + (3 if momentum5 > 0 else 0)
    return trend, volume, momentum


def research_alert(price: float, ma20: float, ma60: float, ratio: float | None,
                   change: float, rsi: float, momentum5: float) -> str:
    """研究提示不是交易警報，不預測漲跌，也不使用帳戶資料。"""
    alerts = []
    if ratio is not None and ratio >= VOLUME_THRESHOLD and change < 0:
        alerts.append('放量下跌')
    if price < ma20 and price < ma60:
        alerts.append('位於20/60日均線下')
    if rsi >= 80:
        alerts.append('RSI偏高')
    elif rsi <= 30:
        alerts.append('RSI偏低')
    if momentum5 <= -8:
        alerts.append('5日跌幅較大')
    return '、'.join(alerts)


def calculate(data: pd.DataFrame, market: str, code: str) -> dict:
    if data is None or data.empty or not {'Close','Volume'}.issubset(data.columns):
        raise ValueError('缺少收盤價或成交量')
    data = data.dropna(subset=['Close','Volume'])
    if len(data) < 61:
        raise ValueError('交易日資料不足 61 筆')
    closes = data['Close'].astype(float)
    volumes = data['Volume'].astype(float)
    price = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    ma20 = float(closes.iloc[-20:].mean())
    ma60 = float(closes.iloc[-60:].mean())
    avg_vol = float(volumes.iloc[-21:-1].mean())  # 排除訊號當日
    ratio = float(volumes.iloc[-1]) / avg_vol if avg_vol > 0 else None
    change = 100 * (price / previous - 1) if previous > 0 else 0.0
    rsi = rsi_14(closes)
    mom5 = 100 * (price / float(closes.iloc[-6]) - 1) if closes.iloc[-6] > 0 else 0.0
    trend, volume, momentum = technique_points(price, ma20, ma60, ratio, change, rsi, mom5)
    return {
        '交易日期':data.index[-1].strftime('%Y-%m-%d'), '市場':market, '股票':code,
        '調整收盤價':round(price,2), 'MA20':round(ma20,2), 'MA60':round(ma60,2),
        '成交量':int(volumes.iloc[-1]), '量比':round(ratio,2) if ratio is not None else '',
        '單日漲跌幅':round(change,2), '量價訊號':classify_volume_price(ratio,change),
        '符合趨勢':'是' if price > ma20 > ma60 else '否',
        '中文名稱':TW_NAMES.get(code.split('.')[0],'') if market=='台股' else '',
        'RSI14':round(rsi,1), '五日動能':round(mom5,2),
        '均線分數':trend, '量價分數':volume, '動能分數':momentum, '技術分數':trend+volume+momentum,
        '產業':INDUSTRY[code], '研究警示':research_alert(price,ma20,ma60,ratio,change,rsi,mom5),
    }


def get_bulk(codes: list[str]) -> pd.DataFrame:
    return yf.download(tickers=codes,period='6mo',interval='1d',group_by='ticker',
                       auto_adjust=True,progress=False,threads=True,timeout=25)


def frame_for(bulk: pd.DataFrame, code: str) -> pd.DataFrame:
    if isinstance(bulk.columns,pd.MultiIndex):
        if code in bulk.columns.get_level_values(0): return bulk[code].copy()
        if code in bulk.columns.get_level_values(1): return bulk.xs(code,axis=1,level=1).copy()
    raise ValueError('批次資料缺少此股票')


def latest_snapshot() -> tuple[list[dict],list[str]]:
    records,errors=[],[]
    for market,codes in UNIVERSE.items():
        for start in range(0,len(codes),BATCH_SIZE):
            chunk=codes[start:start+BATCH_SIZE]
            try: bulk=get_bulk(chunk)
            except Exception as exc:
                bulk=pd.DataFrame()
                print('批次資料問題：',type(exc).__name__,str(exc)[:90])
            for code in chunk:
                try:
                    try: row=calculate(frame_for(bulk,code),market,code)
                    except (ValueError,KeyError,TypeError):
                        row=calculate(yf.Ticker(code).history(period='6mo',auto_adjust=True),market,code)
                    records.append(row)
                    print(f'{code} {row["交易日期"]}：技術{row["技術分數"]}/30；{row["量價訊號"]}')
                except Exception as exc:
                    errors.append(f'{code}: {type(exc).__name__}: {str(exc)[:90]}')
            time.sleep(0.4)
    return records,errors


def persist(records: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True,exist_ok=True)
    merged={}
    if DATA_FILE.exists():
        with DATA_FILE.open('r',encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row.get('交易日期') and row.get('股票'):
                    merged[(row['交易日期'],row['股票'])]={field:row.get(field,'') for field in FIELDS}
    for row in records:
        merged[(row['交易日期'],row['股票'])]=row
    # 輸出完整新舊資料，原有日期不丟棄。舊資料缺少新欄位就留空。
    with DATA_FILE.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader()
        for key in sorted(merged): w.writerow(merged[key])


def rank(row: dict) -> tuple:
    return (-int(row['技術分數']), row['符合趨勢'] != '是',
            -float(row['量比'] or 0), row['股票'])


def show_name(row: dict) -> str:
    return row.get('中文名稱','') or row['股票']


def esc(value) -> str:
    return html.escape(str(value),quote=True)


def stock_card(row: dict, position: int) -> str:
    name=esc(show_name(row))
    score=int(row['技術分數'])
    signal=esc(row['量價訊號'])
    selected=row['符合趨勢']=='是'
    alert=row.get('研究警示','')
    ratio=f"{float(row['量比']):.2f} 倍" if row['量比'] != '' else '無資料'
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
    <p class="signal">量價訊號：<b>{signal}</b></p>{alert_line}
    <details class="carddetail"><summary>查看分數拆解</summary><p>均線 {row['均線分數']}/12 · 量價 {row['量價分數']}/10 · RSI／5日動能 {row['動能分數']}/8</p></details>
    </article>'''


def sector_table(rows: list[dict]) -> str:
    """Each industry is ranked within its own market and displays up to 3 examples."""
    by_sector=defaultdict(list)
    for row in rows: by_sector[row['產業']].append(row)
    items=[]
    for sector,members in by_sector.items():
        ordered=sorted(members,key=rank)
        mean_score=sum(int(m['技術分數']) for m in members)/len(members)
        top=', '.join(f"{show_name(v)}（{v['技術分數']}分）" for v in ordered[:3])
        items.append((mean_score,sector,len(members),top))
    items.sort(key=lambda v:(-v[0],v[1]))
    lines=''.join(f'<tr><td>{esc(sector)}</td><td>{size}</td><td>{mean_score:.1f}/30</td><td>{esc(top)}</td></tr>'
                  for mean_score,sector,size,top in items)
    return ('<div class="table-wrap"><table><thead><tr><th>產業群</th><th>檔數</th>'
            '<th>平均技術分</th><th>群內前三名</th></tr></thead><tbody>'+lines+'</tbody></table></div>')


def render(records: list[dict], errors: list[str]) -> None:
    updated=datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')
    tw=sorted([r for r in records if r['市場']=='台股'],key=rank)
    us=sorted([r for r in records if r['市場']=='美股'],key=rank)
    alert_rows=sorted((r for r in records if r['研究警示']),key=lambda r:(r['市場'],rank(r)))
    top_alerts=''.join(f'<li><b>{esc(show_name(r))}</b>（{esc(r["股票"])}）：{esc(r["研究警示"])}</li>' for r in alert_rows[:12])
    warning=f'<p class="warning">本次有 {len(errors)} 檔無法取得資料，請查看 Actions 日誌。</p>' if errors else ''

    def market_section(rows:list[dict],label:str)->str:
        primary=''.join(stock_card(r,i) for i,r in enumerate(rows[:10],1))
        rest=''.join(stock_card(r,i) for i,r in enumerate(rows[10:],11))
        return f'''<h2>{label}｜技術排名前10</h2><p class="muted">僅此固定測試池內的排名，非全市場名次。</p>
        <section class="grid">{primary}</section><details class="rest"><summary>展開其餘 {len(rows[10:])} 檔</summary><section class="grid">{rest}</section></details>'''

    page=f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>小G股票雷達 1.4</title><style>
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
    @media(max-width:640px){{.grid{{grid-template-columns:1fr}}.weights{{grid-template-columns:repeat(2,1fr)}}.stats strong{{font-size:1.3rem}}.stats>div{{padding:11px}}}}
    </style></head><body><main>
    <div class="eyebrow">STOCK RESEARCH LAB · 1.4</div><h1>📡 小G股票雷達</h1>
    <p class="muted">台股50＋美股50｜產業分組、技術排行、研究提示<br>台灣時間產生：{updated}。各股票請以卡片上的交易日為準。</p>
    <div class="stats"><div><small>成功掃描</small><strong>{len(records)}</strong></div><div><small>符合均線</small><strong>{sum(r['符合趨勢']=='是' for r in records)}</strong></div>
    <div><small>明顯放量</small><strong>{sum(str(r['量價訊號']).startswith('放量') for r in records)}</strong></div></div>
    <h2>四大引擎（目前開發狀態）</h2><div class="weights"><div><b>30%</b>技術分析<small>均線／量價／RSI動能：試驗評分已啟用</small></div>
    <div><b>30%</b>產業前景<small>尚未接入，只做手工產業分類</small></div>
    <div><b>25%</b>法人買賣<small>尚未接入</small></div><div><b>15%</b>國際新聞<small>尚未接入</small></div></div>
    {warning}
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
    SITE_FILE.write_text(page,encoding='utf-8')


def main() -> None:
    records,errors=latest_snapshot()
    for err in errors: print('資料問題：',err)
    if len(records)<MIN_SUCCESS:
        raise RuntimeError(f'僅成功下載 {len(records)}/100 檔，低於安全門檻 {MIN_SUCCESS}，不覆寫舊網頁。')
    persist(records)
    render(records,errors)
    print(f'完成：{len(records)}/100 檔；產業群與研究提示已產生。')


if __name__=='__main__':
    main()
