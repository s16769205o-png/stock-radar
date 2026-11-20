"""Stock Radar 1.21: official TWSE sector indices and US sector-ETF proxies.

Research-only, source-dated price changes, never conflates an industry index
with the radar's fixed stock sample or an ETF with its benchmark index.
Network failure is visible and never aborts the existing market report.
"""
from __future__ import annotations

import html
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
TWSE_URL = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
SOURCE_LINK = 'https://www.twse.com.tw/zh/trading/historical/mi-index.html'
ETF_INFO = {
    'XLK': '資訊科技', 'XLE': '能源', 'XLF': '金融',
    'XLI': '工業', 'XLV': '醫療保健', 'XLY': '非必需消費',
    'XLP': '民生必需消費', 'XLB': '原物料', 'XLU': '公用事業',
    'XLRE': '不動產', 'XLC': '通訊服務',
}


def _text(x):
    return html.escape(str(x), quote=True)


def _number(x):
    if x is None or isinstance(x, bool):
        return None
    cleaned = re.sub(r'<[^>]+>', '', str(x)).strip().replace(',', '').replace('%', '')
    if cleaned in ('', '-', '—', '--', 'N/A', 'null'):
        return None
    try:
        v = float(cleaned)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _format_pct(v):
    return '—' if v is None else f'{v:+.2f}%'


def _format_close(v):
    return '—' if v is None else f'{v:,.2f}'


def _iter_tables(doc):
    if not isinstance(doc, dict):
        return
    if isinstance(doc.get('tables'), list):
        for table in doc['tables']:
            if isinstance(table, dict):
                yield table
    if isinstance(doc.get('fields'), list) and isinstance(doc.get('data'), list):
        yield {'fields':doc['fields'], 'data':doc['data']}
    for i in range(1, 15):
        fields, data = doc.get(f'fields{i}'), doc.get(f'data{i}')
        if isinstance(fields, list) and isinstance(data, list):
            yield {'fields':fields, 'data':data}


def parse_twse_sector_indices(doc):
    """Accept both legacy data1/fields1 and contemporary tables envelopes."""
    if not isinstance(doc, dict) or str(doc.get('stat', '')).upper() != 'OK':
        return {}
    indices = {}
    for table in _iter_tables(doc):
        fields = [re.sub(r'<[^>]*>', '', str(v)).replace(' ', '') for v in table.get('fields', [])]
        name_i = next((i for i, f in enumerate(fields) if f == '指數'), None)
        close_i = next((i for i, f in enumerate(fields) if '收盤指數' in f), None)
        pct_i = next((i for i, f in enumerate(fields) if '漲跌百分比' in f), None)
        sign_i = next((i for i, f in enumerate(fields) if '漲跌(+/-)' in f or '漲跌（+/-）' in f), None)
        if name_i is None or close_i is None or pct_i is None:
            continue
        for row in table.get('data', []):
            if not isinstance(row, list) or len(row) <= max(name_i, close_i, pct_i):
                continue
            name = re.sub(r'<[^>]+>', '', str(row[name_i])).strip()
            # Price (not total-return, leveraged or inverted) sector classifications.
            if not name.endswith('類指數') or '槓桿' in name or '反向' in name:
                continue
            close, daily = _number(row[close_i]), _number(row[pct_i])
            if close is None or close <= 0 or daily is None or abs(daily) > 50:
                continue
            if sign_i is not None and sign_i < len(row):
                sign = str(row[sign_i]).strip()
                if '-' in sign or '－' in sign or '−' in sign or '▼' in sign:
                    daily = -abs(daily)
                elif '+' in sign or '＋' in sign or '▲' in sign:
                    daily = abs(daily)
            indices[name] = {'close':close, 'day_pct':daily}
    return indices


def _get_twse(day):
    params = urllib.parse.urlencode({'response':'json', 'date':day.strftime('%Y%m%d'), 'type':'IND'})
    req = urllib.request.Request(TWSE_URL+'?'+params, headers={
        'User-Agent':'Mozilla/5.0 (compatible; soso-stock-radar/1.21 public sector index research)',
        'Accept':'application/json,text/plain,*/*',
    })
    with urllib.request.urlopen(req, timeout=6) as response:
        payload = response.read(1_800_001)
    if len(payload) > 1_800_000:
        raise ValueError('TWSE response too large')
    return parse_twse_sector_indices(json.loads(payload.decode('utf-8-sig')))


