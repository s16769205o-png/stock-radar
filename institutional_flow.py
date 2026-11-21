"""v1.24 Taiwan TWSE T86 institutional net-trading observations.

Public-market research, not a 25-point production score. Every fetched day is
bound to its own official trading date. Historical values are never invented.
The existing history.csv stores source observations across scheduled runs;
no additional GitHub workflows or credentials are necessary.
"""
from __future__ import annotations

import html
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

BASE_URL = 'https://www.twse.com.tw/rwd/zh/fund/T86'
OFFICIAL_PAGE = 'https://www.twse.com.tw/fund/T86?date=&response=html'
COLUMNS = ('外資買賣超股數','投信買賣超股數','自營商買賣超股數','三大法人買賣超股數')
STATUS_COL = '法人資料狀態'
MAX_DAILY_QUERIES = 5


def _esc(v):
    return html.escape(str(v), quote=True)


def _canonical(name):
    v = re.sub(r'<[^>]*>', '', str(name))
    v = v.replace('（', '(').replace('）', ')').replace(' ', '').replace('\u3000', '')
    return v.replace('\n','').replace('\t','')


def _integer(value):
    if isinstance(value, bool) or value is None:
        return None
    v = str(value).strip().replace(',', '').replace('＋', '+').replace('－', '-').replace('−', '-').replace(' ', '')
    if not v or v in ('--', '—', 'N/A', 'null'):
        return None
    if v.startswith('(') and v.endswith(')'):
        v = '-' + v[1:-1]
    if not re.fullmatch(r'[+-]?\d+', v):
        return None
    result = int(v)
    return result if abs(result) < 10**15 else None


def _field(fields, candidates):
    names = [_canonical(s) for s in fields]
    for candidate in candidates:
        v = _canonical(candidate)
        if v in names:
            return names.index(v)
    return None


def parse_t86(payload, expected_day):
    """Strict, field-name-based parser; only returns verified net shares."""
    if not isinstance(payload, dict) or str(payload.get('stat', '')).upper() != 'OK':
        raise ValueError('官方當日資料尚未提供')
    reported = re.sub('[^0-9]', '', str(payload.get('date','')))
    if len(reported) == 7 and reported[:3].isdigit():
        reported = str(1911 + int(reported[:3])) + reported[3:]
    if reported and reported != expected_day.replace('-', ''):
        raise ValueError('官方資料日期與查詢日不同')
    datasets = []
    if isinstance(payload.get('tables'), list):
        datasets.extend(t for t in payload['tables'] if isinstance(t, dict))
    if isinstance(payload.get('fields'), list) and isinstance(payload.get('data'), list):
        datasets.append(payload)
    for i in range(1, 16):
        if isinstance(payload.get('fields'+str(i)), list) and isinstance(payload.get('data'+str(i)), list):
            datasets.append({'fields':payload['fields'+str(i)],'data':payload['data'+str(i)]})
    for table in datasets:
        fields = table.get('fields', [])
        code_i = _field(fields, ['證券代號'])
        foreign_i = _field(fields, [
            '外陸資買賣超股數(不含外資自營商)',
            '外資及陸資買賣超股數(不含外資自營商)',
            '外資及陸資買賣超股數(不含自營商)',
        ])
        trust_i = _field(fields, ['投信買賣超股數'])
        dealer_i = _field(fields, ['自營商買賣超股數'])
        dealer_own = _field(fields, ['自營商買賣超股數(自行買賣)'])
        dealer_hedge = _field(fields, ['自營商買賣超股數(避險)'])
        total_i = _field(fields, ['三大法人買賣超股數'])
        if any(v is None for v in (code_i,foreign_i,trust_i,total_i)):
            continue
        if dealer_i is None and (dealer_own is None or dealer_hedge is None):
            continue
        parsed = {}
        for row in table.get('data', []):
            if not isinstance(row, (list,tuple)) or len(row) <= max(i for i in (code_i,foreign_i,trust_i,total_i) if i is not None):
                continue
            code = re.sub(r'<[^>]+>', '', str(row[code_i])).strip()
            if not re.fullmatch(r'\d{4,6}', code):
                continue
            try:
                foreign = _integer(row[foreign_i])
                trust = _integer(row[trust_i])
                total = _integer(row[total_i])
                if dealer_i is not None:
                    dealer = _integer(row[dealer_i])
                else:
                    own = _integer(row[dealer_own]); hedge = _integer(row[dealer_hedge])
                    dealer = own + hedge if own is not None and hedge is not None else None
            except IndexError:
                continue
            if any(v is None for v in (foreign,trust,dealer,total)):
                continue
            if foreign + trust + dealer != total:
                continue
            parsed[code] = (foreign,trust,dealer,total)
        # A small/empty table is not reliable evidence that a listed stock was absent.
        if len(parsed) < 30:
            continue
        return parsed
    raise ValueError('官方欄位不符或買賣超合計校驗失敗')


