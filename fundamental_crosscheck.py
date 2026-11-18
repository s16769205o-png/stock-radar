"""Research-only TW listed-company monthly-revenue / YTD profitability cross-check.

Sources are already-captured TWSE official snapshots.  This module does not
backfill unseen filings, forecast returns, or calculate a 30-point score.
Monthly revenue YoY and quarter-to-date *cumulative* operating margin cover
DIFFERENT periods and must never be interpreted as same-period earnings.
"""
from __future__ import annotations

import csv
import html
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
MONTHLY = BASE / 'data' / 'monthly_revenue.csv'
QUARTERLY = BASE / 'data' / 'quarterly_profit.csv'


def read_rows(path):
    if not path.is_file():
        return [], '尚未保存'
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            return list(csv.DictReader(handle)), None
    except (OSError, UnicodeError, csv.Error) as exc:
        return [], f'{type(exc).__name__}：無法讀取'


def number(val):
    if val is None or isinstance(val, bool):
        return None
    raw = str(val).strip().replace(',', '').replace('%', '')
    if raw.lower() in ('', '-', '--', 'nan', 'n/a', 'null', '不適用'):
        return None
    try:
        out = float(raw)
        return out if math.isfinite(out) and abs(out) <= 100000 else None
    except (ValueError, TypeError):
        return None


def quality_group(yoy, margin):
    if yoy is None or margin is None:
        return None
    # A 100%+ operating margin can occur through unusual accounting effects.
    # Treat extreme values as a review issue, not as a positive classification.
    if abs(margin) > 100:
        return None
    if yoy > 0 and margin > 0:
        return '營收年增・營業獲利'
    if yoy > 0 and margin <= 0:
        return '營收年增・營業未獲利'
    if yoy <= 0 and margin > 0:
        return '營收未年增・仍有營業獲利'
    return '營收未年增・營業未獲利'


GROUPS = [
    '營收年增・營業獲利',
    '營收年增・營業未獲利',
    '營收未年增・仍有營業獲利',
    '營收未年增・營業未獲利',
]


def safe(s):
    return html.escape(str(s), quote=True)


def pct(x):
    return '—' if x is None else f'{x:+.1f}%'


