"""Mobile-friendly listed-Taiwan industry drill-down on recorded market snapshots.

Only compares existing published monthly revenue, cumulative YTD profitability
and current technical research. This does not assign industry scores or infer
that reported revenue growth caused a stock-price move.
"""
from __future__ import annotations

import csv
import html
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONTHLY = HERE / 'data' / 'monthly_revenue.csv'
QUARTERLY = HERE / 'data' / 'quarterly_profit.csv'


def _rows(path):
    try:
        with path.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeError, csv.Error, ValueError):
        return []


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    value = str(value).strip().replace(',', '').replace('%', '')
    if value.lower() in ('', '-', '--', 'nan', 'n/a', 'null', '不適用'):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _esc(x):
    return html.escape(str(x), quote=True)


def _pct(x):
    return '—' if x is None else f'{x:+.1f}%'


def _money_millions(amount_in_thousands):
    v = _number(amount_in_thousands)
    return '—' if v is None else f'{v/1000:,.0f}'


def _year_ago(amount_in_thousands, yoy):
    amount = _number(amount_in_thousands)
    if amount is None or yoy is None or amount < 0 or yoy <= -100:
        return None
    return amount / (1 + yoy / 100)


def _sector_records(universe, industry, names, records):
    symbols = universe.get('台股', [])
    groups = defaultdict(list)
    for sym in symbols:
        groups[industry.get(sym, '未分類')].append((sym, names.get(sym.split('.')[0], sym)))
    return groups


