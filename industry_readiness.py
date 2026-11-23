"""Industry-fundamentals data-readiness dashboard for Taiwan listed nonfinancial stocks.

Uses only previously archived TWSE monthly revenue and YTD quarterly income-statement
snapshots. Never assigns a production sector score, simulates old knowledge, or
turns price momentum into a fundamentals metric.
"""
from __future__ import annotations

import calendar
import csv
import html
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONTHLY = HERE / 'data' / 'monthly_revenue.csv'
QUARTERLY = HERE / 'data' / 'quarterly_profit.csv'


def _load(path):
    if not path.is_file():
        return []
    try:
        with path.open(encoding='utf-8-sig', newline='') as file:
            return list(csv.DictReader(file))
    except (OSError, UnicodeError, csv.Error):
        return []


def _num(value):
    try:
        v = float(str(value).replace(',', '').strip())
        return v if math.isfinite(v) and abs(v) < 1_000_000 else None
    except (ValueError, TypeError):
        return None


def _prev_month(value):
    try:
        y, m = map(int, value.split('-'))
        if not (2000 <= y <= 2100 and 1 <= m <= 12): return ''
        return f'{y-1:04d}-12' if m == 1 else f'{y:04d}-{m-1:02d}'
    except (ValueError, AttributeError):
        return ''


def _prior_year_quarter(value):
    try:
        y, q = value.split('Q', 1)
        if 2000 <= int(y) <= 2100 and q in ('1','2','3','4'):
            return f'{int(y)-1}Q{q}'
    except (ValueError, AttributeError):
        pass
    return ''


def compute_industry_readiness(universe, industry, monthly_rows, quarterly_rows):
    """Return unscored industry observations, with explicit comparability flags."""
    sectors = defaultdict(list)
    for ticker in universe.get('台股', []):
        if industry.get(ticker) not in ('金融', None):
            sectors[industry[ticker]].append(ticker.split('.')[0])
    eligible = {code for values in sectors.values() for code in values}
    m_index = {}
    q_index = {}
    for r in monthly_rows:
        code = r.get('公司代號', '')
        date = r.get('資料年月', '')
        if code in eligible and len(date) == 7 and date[4] == '-':
            m_index[(date, code)] = r
    for r in quarterly_rows:
        code = r.get('公司代號', '')
        date = r.get('季度', '')
        if code in eligible and len(date) == 6 and date[4] == 'Q':
            q_index[(date, code)] = r
    latest_m = max((m for m, _ in m_index), default='')
    latest_q = max((q for q, _ in q_index), default='')
    older_m = _prev_month(latest_m)
    older_q = _prior_year_quarter(latest_q)
    table = []
    for sector, codes in sectors.items():
        growth = {}             # yoy revenue in the latest captured month
        prev_growth = {}        # yoy revenue in the directly preceding month
        profit = {}             # YTD operating margin in latest quarter
        prev_profit = {}        # YTD operating margin in same quarter last year
        for code in codes:
            r = m_index.get((latest_m, code), {})
            p = m_index.get((older_m, code), {})
            q = q_index.get((latest_q, code), {})
            oldq = q_index.get((older_q, code), {})
            v = _num(r.get('年增率'))
            w = _num(p.get('年增率'))
            x = _num(q.get('累計營業利益率%'))
            y = _num(oldq.get('累計營業利益率%'))
            if v is not None: growth[code] = v
            if w is not None: prev_growth[code] = w
            if x is not None and -100 <= x <= 100: profit[code] = x
            if y is not None and -100 <= y <= 100: prev_profit[code] = y
        current_codes = sorted(set(growth) & set(profit))
        growth_pairs = sorted(set(growth) & set(prev_growth))
        profit_pairs = sorted(set(profit) & set(prev_profit))
        # Like-for-like comparisons use the same companies in both periods.
        growth_delta = (statistics.median(growth[c]-prev_growth[c] for c in growth_pairs)
                        if len(growth_pairs) >= 3 else None)
        profit_delta = (statistics.median(profit[c]-prev_profit[c] for c in profit_pairs)
                        if len(profit_pairs) >= 3 else None)
        if len(codes) < 3:
            status = '樣本少・不比較趨勢'
        elif len(current_codes) < 3:
            status = '最新資料不足'
        elif growth_delta is None or profit_delta is None:
            status = '待累積跨期資料'
        else:
            status = '跨期資料可比較'
        table.append({
            '產業': sector, '股票數': len(codes), '同時有數據': len(current_codes),
            '月營收年增中位數': statistics.median(growth.values()) if growth else None,
            '營業利益率中位數': statistics.median(profit.values()) if profit else None,
            '月營收年增變化pp': growth_delta,
            '去年同季累計營利率變化pp': profit_delta,
            '營收配對': len(growth_pairs), '獲利配對': len(profit_pairs),
            '狀態': status,
        })
    table.sort(key=lambda x:(x['狀態'] != '跨期資料可比較', -x['同時有數據'], x['產業']))
    return latest_m, older_m, latest_q, older_q, table


