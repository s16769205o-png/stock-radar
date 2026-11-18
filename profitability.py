"""TWSE latest listed-general-industry income statement observations.

All amounts are year-to-date cumulative thousands of NTD except EPS in NTD.
The public open-data feed is a snapshot, not point-in-time historical filing data.
Only observations actually captured from now on are archived.  No investment score.
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
from zoneinfo import ZoneInfo

SOURCE = 'https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci'
ARCHIVE = Path(__file__).resolve().parent / 'data' / 'quarterly_profit.csv'
COLUMNS = [
    '季度', '公司代號', '公司名稱', '出表日期', '首次擷取日期', '最近擷取日期',
    '累計營業收入千元', '累計營業毛利千元', '累計營業利益千元', '累計稅後淨利千元',
    '累計每股盈餘元', '累計毛利率%', '累計營業利益率%', '研究提醒', '來源',
]


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    s = str(value).strip().replace(',', '').replace('％', '').replace('%', '')
    if not s or s in ('-', '--', '不適用', 'N/A', 'null', 'nan'):
        return None
    try:
        n = float(s)
        return n if abs(n) < 1e17 and n == n else None
    except (ValueError, TypeError):
        return None


def _period(row):
    try:
        year = int(str(row.get('年度', '')).strip())
        quarter = int(str(row.get('季別', '')).strip())
        if year < 2000:
            year += 1911
        if not (2000 <= year <= datetime.now().year and 1 <= quarter <= 4):
            return None
        return f'{year}Q{quarter}'
    except (ValueError, TypeError):
        return None


def _statement_date(row):
    raw = str(row.get('出表日期', '')).strip().replace('-', '').replace('/', '')
    if not raw.isdigit() or len(raw) not in (6, 7, 8):
        return ''
    try:
        yy, mm, dd = int(raw[:-4]), int(raw[-4:-2]), int(raw[-2:])
        if yy < 1900:
            yy += 1911
        return datetime(yy, mm, dd).strftime('%Y-%m-%d')
    except ValueError:
        return ''


def _fetch_official():
    request = urllib.request.Request(
        SOURCE,
        headers={'User-Agent': 'StockRadarResearch/1.10 (public TWSE data)',
                 'Accept': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(12_000_001)
    if len(raw) > 12_000_000:
        raise ValueError('財報資料超過大小限制')
    rows = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise ValueError('官方財報回應格式不符')
    if not {'年度','季別','公司代號','營業收入'}.issubset(rows[0]):
        raise ValueError('官方財報欄位不符')
    return rows


def _normalize(rows, allowed):
    found = {}
    grabbed = datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d')
    for row in rows:
        code = str(row.get('公司代號','')).strip()
        if code not in allowed:
            continue
        quarter = _period(row)
        if not quarter:
            continue
        revenue = _num(row.get('營業收入'))
        gross = _num(row.get('營業毛利（毛損）淨額'))
        if gross is None:
            gross = _num(row.get('營業毛利（毛損）'))
        operating = _num(row.get('營業利益（損失）'))
        net = _num(row.get('本期淨利（淨損）'))
        eps = _num(row.get('基本每股盈餘（元）'))
        if revenue is None or revenue <= 0 or (gross is None and operating is None):
            continue
        gross_margin = 100 * gross / revenue if gross is not None else None
        operating_margin = 100 * operating / revenue if operating is not None else None
        note = []
        if operating is not None and operating <= 0 and net is not None and net > 0:
            note.append('營業未獲利、淨利為正：留意業外')
        if operating_margin is not None and operating_margin < 0:
            note.append('營業利益率為負')
        if operating_margin is not None and abs(operating_margin) > 100:
            note.append('利益率異常，需核對原始財報')
        found[(quarter,code)] = {
            '季度': quarter, '公司代號':code,
            '公司名稱': str(row.get('公司名稱','')).strip(),
            '出表日期': _statement_date(row),
            '首次擷取日期': grabbed, '最近擷取日期': grabbed,
            '累計營業收入千元': revenue,
            '累計營業毛利千元': '' if gross is None else gross,
            '累計營業利益千元': '' if operating is None else operating,
            '累計稅後淨利千元': '' if net is None else net,
            '累計每股盈餘元': '' if eps is None else eps,
            '累計毛利率%': '' if gross_margin is None else round(gross_margin,4),
            '累計營業利益率%': '' if operating_margin is None else round(operating_margin,4),
            '研究提醒': '；'.join(note), '來源': SOURCE,
        }
    return found


def _merge_archive(incoming):
    all_rows = {}
    if ARCHIVE.exists():
        with ARCHIVE.open(encoding='utf-8-sig', newline='') as file:
            for row in csv.DictReader(file):
                if row.get('季度') and row.get('公司代號'):
                    all_rows[(row['季度'],row['公司代號'])] = {
                        name: row.get(name,'') for name in COLUMNS
                    }
    for key, row in incoming.items():
        old = all_rows.get(key)
        if old and old.get('首次擷取日期'):
            row['首次擷取日期'] = old['首次擷取日期']
        all_rows[key] = row
    ARCHIVE.parent.mkdir(parents=True,exist_ok=True)
    with ARCHIVE.open('w',encoding='utf-8-sig',newline='') as file:
        w = csv.DictWriter(file,fieldnames=COLUMNS)
        w.writeheader()
        for key in sorted(all_rows):
            w.writerow(all_rows[key])
    return all_rows


def quarterly_profit_section(universe, industry, names):
    """Official listed-general-company snapshot; existing radar survives remote failures."""
    non_financial = [sym for sym in universe.get('台股',[])
                     if industry.get(sym) != '金融']
    eligible_codes = {sym.split('.')[0] for sym in non_financial}
    issue = None
    try:
        raw = _fetch_official()
        incoming = _normalize(raw,eligible_codes)
        snapshots = _merge_archive(incoming)
        if not incoming:
            issue = '本次官方快照沒有符合股票池的有效一般業財報，顯示已保存資料'
    except Exception as ex:
        issue = '官方財報下載或儲存遇到問題（'+type(ex).__name__+'），顯示已保存資料'
        try:
            snapshots = _merge_archive({})
        except Exception:
            snapshots = {}
    heading = (
        '<h2>🏗️ 獲利品質研究室・第二期：上市公司季報</h2>'
        '<p class="muted">資料來源：<a href="'+SOURCE+'">證交所官方一般業綜合損益表</a>。'
        '此處所有營業收入、毛利、營業利益、稅後淨利與 EPS 均為<b>本年度截至當季累計數</b>，'
        '利益率也依累計數計算；<b>不是單季數字</b>。來源的「出表日期」不一定是每家公司個別公告日期，'
        '不能把它當成歷史回測時的精確可知時間。'
        '金融業財報架構不同，暫不納入毛利率與營業利益率比較；美股未接入。</p>'
    )
    if not snapshots:
        return heading + '<p class="warning">尚無可用季度財報快照；原股票雷達繼續正常運作。</p>'
    latest = max(key[0] for key in snapshots)
    data = {code: rec for (period,code),rec in snapshots.items() if period == latest}
    grouped=defaultdict(list)
    expected=defaultdict(int)
    for sym in non_financial:
        name=industry.get(sym,'未分類')
        expected[name]+=1
        if sym.split('.')[0] in data:
            grouped[name].append(data[sym.split('.')[0]])
    def fmt(value):
        n=_num(value)
        return '—' if n is None else f'{n:+.1f}%'
    def mid(rows,field):
        arr=[_num(r.get(field)) for r in rows]
        arr=[n for n in arr if n is not None]
        return statistics.median(arr) if arr else None
    output=[]
    for group,total in expected.items():
        rows=grouped[group]
        gross=mid(rows,'累計毛利率%')
        op=mid(rows,'累計營業利益率%')
        op_valid=[_num(r.get('累計營業利益率%')) for r in rows]
        op_valid=[x for x in op_valid if x is not None]
        profitable=(100*sum(v>0 for v in op_valid)/len(op_valid)) if op_valid else None
        flag='樣本太少' if total < 3 else ('有公司缺報表' if len(rows)<total else '—')
        output.append((group,len(rows),total,gross,op,profitable,flag))
    output.sort(key=lambda x:(x[4] is None,-(x[4] if x[4] is not None else -9999),x[0]))
    trs=[]
    for group,n,total,gross,op,profitable,flag in output:
        trs.append('<tr><td>'+html.escape(group)+'</td><td>'+f'{n}/{total}'+'</td>'
                   '<td>'+fmt(gross)+'</td><td>'+fmt(op)+'</td>'
                   '<td>'+('—' if profitable is None else f'{profitable:.0f}%')+'</td>'
                   '<td>'+html.escape(flag)+'</td></tr>')
    companies=[]
    for code,rec in sorted(data.items(),key=lambda x:(-
                     (_num(x[1].get('累計營業利益率%')) if _num(x[1].get('累計營業利益率%')) is not None else -9999),x[0])):
        companies.append('<tr><td>'+html.escape(names.get(code,code))+'</td><td>'+code+'</td>'
                         '<td>'+fmt(rec.get('累計毛利率%'))+'</td><td>'+fmt(rec.get('累計營業利益率%'))+'</td>'
                         '<td>'+('—' if _num(rec.get('累計每股盈餘元')) is None else f"{_num(rec.get('累計每股盈餘元')):+.2f}")+'</td>'
                         '<td>'+html.escape(rec.get('研究提醒',''))+'</td></tr>')
    warning=('<p class="warning">'+html.escape(issue)+'</p>') if issue else ''
    return (
        heading+warning+'<p class="muted">目前展示 <b>'+html.escape(latest)+'</b> '
        f'（非網頁更新日），這個季度一般業資料涵蓋 {len(data)}/{len(eligible_codes)} 檔。'
        '各族群使用中位數，僅比較同季度與本研究股票池；跨季累計數不可直接當成單季成長。'
        '營業利益率與毛利率越高也不保證未來股價越高。</p>'
        '<div class="table-wrap"><table><thead><tr><th>產業群</th><th>檔數</th>'
        '<th>累計毛利率中位數</th><th>累計營利率中位數</th><th>營利率為正</th><th>提醒</th>'
        '</tr></thead><tbody>'+''.join(trs)+'</tbody></table></div>'
        '<details class="rest"><summary>查看上市一般業個股季報</summary><div class="table-wrap"><table>'
        '<thead><tr><th>公司</th><th>代碼</th><th>累計毛利率</th><th>累計營利率</th>'
        '<th>累計 EPS（元）</th><th>提醒</th></tr></thead><tbody>'+''.join(companies)+
        '</tbody></table></div></details>'
        '<p class="muted">快照存至 data/quarterly_profit.csv；可日後累積不同季度。'
        '本版不依這些資料編造產業30分，也不將最新財報回填到過去的交易訊號。</p>'
    )