def build_industry_lens(universe, industry, names, records):
    """Return the HTML fragment. Missing historical data stays missing."""
    grouped = _sector_records(universe, industry, names, records)
    allowed = {sym.split('.')[0] for sym in universe.get('台股', [])}
    monthly_rows, quarterly_rows = _rows(MONTHLY), _rows(QUARTERLY)
    month = max((r.get('資料年月', '') for r in monthly_rows
                 if r.get('公司代號') in allowed and r.get('資料年月', '')[:4].isdigit()),
                default='')
    quarter = max((r.get('季度', '') for r in quarterly_rows
                   if r.get('公司代號') in allowed and r.get('季度', '')[:4].isdigit()),
                  default='')
    monthly = {r['公司代號']: r for r in monthly_rows
               if r.get('資料年月') == month and r.get('公司代號') in allowed}
    quarterly = {r['公司代號']: r for r in quarterly_rows
                 if r.get('季度') == quarter and r.get('公司代號') in allowed}
    technical = {r.get('股票'): r for r in records
                 if r.get('市場') == '台股' and r.get('股票')}
    rendered = []
    ordered = []
    for group, stock_pairs in grouped.items():
        yoy_values = [_number(monthly.get(sym.split('.')[0], {}).get('年增率')) for sym, _ in stock_pairs]
        yoy_values = [v for v in yoy_values if v is not None]
        median = statistics.median(yoy_values) if yoy_values else None
        ordered.append((group, stock_pairs, median, len(yoy_values)))

    ordered.sort(key=lambda g: (g[2] is None, -(g[2] or 0), g[0]))
    for idx, (group, members, median, coverage) in enumerate(ordered, 1):
        rows_html = []
        positive = 0
        for sym, company_name in members:
            code = sym.split('.')[0]
            mr = monthly.get(code, {})
            pr = quarterly.get(code, {})
            tr = technical.get(sym, {})
            yoy = _number(mr.get('年增率'))
            mom = _number(mr.get('月增率'))
            amt = _number(mr.get('月營收千元'))
            previous = _year_ago(amt, yoy)
            margin = _number(pr.get('累計營業利益率%'))
            score = _number(tr.get('技術分數'))
            positive += int(yoy is not None and yoy > 0)
            tips = []
            if yoy is not None and yoy >= 80:
                tips.append('年增幅大，留意去年基期')
            if yoy is not None and yoy > 0 and mom is not None and mom < 0:
                tips.append('年增但月減')
            if margin is not None and margin < 0:
                tips.append('累計營業利益率為負')
            if tr.get('研究警示'):
                tips.append(str(tr.get('研究警示')))
            trend = '均線符合' if tr.get('符合趨勢') == '是' else (
                '均線未符合' if tr.get('符合趨勢') == '否' else '行情暫缺')
            tech_text = (f'{int(score)}/30・{trend}' if score is not None else '—')
            # The source has rounded YoY numbers; historical revenue is only
            # mathematically estimated, not an independent official prior filing.
            rows_html.append(
                f'<tr><td><b>{_esc(company_name)}</b><small>{_esc(code)}</small></td>'
                f'<td>{_money_millions(amt)}</td><td>{_money_millions(previous)}</td>'
                f'<td>{_pct(yoy)}</td><td>{_pct(mom)}</td>'
                f'<td>{_pct(margin)}</td><td>{_esc(tech_text)}</td>'
                f'<td>{_esc("；".join(tips) if tips else "—")}</td></tr>'
            )
        status = (f'年增中位數 {_pct(median)}' if median is not None else '營收資料待補')
        title = (f'{_esc(group)}　<b>{_esc(status)}</b>　'
                 f'<small>{coverage}/{len(members)} 檔有資料</small>')
        rendered.append(
            f'<details class="lens-sector" data-lens-sector="{_esc(group)}" id="lens-sector-{idx}">'
            f'<summary>{title}</summary>'
            f'<p class="muted">本群 {len(members)} 檔；月營收年增為正 {positive}/{coverage} 檔'
            + ('；本群樣本少，不能代表整個產業。' if len(members)<3 else '。')
            + '</p>'
            '<div class="table-wrap"><table><thead><tr>'
            '<th>股票</th><th>本月營收（百萬元）</th><th>去年同月推估（百萬元）</th>'
            '<th>營收年增</th><th>營收月增</th><th>累計營業利益率</th>'
            '<th>最新技術分數</th><th>研究提醒</th>'
            '</tr></thead><tbody>'+''.join(rows_html)+'</tbody></table></div></details>'
        )
    css = """<style>
    details.lens-sector {background:#fff;border:1px solid #dce5f1;border-radius:13px;
      margin:10px 0;overflow:hidden;scroll-margin-top:110px;}
    details.lens-sector>summary {cursor:pointer;padding:15px 13px;line-height:1.6;
      list-style-position:inside;color:#263b55}
    details.lens-sector>summary b {color:#245e96}
    details.lens-sector>summary small {font-size:.79rem;color:#657389;margin-left:5px}
    details.lens-sector[open]>summary {background:#edf4ff}
    details.lens-sector>.muted {padding:0 14px}
    details.lens-sector table td:first-child small {display:block;font-size:.73rem;margin-top:2px}
    .lens-link {background:none;border:0;padding:2px 0;cursor:pointer;
      color:#225d9f;text-decoration:underline;text-underline-offset:3px;
      font:inherit;text-align:left;}
    .lens-link:focus-visible {outline:2px solid #245e96}
    </style>"""
    # Runs after mobile_tabs.py has moved the HTML into cloned tab panels.
    script = """<script>
    (function(){
      function connectLens(){
        const details=Array.from(document.querySelectorAll('details[data-lens-sector]'));
        if(!details.length) return;
        for(const table of document.querySelectorAll('table')){
          const head=table.querySelector('thead');
          if(!head || !head.textContent.includes('營收年增中位數')) continue;
          for(const tr of table.querySelectorAll('tbody tr')){
            const cell=tr.querySelector('td');
            if(!cell || cell.querySelector('.lens-link')) continue;
            const name=cell.textContent.trim();
            const target=details.find(n=>n.getAttribute('data-lens-sector')===name);
            if(!target) continue;
            const btn=document.createElement('button');
            btn.type='button';btn.className='lens-link';
            btn.textContent=name+' ⌄';
            btn.setAttribute('aria-label','展開'+name+'產業個股分析');
            btn.addEventListener('click',function(){
              target.open=true;
              target.scrollIntoView({behavior:'auto',block:'start'});
            });
            cell.textContent='';cell.appendChild(btn);
          }
        }
      }
      if(document.readyState==='loading'){
        document.addEventListener('DOMContentLoaded',connectLens,{once:true});
      }else{connectLens();}
    })();
    </script>"""
    intro = (
        '<h2>📊 台股月營收｜產業透視鏡・1.14</h2>'
        f'<p class="muted">月營收 <b>{_esc(month or "尚未保存")}</b>；'
        f'累計季報 <b>{_esc(quarter or "尚未保存")}</b>。'
        '點上方營收表的「產業名稱」，可直接打開這裡對應的公司；'
        '也可點以下產業展開。依本研究池的營收年增中位數排序，並非股價或獲利排名。</p>'
        '<p class="muted">「去年同月推估」＝當月營收 ÷（1＋申報年增率），'
        '因年增率經四捨五入，僅為近似值，不能代替去年原始公告。'
        '高年增可能與低基期有關，但光看一個月不能證明。'
        '季度累計利益率與月營收不同期間；技術評分是當次股價快照，'
        '三者不可當作同期的因果證據。金融業的累計營業利益率不適用一般業公式。</p>'
    )
    if not rendered:
        return intro + '<p class="warning">尚無股票分類資訊。</p>'
    return intro + css + ''.join(rendered) + script


# Stable integration entrypoint
industry_lens_section = build_industry_lens