def _nearest_twse(day, tries=4):
    # Holidays and unpublished trade dates can return 200 with a non-OK result.
    errors = []
    for n in range(tries):
        candidate = day - timedelta(days=n)
        if candidate.weekday() >= 5:
            continue
        try:
            rows = _get_twse(candidate)
            if len(rows) >= 6:
                return candidate.isoformat(), rows, ''
            errors.append('無有效指數表')
        except Exception as exc:
            errors.append(type(exc).__name__)
            # Cloud hosts sometimes receive 403; do not repeatedly hammer the endpoint.
            if getattr(exc, 'code', None) in (403, 429) or isinstance(exc, (TimeoutError, ConnectionError)):
                break
    return '', {}, (errors[-1] if errors else '尚未公布')


def fetch_twse():
    today = datetime.now(ZoneInfo('Asia/Taipei')).date()
    date, current, why = _nearest_twse(today, tries=6)
    if not current:
        return {'date':'','rows':[],'error':why or 'TWSE 暫不可用'}
    prior_date, past, _ = _nearest_twse(datetime.fromisoformat(date).date() - timedelta(days=7), tries=4)
    rows = []
    for name, value in current.items():
        old = past.get(name, {}).get('close')
        one_week = 100 * (value['close'] / old - 1) if old and old > 0 else None
        rows.append({'name':name, 'close':value['close'], 'day_pct':value['day_pct'], 'week_pct':one_week})
    return {'date':date,'prior':prior_date,'rows':rows, 'error':''}


def fetch_us_etfs():
    try:
        import yfinance as yf
        # ETFs are exchange-traded proxy prices, NOT the underlying index values.
        data = yf.download(
            tickers=list(ETF_INFO), period='2mo', interval='1d', group_by='ticker',
            auto_adjust=False, progress=False, threads=True, timeout=9
        )
        rows=[]
        for ticker, label in ETF_INFO.items():
            try:
                frame = data[ticker] if isinstance(data.columns, __import__('pandas').MultiIndex) else data
                if 'Close' not in frame.columns: continue
                closes = frame['Close'].dropna()
                closes = closes[closes > 0]
                if len(closes) < 2: continue
                vals = list(closes)
                now = float(vals[-1])
                # Match precise prior trading-day intervals, no fabricated dates.
                def pct(days):
                    if len(vals) <= days: return None
                    then = float(vals[-1-days])
                    return 100*(now/then - 1) if then > 0 else None
                rows.append({
                    'name':label, 'ticker':ticker, 'close':now,
                    'day_pct':pct(1), 'week_pct':pct(5), 'month_pct':pct(20),
                    'date':closes.index[-1].strftime('%Y-%m-%d'),
                })
            except (KeyError, TypeError, ValueError, IndexError, AttributeError):
                continue
        return {'rows':rows, 'error':'' if rows else 'ETF 行情未取得'}
    except Exception as exc:
        return {'rows':[], 'error':type(exc).__name__}


def _highlights(rows, key, names=3):
    valid=[r for r in rows if r.get(key) is not None]
    if not valid: return '<p class="sector-note">近期比較資料尚未取得。</p>'
    leaders=sorted(valid, key=lambda x:x[key],reverse=True)[:names]
    laggers=sorted(valid, key=lambda x:x[key])[:names]
    def render_set(label,items):
        return '<div class="sector-highlight"><small>'+_text(label)+'</small>'+''.join(
            '<div><span>'+_text(r['name'])+'</span><b>'+_format_pct(r[key])+'</b></div>' for r in items
        )+'</div>'
    leader_label = '相對較強（仍可能下跌）' if all(r[key] < 0 for r in leaders) else '相對較強（僅價格變化）'
    return '<div class="sector-highlights">'+render_set(leader_label,leaders)+render_set('相對較弱（僅價格變化）',laggers)+'</div>'


