"""Public SEC Form 13F research room for Berkshire Hathaway (CIK 1067983).

Research only. Caches verified filing information tables; never fabricates holdings,
claims trading dates, reads browser private holdings, or changes trading scores.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'data' / 'berkshire_13f.json'
CIK = '0001067983'
SEC_COMPANY = f'https://www.sec.gov/edgar/browse/?CIK={CIK}&owner=exclude'
SEC_SUBMISSIONS = f'https://data.sec.gov/submissions/CIK{CIK}.json'
UA = 'soso-stock-radar/1.19 public 13F research github.com/s16769205o-png/stock-radar'
KNOWN = (
    {'period':'2026-09-30','filed':'2026-11-16','accession':'0001193125-26-463399', 'document':'60471.xml'},
    {'period':'2026-06-30','filed':'2026-08-14','accession':'0001193125-26-352200', 'document':'56757.xml'},
)


def _filing_url(accession):
    short = accession.replace('-', '')
    ext = '.htm' if accession == '0001193125-26-352200' else '.html'
    return f'https://www.sec.gov/Archives/edgar/data/1067983/{short}/{accession}-index{ext}'


def _request(url, size=3_000_000):
    if not (url.startswith('https://www.sec.gov/') or url.startswith('https://data.sec.gov/')):
        raise ValueError('Only SEC is allowed')
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': 'application/json,application/xml,text/xml,*/*',
        'Accept-Encoding': 'identity', 'Host': urllib.parse.urlparse(url).hostname,
    })
    with urllib.request.urlopen(req, timeout=14) as res:
        data = res.read(size + 1)
        if len(data) > size: raise ValueError('SEC response exceeds size limit')
        return data


def _local_tag(t):
    return t.rsplit('}', 1)[-1] if '}' in t else t


def _get_field(element, field):
    for n in element.iter():
        if _local_tag(n.tag).lower() == field.lower():
            return (n.text or '').strip()
    return ''


def _decimal(v):
    try:
        x = float(str(v).replace(',', ''))
        if x < 0 or not 0 <= x < 1e15: raise ValueError('invalid quantity')
        return x
    except (ValueError, TypeError):
        return None


def parse_information_table(payload):
    """SEC namespace-independent parser. Key by CUSIP/class/option, aggregate managers."""
    root = ET.fromstring(payload)
    holdings = defaultdict(lambda: {'name':'', 'cusip':'', 'class':'', 'option':'', 'shares':0, 'value':0})
    count = 0
    for el in root.iter():
        if _local_tag(el.tag).lower() != 'infotable': continue
        cusip = _get_field(el, 'cusip').strip().upper()
        name = _get_field(el, 'nameOfIssuer')
        secclass = _get_field(el, 'titleOfClass')
        option = _get_field(el, 'putCall')
        qty = _decimal(_get_field(el,'sshPrnamt'))
        value = _decimal(_get_field(el,'value'))
        unit = _get_field(el,'sshPrnamtType')
        if not re.fullmatch(r'[A-Z0-9]{9}', cusip) or not name or qty is None:
            continue
        # Shares only; exclude PRN units from direct share-change comparisons.
        if unit.upper() not in ('', 'SH'):
            continue
        key = f'{cusip}|{secclass.upper()}|{option.upper()}'
        item = holdings[key]
        item.update({'name':name[:110], 'cusip':cusip, 'class':secclass[:55], 'option':option[:8]})
        item['shares'] += qty
        if value is not None: item['value'] += value
        count += 1
    if len(holdings) < 8 or len(holdings) > 500 or count > 5000:
        raise ValueError('SEC information table unexpectedly incomplete')
    return {k:{**v, 'shares':round(v['shares'], 4), 'value':round(v['value'], 2)}
            for k,v in sorted(holdings.items())}


def _index_documents(accession):
    key=accession.replace('-','')
    url=f'https://www.sec.gov/Archives/edgar/data/1067983/{key}/index.json'
    data=json.loads(_request(url,1_000_000))
    return [x['name'] for x in data.get('directory',{}).get('item',[])
            if x.get('name','').lower().endswith('.xml')
            and 'primary_doc' not in x.get('name','').lower()
            and not x.get('name','').lower().startswith('filing')]


def _download_table(meta):
    accession=meta['accession']
    names=[]
    try:
        names=_index_documents(accession)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
        pass
    # Verified SEC filing-index document names are a safe fallback if index.json fails.
    if not names:
        for known in KNOWN:
            if known['accession']==accession: names=[known['document']]
    if not names:
        raise RuntimeError('Official SEC filing document index unavailable')
    parent=f'https://www.sec.gov/Archives/edgar/data/1067983/{accession.replace("-", "")}/'
    last_error=None
    for name in names[:12]:
        if not re.fullmatch(r'[\w.\-]+\.xml',name,re.I): continue
        try:
            rows=parse_information_table(_request(parent+name,3_000_000))
            return rows, parent+name
        except (ET.ParseError, ValueError, urllib.error.URLError, TimeoutError) as e:
            last_error=e
    raise RuntimeError('Cannot parse SEC information table: '+str(last_error)[:120])


def _recent_filings():
    payload=json.loads(_request(SEC_SUBMISSIONS,5_000_000))
    records=payload['filings']['recent']
    cols=('form','reportDate','filingDate','accessionNumber')
    n=min(len(records[c]) for c in cols)
    periods={}
    for i in range(n):
        # Amended filings can be partial; do not silently combine them.
        if records['form'][i]!='13F-HR': continue
        period=records['reportDate'][i]
        if not re.fullmatch(r'20\d\d-\d\d-\d\d',period): continue
        meta={'period':period,'filed':records['filingDate'][i],
              'accession':records['accessionNumber'][i]}
        if period not in periods or meta['filed']>periods[period]['filed']:
            periods[period]=meta
    picked=sorted(periods.values(),key=lambda x:x['period'],reverse=True)[:2]
    if len(picked)<2: raise ValueError('Fewer than two original 13F-HR filings')
    return picked


def _read_cache():
    try:
        d=json.loads(CACHE.read_text(encoding='utf-8'))
        if d.get('schema')==1 and isinstance(d.get('filings'),list): return d
    except (OSError,ValueError,UnicodeError): pass
    return {'schema':1,'updated_at':'','filings':[], 'last_error':''}


def update_cache(fetcher=None):
    old = _read_cache()
    fetched=[]
    try:
        if fetcher is not None:
            recent=fetcher()
        else:
            try: recent=_recent_filings()
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                print('SEC submissions unavailable; checking verified Q3/Q2 filing paths:', type(exc).__name__)
                recent=[dict(x) for x in KNOWN]
        # Only publish BOTH comparable periods together; never mix old/new quarters.
        for meta in recent:
            table, source=_download_table(meta)
            fetched.append({'period':meta['period'],'filed':meta['filed'],
                            'accession':meta['accession'],'source':source,
                            'index':_filing_url(meta['accession']),
                            'positions':table})
        if len(fetched)!=2: raise ValueError('Two complete official tables are required')
        state={'schema':1,'updated_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
               'filings':fetched,'last_error':''}
        CACHE.parent.mkdir(parents=True,exist_ok=True)
        CACHE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'SEC 13F success: {[(x["period"],len(x["positions"])) for x in fetched]}')
        return True
    except (Exception) as exc:
        # Fail closed with an empty/no-overwrite update. Old holdings remain as of their label.
        print(f'SEC 13F update unavailable: {type(exc).__name__}: {str(exc)[:170]}')
        return False


def _esc(x):return html.escape(str(x),quote=True)


def _short_qty(x):
    x=float(x)
    return f'{x/1e6:,.2f} 百萬股' if x>=1e6 else f'{x:,.0f} 股'


def _compare(current, previous):
    cur=current.get('positions',{})
    prev=previous.get('positions',{})
    results=[]
    for key in sorted(set(cur)|set(prev)):
        a=cur.get(key); b=prev.get(key)
        one=a or b
        sa=float(a['shares']) if a else 0.0
        sb=float(b['shares']) if b else 0.0
        if b is None: kind='new'; label='新增列示'
        elif a is None: kind='gone'; label='本季未列示'
        elif sa>sb+1e-7: kind='added';label='股數增加'
        elif sa<sb-1e-7: kind='reduced';label='股數減少'
        else: kind='same';label='股數未變'
        delta=(100*(sa/sb-1)) if (a and b and sb>0) else None
        results.append({'name':one.get('name',''),'class':one.get('class',''),
                        'cusip':one.get('cusip',''),'kind':kind,'label':label,
                        'shares':sa if a else None,'previous_shares':sb if b else None,
                        'change_percent':delta,'value':float(a.get('value',0)) if a else None})
    order={'new':0,'added':1,'reduced':2,'gone':3,'same':4}
    results.sort(key=lambda x:(order[x['kind']],-(abs(x['change_percent']) if x['change_percent'] is not None else 0),x['name']))
    return results


def _view_contents():
    data=_read_cache()
    filings=data.get('filings',[])
    label='SEC 官方原始 13F 申報'
    disclaimer=('資料為季末列示持股，通常於季末後 45 天內申報；不是即時交易、'
                '也不是巴菲特個人全部資產。未列示不等於已全部賣出，股數增減也不必然是買賣，'
                '可能有拆併股、公司行動或申報修正。僅比較原始 13F-HR，修正申報需另核對。')
    if len(filings)==2 and all(x.get('positions') for x in filings):
        latest,older=sorted(filings,key=lambda x:x['period'],reverse=True)
        if latest['period']==older['period']: raise ValueError('same SEC reporting periods')
        rows=_compare(latest,older)
        counts={k:sum(x['kind']==k for x in rows) for k in ['new','added','reduced','gone','same']}
        lines=[]
        for x in rows:
            change=f'{x["change_percent"]:+.1f}%' if x['change_percent'] is not None else '—'
            lines.append(
                '<tr data-change="'+x['kind']+'"><td><b>'+_esc(x['name'])+'</b>'
                '<small>'+_esc(x['class'])+' · CUSIP '+_esc(x['cusip'])+'</small></td>'
                '<td><span class="famous-mark '+x['kind']+'">'+_esc(x['label'])+'</span></td>'
                '<td>'+(_short_qty(x['shares']) if x['shares'] is not None else '—')+'</td>'
                '<td>'+(_short_qty(x['previous_shares']) if x['previous_shares'] is not None else '—')+'</td>'
                '<td>'+change+'</td></tr>'
            )
        metrics=(''.join(f'<div><small>{label}</small><b>{counts[k]}</b></div>' for k,label in
                  [('new','新增列示'),('added','股數增加'),('reduced','股數減少'),('gone','本季未列示'),('same','股數未變')]))
        contents=('''<div class="famous-stats">'''+metrics+'</div>'
                  '<p class="villa-muted">申報基準日：<b>'+_esc(latest['period'])+'</b> 與 <b>'+_esc(older['period'])+'</b>；'
                  '最新申報公開日：<b>'+_esc(latest['filed'])+'</b>；'
                  '取得官方資料紀錄：'+_esc(data.get('updated_at','')[:19] or '未知')+'。</p>'
                  '<div class="famous-buttons"><button type="button" data-kind="all" aria-pressed="true">全部 '+str(len(rows))+'</button>'
                  +''.join('<button type="button" data-kind="'+k+'" aria-pressed="false">'+_esc(n)+' '+str(counts[k])+'</button>' for k,n in [('new','新增'),('added','增加'),('reduced','減少'),('gone','未列示'),('same','未變')])
                  +'</div>'
                  '<div class="table-wrap famous-table"><table><thead><tr><th>證券</th><th>狀態</th><th>本季股數</th><th>上季股數</th><th>股數變化</th></tr></thead><tbody>'
                  +''.join(lines)+'</tbody></table></div>'
                  '<p class="villa-muted">官方原始資料：<a target="_blank" rel="noopener noreferrer" href="'+_esc(latest['index'])+'">最新季申報</a>・'
                  '<a target="_blank" rel="noopener noreferrer" href="'+_esc(older['index'])+'">前季申報</a>。'
                  '股數已按同一 CUSIP、股別和選擇權型態彙整；沒有把市值變化誤認為買賣。</p>')
    else:
        summary=('根據已查證的公開資訊，波克夏 2026 年第三季 13F 於 2026-11-16 公布，'
                 '上一季於 2026-08-14 公布。')
        contents=('<div class="villa-note"><b>官方持股明細尚未成功同步</b><p>'+_esc(summary)+'</p>'
                  '<p>這個網站需要先下載兩期 SEC information table 才能比較股數；'
                  '若 SEC 限制自動存取，會保留此提醒，不填入沒有驗證的持股資料。</p>'
                  '<a href="'+_filing_url(KNOWN[0]['accession'])+'" target="_blank" rel="noopener noreferrer">2026 Q3 官方申報</a> · '
                  '<a href="'+_filing_url(KNOWN[1]['accession'])+'" target="_blank" rel="noopener noreferrer">2026 Q2 官方申報</a></div>')
    return ('''<h2 class="villa-h1">🏦 名人持股觀察室・1.19</h2>
      <p class="villa-muted">第一位研究對象：<b>波克夏・海瑟威（Berkshire Hathaway）</b>。'''
      +_esc(disclaimer)+'</p>'+contents+
      '<p class="villa-muted">申報人：CIK '+CIK+'；<a href="'+SEC_COMPANY+'" target="_blank" rel="noopener noreferrer">SEC 申報查詢</a>。本頁僅供學習研究，不能用於跟單或推斷即時交易。</p>')


CSS=r"""
/* stock-radar-famous-1.19 */
.famous-stats {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin:12px 0}
.famous-stats>div {background:white;border:1px solid #e0e6f0;border-radius:11px;padding:11px 6px;text-align:center}
.famous-stats small {display:block;color:#617083;font-size:.7rem}
.famous-stats b {display:block;font-size:1.35rem;margin-top:4px;color:#28476b}
.famous-buttons {display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.famous-buttons button {border:1px solid #d5e3f3;background:#fff;border-radius:20px;padding:8px 12px;cursor:pointer;color:#275079;font:600 .83rem system-ui}
.famous-buttons button[aria-pressed="true"] {background:#dcecff;border-color:#538bb9;color:#194e87}
.famous-table {overflow-x:auto}
.famous-table table {min-width:670px}
.famous-table td:first-child small {display:block;color:#647589;margin-top:4px;font-size:.7rem}
.famous-mark {border-radius:16px;padding:4px 8px;background:#edf1f7;white-space:nowrap}
.famous-mark.new,.famous-mark.added {background:#e3f4e8;color:#237247}
.famous-mark.gone,.famous-mark.reduced {background:#fff0e9;color:#99512c}
@media(max-width:600px){.famous-stats{grid-template-columns:repeat(3,minmax(0,1fr));}}
"""
JS=r"""
(function(){
  'use strict';
  const panel=document.getElementById('panel-famous');
  if(!panel)return;
  panel.innerHTML=__CONTENT__;
  const plan=document.querySelector('[data-room="famous"]');
  if(plan){
    const status=plan.querySelector('.villa-card-label');
    const desc=plan.querySelector('small');
    if(status)status.textContent=__READY__?'季報比較已接入':'待同步 SEC 明細';
    if(desc)desc.textContent=__READY__?'SEC 13F 官方季度股數變化':'SEC 13F 季度比較，官方明細待同步';
  }
  const btns=Array.from(panel.querySelectorAll('button[data-kind]'));
  if(!btns.length)return;
  btns.forEach(b=>b.addEventListener('click',function(){
    const value=b.dataset.kind;
    btns.forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
    for(const tr of panel.querySelectorAll('tr[data-change]')){
      tr.hidden=value!=='all'&&tr.dataset.change!==value;
    }
  }));
})();
"""


def install_famous_room(path):
    """Enhance the already-generated 1.18 HTML without touching private watchlists."""
    path=Path(path)
    text=path.read_text(encoding='utf-8')
    if '/* stock-radar-famous-1.19 */' in text: return
    if text.count('</head>')!=1 or text.count('</body>')!=1:
        raise ValueError('Unexpected HTML structure')
    if '/* stock-radar-villa-1.18 */' not in text:
        raise ValueError('Stock Radar villa 1.18 must exist before celebrity room')
    content=_view_contents()
    script=JS.replace('__CONTENT__',json.dumps(content,ensure_ascii=False).replace('<',r'\u003c').replace('>',r'\u003e').replace('&',r'\u0026'))
    script=script.replace('__READY__',str(bool(_read_cache().get('filings'))).lower())
    text=text.replace('</head>','<style>'+CSS+'</style></head>',1)
    text=text.replace('</body>','<script>'+script+'</script></body>',1)
    path.write_text(text,encoding='utf-8')


if __name__=='__main__':
    if '--refresh' in sys.argv:
        # Official source may be rate-limited; keep existing known-good cache.
        update_cache()
    else:
        print(_view_contents()[:600])