def industry_readiness_section(universe, industry):
    """Small self-contained HTML section; works with current 1.12 mobile TW tab."""
    monthly = _load(MONTHLY)
    quarterly = _load(QUARTERLY)
    month, old_month, quarter, old_quarter, results = compute_industry_readiness(
        universe, industry, monthly, quarterly)
    esc = lambda s: html.escape(str(s), quote=True)
    pct = lambda v: '—' if v is None else f'{v:+.1f}%'
    diff = lambda v: '—' if v is None else f'{v:+.1f} 百分點'
    intro = ('<h2>🧱 台股產業前景・評分地基 1.13</h2>'
             '<p class="muted">先驗證資料完整度與可比性，<b>不另編產業總分</b>。'
             '這裡只使用既有證交所月營收與一般業季報歸檔資料，金融股不混入一般業比較。'
             '月營收與累計獲利的所屬期間不同，不能視為同一月份損益。</p>')
    intro += ('<p class="muted">目前最新月份：<b>'+esc(month or '尚無')+'</b>'
              '（對照 '+esc(old_month or '尚無')+'）；最新季度：<b>'
              +esc(quarter or '尚無')+'</b>（對照去年同季 '+esc(old_quarter or '尚無')+'）。'
              '只顯示實際已存檔的月份、季度，沒有資料時以「—」呈現。</p>')
    if not results or not month or not quarter:
        return intro + '<p class="warning">資料不足，先保留原本雷達，待後續累積官方快照。</p>'
    items = []
    for r in results:
        items.append('<tr><td>'+esc(r['產業'])+'</td>'
                     '<td>'+str(r['同時有數據'])+'/'+str(r['股票數'])+'</td>'
                     '<td>'+pct(r['月營收年增中位數'])+'</td>'
                     '<td>'+pct(r['營業利益率中位數'])+'</td>'
                     '<td>'+diff(r['月營收年增變化pp'])+'</td>'
                     '<td>'+diff(r['去年同季累計營利率變化pp'])+'</td>'
                     '<td>'+esc(r['狀態'])+'</td></tr>')
    info = ('<p class="muted">「月營收年增變化」比較<strong>連續兩個月份</strong>、'
            '「營利率變化」比較<strong>今年與去年相同季度的年初至今累計營業利益率</strong>。'
            '兩個比較都使用相同公司的配對樣本，且配對檔數至少3檔才顯示差值；'
            '這些是研究觀察，不是因果解釋、股價預測或已驗證的選股分數。</p>')
    rubric = ('<details class="rest"><summary>資料完整度與比較限制</summary>'
              '<div class="note">只比較已存檔的兩個營運期間，'
              '營收年增的跨月變化與去年同季累計營利率的變化屬於不同資料。'
              '目前不把它們換算成產業分數；樣本不足時只顯示現有資料。'
              '金融業財報口徑與一般產業不同，已排除。</div></details>')
    return (intro + info + '<div class="table-wrap"><table><thead><tr><th>產業</th><th>資料覆蓋</th>'
            '<th>最新月營收年增</th><th>累計營利率</th><th>營收年增變化</th>'
            '<th>同季營利率變化</th><th>可比性</th></tr></thead><tbody>'
            + ''.join(items) + '</tbody></table></div>' + rubric
            + '<p class="muted">歷史資料只從實際開始保存時逐步累積；不會把今天才看到的財報'
              '誤稱為過去已經知道，亦不追溯填上未存檔快照。</p>')