def _sector_table(rows, us=False):
    if us:
        headers=('類別 / ETF','市價 USD','1交易日','5交易日','20交易日')
    else:
        headers=('證交所產業指數','收盤點數','當日','約一週')
    body=[]
    for row in rows:
        cells=[_text(row['name']) + (f'<small>{_text(row["ticker"])}</small>' if us else ''),
               _format_close(row.get('close')), _format_pct(row.get('day_pct')),
               _format_pct(row.get('week_pct'))]
        if us: cells.append(_format_pct(row.get('month_pct')))
        body.append('<tr>'+''.join('<td>'+v+'</td>' for v in cells)+'</tr>')
    return '<div class="sector-scroll"><table><thead><tr>'+''.join(
        '<th>'+_text(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'


def render_sections(tw, us):
    source = ('<a href="'+TWSE_URL+'?response=html&amp;type=IND" '
              'target="_blank" rel="noopener noreferrer">證交所官方類股指數</a>')
    twrows = tw.get('rows',[])
    if twrows:
        date = tw['date']; prior=tw.get('prior','')
        twrows = sorted(twrows,key=lambda x:(x.get('week_pct') is None, -(x.get('week_pct') or 0), x['name']))
        twcontent = (_highlights(twrows,'week_pct' if prior else 'day_pct')+
                     '<details class="sector-detail"><summary>展開全部 '+str(len(twrows))+' 類指數</summary>'+
                     '<p class="sector-note">表格可以左右滑動查看。</p>'+_sector_table(twrows)+'</details>')
        priorinfo='；約一週比較基準 '+_text(prior) if prior else '；一週比較資料暫缺'
    else:
        twcontent='<p class="sector-unavailable">目前無法自動取得證交所產業指數（'+_text(tw.get('error') or '資料未公布')+'）。既有股票研究報告不受影響。</p>'
        date='尚未取得';priorinfo=''
    twsection=(
        '<section class="sector-index-section" id="sector-index-tw">'
        '<h2>🔭 產業指數觀景台｜台股</h2>'
        '<p class="sector-note">台灣證交所<b>官方產業分類「價格指數」</b>；統計日期 '+_text(date)+priorinfo+'。'
        '指數是上市市場類別表現，不等於我們固定 50 檔的研究群組；指數本身不能直接買賣。'+source+'。</p>'
        +twcontent+
        '<p class="sector-note">價格指數不含股息；「約一週」是與上週相近交易日的收盤點數相比，'
        '不是固定 5 個交易日。若行情源暫不可用，不會用預設數字補齊。</p></section>'
    )
    usrows=us.get('rows',[])
    if usrows:
        current_date=max(r['date'] for r in usrows)
        usrows=[r for r in usrows if r['date']==current_date]
        usrows=sorted(usrows,key=lambda x:(x.get('week_pct') is None, -(x.get('week_pct') or 0),x['name']))
        found={r.get('ticker') for r in usrows}
        unavailable=[ticker+'（'+label+'）' for ticker,label in ETF_INFO.items() if ticker not in found]
        coverage=('<p class="sector-note"><b>本次行情覆蓋 '+str(len(found))+'/'+str(len(ETF_INFO))+' 個產業 ETF。</b>'
                  +(' 暫缺：'+_text('、'.join(unavailable))+'。缺值不代表停止交易或股價下跌。' if unavailable else ' 全部板塊均有本交易日資料。')
                  +'</p>')
        uscontent=(
            coverage+_highlights(usrows, 'week_pct')+
            '<details class="sector-detail"><summary>展開全部 '+str(len(usrows))+' 個產業 ETF</summary>'+
            '<p class="sector-note">表格可以左右滑動查看。</p>'+_sector_table(usrows,us=True)+'</details>'
        )
    else:
        current_date='尚未取得'
        uscontent='<p class="sector-unavailable">本次行情覆蓋 0/'+str(len(ETF_INFO))+' 個產業 ETF。暫時無法取得產業 ETF 行情（'+_text(us.get('error') or '行情缺漏')+'）。原本報告仍可正常使用。</p>'
    ussection=(
        '<section class="sector-index-section" id="sector-index-us">'
        '<h2>🔭 產業指數觀景台｜美股</h2>'
        '<p class="sector-note">美股暫以 <b>SPDR 產業 ETF 市價</b> 代理觀察標普主要板塊，不是官方產業指數點數。'
        '最近交易日 '+_text(current_date)+'；5／20 日比較為真正的交易日間隔。'
        'ETF 可能與追蹤指數出現費用、配息與追蹤誤差，不等於指數本身。</p>'+
        uscontent+
        '<p class="sector-note">以上為未含現金股息的 ETF 價格漲跌，不代表含息總報酬；'
        '台股是價格指數、美股是 ETF 市價，兩者口徑不同，不宜直接當同一指標排行。</p></section>'
    )
    return twsection, ussection


CSS = r"""
/* stock-radar-sector-indices-1.21 */
.sector-index-section {margin:18px 0 24px;padding:16px;border-radius:16px;
 background:#fff;border:1px solid #dce6f1;box-shadow:0 1px 3px #d5dfef55;}
.sector-index-section h2 {margin:0 0 12px;color:#244367;font-size:1.25rem;}
.sector-index-section .sector-note {font-size:.87rem;color:#61748a;line-height:1.75;margin:8px 0 14px;}
.sector-highlights {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:16px 0;}
.sector-highlight {border:1px solid #e4eaf3;background:#f5f8fd;border-radius:12px;padding:12px;min-width:0;}
.sector-highlight>small {display:block;color:#60748a;font-weight:700;margin-bottom:10px;font-size:.78rem;}
.sector-highlight>div {display:flex;align-items:baseline;justify-content:space-between;gap:5px;
 font-size:.86rem;margin:9px 0;}
.sector-highlight b {font-size:.85rem;color:#29577d;white-space:nowrap;}
.sector-detail>summary {padding:12px 9px;border-radius:9px;color:#285c8d;background:#eaf2fd;font-weight:650;}
.sector-scroll {overflow-x:auto;margin-top:12px;border:1px solid #e0e7f0;border-radius:12px;}
.sector-scroll table {border-collapse:collapse;min-width:490px;width:100%;font-size:.82rem;}
.sector-scroll th {background:#eef3fa;text-align:right;font-weight:650;white-space:nowrap;}
.sector-scroll th:first-child,.sector-scroll td:first-child {text-align:left;}
.sector-scroll td,.sector-scroll th {padding:12px 9px;border-bottom:1px solid #e9eef5;}
.sector-scroll td:not(:first-child) {white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums;}
.sector-scroll td:first-child small {display:block;font-size:.76rem;color:#6c7b8d;margin-top:3px;}
.sector-unavailable {background:#fff5ec;border-left:3px solid #d3a06d;border-radius:6px;padding:14px;
 line-height:1.65;color:#77552d;}
@media(max-width:520px){.sector-highlights{grid-template-columns:1fr;}.sector-index-section{padding:14px;}}
"""
SCRIPT = r"""
(function(){
  'use strict';
  const sections=[['panel-tw',__TW_HTML__],['panel-us',__US_HTML__]];
  for(const [panelId, content] of sections){
    const panel=document.getElementById(panelId);
    if(!panel)continue;
    const host=document.createElement('div');
    host.innerHTML=content;
    const section=host.firstElementChild;
    if(section)panel.insertBefore(section,panel.firstChild);
  }
})();
"""


def install_sector_indices(path):
    """Enhance existing market panels without modifying holdings or source history."""
    path=Path(path)
    page=path.read_text(encoding='utf-8')
    if '/* stock-radar-sector-indices-1.21 */' in page:
        return
    if page.count('</head>') != 1 or page.count('</body>') != 1:
        raise ValueError('Stock Radar HTML structure invalid')
    if '/* stock-radar-villa-1.18 */' not in page:
        raise ValueError('Requires 1.18 villa tabs')
    try:
        tw=fetch_twse()
    except Exception as exc:
        tw={'rows':[],'error':type(exc).__name__}
    try:
        us=fetch_us_etfs()
    except Exception as exc:
        us={'rows':[],'error':type(exc).__name__}
    twhtml, ushtml=render_sections(tw,us)
    def safejs(data):
        return json.dumps(data, ensure_ascii=False).replace('<',r'\u003c').replace('>',r'\u003e').replace('&',r'\u0026')
    js=SCRIPT.replace('__TW_HTML__',safejs(twhtml)).replace('__US_HTML__',safejs(ushtml))
    page=page.replace('</head>','<style>'+CSS+'</style></head>',1)
    page=page.replace('</body>','<script>'+js+'</script></body>',1)
    path.write_text(page,encoding='utf-8')