def classify(rows_revenue, rows_profit, universe, industry, names):
    """Return a transparent, point-in-time *snapshot* comparison, not a score."""
    allowed = {s.split('.')[0]: s for s in universe.get('台股', [])
               if industry.get(s) != '金融'}
    latest_month = max((r.get('資料年月', '') for r in rows_revenue
                        if r.get('公司代號') in allowed and
                        re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', r.get('資料年月', ''))), default='')
    latest_quarter = max((r.get('季度', '') for r in rows_profit
                          if r.get('公司代號') in allowed and
                          re.fullmatch(r'20\d\dQ[1-4]', r.get('季度', ''))), default='')
    rev = {r['公司代號']: r for r in rows_revenue
           if r.get('資料年月') == latest_month and r.get('公司代號') in allowed}
    prof = {r['公司代號']: r for r in rows_profit
            if r.get('季度') == latest_quarter and r.get('公司代號') in allowed}

    out = []
    for code, symbol in allowed.items():
        sector = industry.get(symbol, '未分類')
        revrow = rev.get(code, {})
        profrow = prof.get(code, {})
        yoy = number(revrow.get('年增率'))
        margin = number(profrow.get('累計營業利益率%'))
        note = str(profrow.get('研究提醒', '')).strip()
        category = quality_group(yoy, margin)
        if margin is not None and abs(margin) > 100:
            note = ('；'.join(x for x in (note, '營業利益率異常，需人工核對') if x))
        if yoy is not None and abs(yoy) >= 100:
            note = ('；'.join(x for x in (note, '營收年增幅度大，留意去年基期') if x))
        out.append({'code': code, 'symbol': symbol,
                    'name': names.get(code, code), 'industry': sector,
                    'yoy': yoy, 'margin': margin,
                    'eps': number(profrow.get('累計每股盈餘元')),
                    'group': category, 'note': note})
    return latest_month, latest_quarter, out


def fundamental_crosscheck_section(universe, industry, names):
    """HTML for quick research questions; all inputs are stored local snapshots."""
    rev, rev_issue = read_rows(MONTHLY)
    prof, prof_issue = read_rows(QUARTERLY)
    month, quarter, records = classify(rev, prof, universe, industry, names)
    intro = (
        '<h2>🔬 基本面交叉驗證室・1.11</h2>'
        '<p class="muted">將<strong>最新已保存的上市公司月營收年增率</strong>，'
        '與<strong>最新已保存的一般業季度累計營業利益率</strong>放在一起看。'
        '兩個指標涵蓋<strong>不同期間</strong>，不能認為當月的營收就對應這筆累計獲利，'
        '也不能把它當成股價上漲的原因或買進訊號。'
        '金融股的財報架構不同，這版先排除；美股尚未接入。'
        '資料來源為已保存的證交所官方月營收與一般業綜合損益表快照。</p>'
    )
    info = (f'<p class="muted">月營收月份：<b>{safe(month or "尚無")}</b>；'
            f'季度獲利：<b>{safe(quarter or "尚無")}</b>（年初至今累計）。'
            f'非金融台股池：{len(records)} 檔。</p>')
    if not month or not quarter:
        msg = '；'.join(x for x in (rev_issue, prof_issue) if x)
        return (intro + info + '<p class="warning">資料不足，等官方快照正常累積後再交叉比較。'
                + safe(msg) + '</p>')

    both = [r for r in records if r['group']]
    counts = Counter(r['group'] for r in both)
    labels = (
        '<div class="table-wrap"><table><thead><tr><th>交叉觀察類型</th><th>符合檔數</th><th>觀察重點</th></tr></thead><tbody>'
        + ''.join(f'<tr><td>{safe(group)}</td><td>{counts[group]}</td><td>{hint}</td></tr>'
                  for group, hint in [
                     (GROUPS[0], '檢查成長持續性與獲利率是否改善'),
                     (GROUPS[1], '留意成本、費用、價格或產業週期'),
                     (GROUPS[2], '評估季節性、基期與獲利維持能力'),
                     (GROUPS[3], '留意營運壓力，仍需回原始財報核對')])
        + '</tbody></table></div>'
    )
    seen_ind = defaultdict(list)
    for r in both:
        seen_ind[r['industry']].append(r)
    ind_rows=[]
    for sector, group in sorted(seen_ind.items(), key=lambda v:(-len(v[1]),v[0])):
        count=sum(x['group']==GROUPS[0] for x in group)
        ind_rows.append(f'<tr><td>{safe(sector)}</td><td>{len(group)}</td><td>{count}/{len(group)}</td></tr>')
    industries = ('<h3>各產業：營收成長且營業獲利</h3>'
                  '<p class="muted">僅比較本研究池內同時有兩份有效數字的公司；'
                  '族群只有一兩家公司時，不代表整個產業。</p>'
                  '<div class="table-wrap"><table><thead><tr><th>產業群</th><th>可比較檔數</th><th>雙條件符合</th></tr></thead><tbody>'
                  + ''.join(ind_rows) + '</tbody></table></div>')
    sorted_records = sorted(
        records,
        key=lambda x: (GROUPS.index(x['group']) if x['group'] in GROUPS else 4,
                       -(x['yoy'] if x['yoy'] is not None else -999999), x['code']))
    rows=[]
    for r in sorted_records:
        eps='—' if r['eps'] is None else f'{r["eps"]:+.2f}'
        rows.append('<tr><td>'+safe(r['name'])+'</td><td>'+safe(r['industry'])+'</td>'
                    '<td>'+pct(r['yoy'])+'</td><td>'+pct(r['margin'])+'</td>'
                    '<td>'+eps+'</td><td>'+safe(r['group'] or '資料不足／異常')+'</td>'
                    '<td>'+safe(r['note'] or '—')+'</td></tr>')
    detail = ('<details class="rest"><summary>展開個股交叉檢查（'+str(len(records))+' 檔）</summary>'
              '<div class="table-wrap"><table><thead><tr><th>公司</th><th>產業群</th>'
              '<th>最新月營收年增</th><th>累計營業利益率</th><th>累計EPS</th><th>交叉觀察</th>'
              '<th>研究提醒</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></details>')
    count_line=(f'<p class="muted">符合有效交叉條件：<b>{len(both)}/{len(records)}</b> 檔。'
                '分類的「未年增」包含年增率為零或負值；「未獲利」包含利益率為零或負值。任一指標缺值或比率異常，便不強制歸類。</p>')
    caution = ('<p class="muted">注意：此處的「營收成長」是最新月營收對去年同月，不是季度營收成長；'
               '「營業獲利」是本年截至最新季度的<strong>累計</strong>營業利益率為正，不代表最近單季獲利。'
               '只為觀察，不增加獨立分數；四大權重仍為 30／30／25／15，'
               '產業前景完整30分尚未啟用。資料可能有公告延遲與修訂，請查證原始財報。</p>')
    return intro+info+count_line+labels+industries+detail+caution