def fetch_t86(day):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('交易日期格式錯誤')
    query = urllib.parse.urlencode({'response':'json','date':day.replace('-',''),'selectType':'ALLBUT0999'})
    request = urllib.request.Request(BASE_URL + '?' + query, headers={
        'User-Agent':'Mozilla/5.0 (compatible; stock-radar-v124/1.0; public research)',
        'Accept':'application/json,text/plain,*/*',
        'Referer':'https://www.twse.com.tw/',
    })
    with urllib.request.urlopen(request,timeout=9) as response:
        data = response.read(3_000_001)
    if len(data) > 3_000_000:
        raise ValueError('官方回覆內容過大')
    return parse_t86(json.loads(data.decode('utf-8-sig')),day)


def _valid_row(row):
    if row.get(STATUS_COL) != '官方已核對':
        return None
    vals = [_integer(row.get(col)) for col in COLUMNS]
    if any(v is None for v in vals) or sum(vals[:3]) != vals[3]:
        return None
    return vals


def _refresh(history_rows, universe):
    wanted = {symbol.split('.')[0] for symbol in universe.get('台股', [])}
    bydate = defaultdict(list)
    for r in history_rows:
        if r.get('市場') == '台股' and str(r.get('股票', '')).split('.')[0] in wanted:
            d = str(r.get('交易日期',''))
            try:
                dd = date.fromisoformat(d)
                if dd > datetime.now(ZoneInfo('Asia/Taipei')).date() or dd.weekday() >= 5:
                    continue
            except ValueError:
                continue
            bydate[d].append(r)
    if not bydate:
        return [], '', {}
    expected_days = sorted(bydate,reverse=True)[:20]
    # Already checked dates may have some official-unlisted securities: don't loop forever.
    missing_days = [d for d in expected_days if any(
        r.get(STATUS_COL) not in ('官方已核對','官方未列示') for r in bydate[d]
    )]
    errors = []
    # Newest days first; backfill in small batches so scheduled scans remain gentle.
    for d in missing_days[:MAX_DAILY_QUERIES]:
        try:
            dataset = fetch_t86(d)
            coverage = len(wanted.intersection(dataset))
            if coverage < 35:
                raise ValueError(f'官方股票池涵蓋不足：{coverage}/50')
            for r in bydate[d]:
                code = r.get('股票','').split('.')[0]
                values = dataset.get(code)
                if values is None:
                    r[STATUS_COL] = '官方未列示'
                    continue
                r.update({col:str(v) for col,v in zip(COLUMNS,values)})
                r[STATUS_COL] = '官方已核對'
        except Exception as exc:
            errors.append(f'{d}: {type(exc).__name__}（未把缺資料當零）')
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429):
                errors.append('官方網站限制此執行環境的自動下載，停止重試')
                break
        time.sleep(0.15)
    latest_day = expected_days[0]
    return expected_days, latest_day, {'errors':errors,'queried':len(missing_days[:MAX_DAILY_QUERIES])}


def _fmt_shares(shares):
    if shares is None:
        return '—'
    return f'{shares/1000:+,.2f} 張'


def _data_window(history_rows, ticker, asof, observed_days):
    # Only saved scan dates count as window candidates; missing date is NOT a zero.
    lookup = {(r.get('股票'),r.get('交易日期')):r for r in history_rows
              if r.get('市場')=='台股'}
    output = {}
    for horizon in (5,20):
        target = observed_days[:horizon]
        checked=[]
        for day in target:
            values = _valid_row(lookup.get((ticker,day), {}))
            if values is not None:
                checked.append(values)
        if len(target) != horizon or len(checked) != horizon:
            output[horizon] = (None,len(checked),horizon)
        else:
            output[horizon] = ([sum(v[i] for v in checked) for i in range(4)],horizon,horizon)
    return output


def institutional_section(universe, industry, history_rows, records):
    """Render one Taiwan-only section and enrich CSV rows in place."""
    observed_days, newest, diag = _refresh(history_rows, universe)
    result = [
        '<h2>🇹🇼 台股｜法人買賣超研究室・1.24</h2>',
        '<p class="muted">來源：<a target="_blank" rel="noopener noreferrer" href="'+OFFICIAL_PAGE+'">'
        '臺灣證券交易所三大法人買賣超日報（T86）</a>。上市股票，單位為股；'
        '展示時換算為張（1張＝1,000股）。外資採不含外資自營商口徑；'
        '三大法人合計逐筆校驗。<b>目前只是資金方向研究，法人25分評分尚未啟用。</b>'
        '買超不是未來漲價保證；自營商交易包含避險活動。</p>',
    ]
    if not newest:
        return ''.join(result)+'<p class="warning">目前沒有可對應的台股掃描日期，未提供買賣超推論。</p>'
    official = [(r.get('交易日期'),r) for r in history_rows if r.get('市場')=='台股'
                and r.get('交易日期') in observed_days and _valid_row(r) is not None]
    verified_days = sorted({d for d,_ in official},reverse=True)
    all_latest = [r for r in history_rows if r.get('市場')=='台股' and r.get('交易日期')==newest]
    matching = [r for r in all_latest if _valid_row(r) is not None]
    if diag.get('errors'):
        result.append('<p class="warning">部分日期官方資料暫時無法取得：'
                      +_esc('；'.join(diag['errors'][:3]))+'。保留原資料，不以零代替。</p>')
    result.append(f'<p class="muted">最新股票掃描交易日 <b>{_esc(newest)}</b>；'
                  f'同日法人資料已校驗 <b>{len(matching)}/{len(all_latest)}</b> 檔。'
                  f'歷史法人資料涵蓋 <b>{len(verified_days)}</b> 個已保存掃描交易日；'
                  '5／20 日累積需每個觀察日期都有有效資料，否則標示待累積。</p>')
    if not matching:
        result.append('<div class="warning">這個交易日沒有足夠的官方法人資料；'
                      '可能是交易所尚未公布或限制自動下載。'
                      '不顯示任何推測的買賣超。</div>')
        return ''.join(result)
    sorted_pos = sorted(matching,key=lambda r:_valid_row(r)[3],reverse=True)
    result.append('<div class="institutional-pair">')
    for label,items in (('當日法人合計買超較多',sorted_pos[:3]),
                        ('當日法人合計賣超較多',list(reversed(sorted_pos[-3:])))):
        result.append('<div class="institutional-mini"><strong>'+_esc(label)+'</strong>')
        for r in items:
            code=r['股票'].split('.')[0]
            name = r.get('中文名稱') or code
            result.append('<div><span>'+_esc(name)+'</span><b>'+_esc(_fmt_shares(_valid_row(r)[3]))+'</b></div>')
        result.append('</div>')
    result.append('</div><details class="institutional-details"><summary>展開台股法人買賣超（本次有資料股票）</summary>')
    result.append('<p class="muted">依合計買賣超張數排列，非全市場排行榜；公司規模不同，不能僅用張數比較法人偏好。'
                  '5／20 日為「最近保存的掃描交易日」之完整加總，缺任一天就顯示待累積，'
                  '不會把不完整資料假稱連續交易日。</p>')
    result.append('<div class="institutional-scroll"><table><thead><tr>'
                  '<th>股票</th><th>外資</th><th>投信</th><th>自營商</th><th>合計</th>'
                  '<th>最近保存5日合計</th><th>最近保存20日合計</th><th>資料日期</th>'
                  '</tr></thead><tbody>')
    for row in sorted_pos:
        sym = row['股票']
        values = _valid_row(row)
        window = _data_window(history_rows,sym,newest,observed_days)
        tail = []
        for length in (5,20):
            nums,count,required = window[length]
            tail.append(_fmt_shares(nums[3]) if nums is not None else f'待累積（{count}/{required} 日）')
        cells = [str(row.get('中文名稱') or sym.split('.')[0])+' ('+sym.split('.')[0]+')']
        cells += [_fmt_shares(n) for n in values]
        cells += tail+[newest]
        result.append('<tr>'+''.join('<td>'+_esc(v)+'</td>' for v in cells)+'</tr>')
    result.append('</tbody></table></div></details>')
    result.append('''<style>
    .institutional-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:13px 0}
    .institutional-mini{border:1px solid #dce6f0;border-radius:13px;padding:12px;background:#f6f9fe;min-width:0}
    .institutional-mini strong{display:block;font-size:.82rem;margin-bottom:9px;color:#35577c}
    .institutional-mini div{display:flex;gap:6px;justify-content:space-between;margin:7px 0;font-size:.85rem}
    .institutional-mini b{font-size:.86rem;color:#2c587e;white-space:nowrap}
    .institutional-details>summary{background:#e8f1fc;color:#265988;border-radius:10px;padding:12px;font-weight:700}
    .institutional-scroll{overflow-x:auto;max-width:100%;border:1px solid #dfe6f1;border-radius:12px;margin:10px 0}
    .institutional-scroll table{min-width:830px;width:100%;border-collapse:collapse;font-size:.83rem}
    .institutional-scroll td,.institutional-scroll th{padding:10px 8px;border-bottom:1px solid #e5eaf2;white-space:nowrap;text-align:right}
    .institutional-scroll td:first-child,.institutional-scroll th:first-child{text-align:left}
    .institutional-scroll th{background:#eef3fa}
    @media(max-width:550px){.institutional-pair{grid-template-columns:1fr}}
    </style>''')
    return ''.join(result)
