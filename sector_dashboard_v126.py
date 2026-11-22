"""Stock radar 1.26: one-page Taiwan industry evidence dashboard.

Research only. Combines dated, independently sourced observations without
promoting them to a 100-point score. Neither margins nor institutional flows
are future-return predictors; data gaps must remain visible.
"""
from __future__ import annotations

import csv
import html
import math
import statistics
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
REVENUE_FILE = BASE / 'data' / 'monthly_revenue.csv'
PROFIT_FILE = BASE / 'data' / 'quarterly_profit.csv'


def _esc(s):
    return html.escape(str(s), quote=True)


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(str(value).strip().replace(',', ''))
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _rows(path):
    try:
        with Path(path).open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))
    except (OSError, UnicodeError, ValueError, csv.Error):
        return []


def _stock_return(frame, asof, trading_days=20):
    """20 intervals ending on the same recorded day; not 20 calendar days."""
    if frame is None or getattr(frame, 'empty', True) or 'Close' not in frame:
        return None
    entries = []
    for timestamp, value in frame['Close'].items():
        try:
            day = timestamp.strftime('%Y-%m-%d')
        except AttributeError:
            day = str(timestamp)[:10]
        n = _num(value)
        if n is not None and n > 0:
            entries.append((day, n))
    dates = [i for i, (day, _) in enumerate(entries) if day == asof]
    if not dates or dates[-1] < trading_days:
        return None
    i = dates[-1]
    return 100.0 * (entries[i][1] / entries[i-trading_days][1] - 1)


def _as_index(rows, period_field, allowed, code_field='公司代號'):
    period = max((str(r.get(period_field,'')) for r in rows
                  if str(r.get(code_field,'')) in allowed and str(r.get(period_field,''))[:4].isdigit()), default='')
    index = {str(r.get(code_field,'')):r for r in rows
             if r.get(period_field) == period and str(r.get(code_field,'')) in allowed}
    return period, index


def _fmt(n, unit='%', digits=1):
    return '—' if n is None else f'{n:+.{digits}f}{unit}'


def _rate(values, label):
    good = sum(1 for v in values if v > 0)
    return '—' if not values else f'{good}/{len(values)} {label}'


def _direction(values, sample_total):
    # Only >=3 observations and >=75% group coverage can drive a summary.
    if sample_total < 3 or len(values) < 3 or len(values) / sample_total < .75:
        return None
    rate = sum(v > 0 for v in values) / len(values)
    return True if rate >= .60 else False if rate <= .40 else None


def analyze(universe, industry, records, histories, benchmarks, history_rows,
            revenue_rows=None, profit_rows=None):
    """Pure-ish evidence aggregation suitable for tests; no network access."""
    target = set(universe.get('台股', ()))
    codes = {sym.split('.')[0] for sym in target}
    revenues = _rows(REVENUE_FILE) if revenue_rows is None else revenue_rows
    profits = _rows(PROFIT_FILE) if profit_rows is None else profit_rows
    revenue_period, revenue = _as_index(revenues, '資料年月', codes)
    profit_period, profit = _as_index(profits, '季度', codes)
    candidates = [r for r in records if r.get('市場') == '台股' and r.get('股票') in target and r.get('交易日期')]
    asof = max((r['交易日期'] for r in candidates), default='')
    current = {r['股票']:r for r in candidates if r['交易日期'] == asof}
    institutional = {r.get('股票'):r for r in history_rows if r.get('市場') == '台股'
                     and r.get('交易日期') == asof and r.get('股票') in target}
    benchmark20 = _stock_return(benchmarks.get('台股'),asof) if asof else None
    groups = defaultdict(list)
    for sym in universe.get('台股', ()):
        groups[industry.get(sym,'未分類')].append(sym)

    answer = []
    for name, members in groups.items():
        prices, revenues_yoy, profits_pos, institutions = [], [], [], []
        # Financial firms don't share ordinary industrial operating margin definitions.
        for symbol in members:
            row = current.get(symbol)
            if row:
                result = _stock_return(histories.get(symbol),asof)
                if result is not None:
                    prices.append(result)
            code = symbol.split('.')[0]
            yoy = _num(revenue.get(code,{}).get('年增率'))
            if yoy is not None:
                revenues_yoy.append(yoy)
            if name != '金融':
                margin = _num(profit.get(code,{}).get('累計營業利益率%'))
                if margin is not None:
                    profits_pos.append(margin)
            ir = institutional.get(symbol, {})
            if ir.get('法人資料狀態') == '官方已核對':
                net = _num(ir.get('三大法人買賣超股數'))
                f = _num(ir.get('外資買賣超股數'))
                t = _num(ir.get('投信買賣超股數'))
                d = _num(ir.get('自營商買賣超股數'))
                if (all(n is not None and n.is_integer() for n in (net,f,t,d))
                        and f+t+d == net):
                    institutions.append(net)
        median_price = statistics.median(prices) if prices else None
        median_yoy = statistics.median(revenues_yoy) if revenues_yoy else None
        relative = median_price - benchmark20 if median_price is not None and benchmark20 is not None else None
        signals = [
            _direction(prices,len(members)),
            _direction(revenues_yoy,len(members)),
            _direction(profits_pos,len(members)) if name != '金融' else None,
            _direction(institutions,len(members)),
        ]
        known = [v for v in signals if v is not None]
        plus = known.count(True)
        if len(members) < 3:
            status = '樣本少'
        elif len(known) < 3:
            status = '資料不足／待觀察'
        elif plus == len(known):
            status = '多項方向偏正'
        elif plus == 0:
            status = '多項方向偏弱'
        else:
            status = '訊號分歧'
        # Distinguish company-breadth figures from industry index, absolute sizes,
        # and 20-day stock-price changes. No buy/hold/sell instructions.
        if (len(members) >= 3 and _direction(revenues_yoy,len(members)) is True
            and _direction(prices,len(members)) is False):
            insight = f'{name}：營收普遍年增，但股價近20個交易日多數下跌'
            priority = 0
        elif (len(members) >= 3 and _direction(revenues_yoy,len(members)) is True
              and name != '金融' and _direction(profits_pos,len(members)) is False):
            insight = f'{name}：營收普遍年增，但累計營業利益率仍多數未轉正'
            priority = 1
        elif status == '訊號分歧':
            insight = f'{name}：價格、營收、獲利或法人方向出現分歧'
            priority = 2
        elif status == '多項方向偏正':
            insight = f'{name}：本次多項觀察方向偏正，仍須留意基期與時間差'
            priority = 3
        else:
            insight = ''
            priority = 99
        answer.append({
            'group':name,'members':len(members), 'day':asof,
            'p_n':len(prices),'p_pos':sum(x>0 for x in prices),
            'price20':median_price,'relative20':relative,
            'r_n':len(revenues_yoy),'r_pos':sum(x>0 for x in revenues_yoy), 'revenue_yoy':median_yoy,
            'o_n':len(profits_pos),'o_pos':sum(x>0 for x in profits_pos),
            'i_n':len(institutions),'i_pos':sum(x>0 for x in institutions),
            'status':status,'insight':insight,'priority':priority,
            'signals_valid':len(known),
        })
    return {'trade_day':asof,'month':revenue_period,'quarter':profit_period,
            'benchmark20':benchmark20,'groups':answer}


def sector_dashboard_section(universe, industry, records, histories, benchmarks, history_rows):
    """Compact at-a-glance Taiwan dashboard; always survives gaps."""
    data = analyze(universe, industry, records, histories, benchmarks, history_rows)
    groups = sorted(data['groups'],key=lambda r:(r['priority'],r['group']))
    stories = [r['insight'] for r in groups if r['insight']][:3]
    if not stories:
        stories = ['目前各產業資料不足以形成可靠的跨面向觀察；請先核對缺漏與公告日期。']
    top = ''.join('<li>'+_esc(s)+'</li>' for s in stories)
    table = []
    for r in groups:
        n = r['members']
        rel = ('<small>對0050 '+_esc(_fmt(r['relative20'],'pp'))+'</small>') if r['relative20'] is not None else ''
        price = (_esc(_fmt(r['price20'])) + rel + '<small>'+_esc(f"{r['p_n']}/{n}檔")+'</small>') if r['p_n'] else '—'
        yoy = (_esc(_fmt(r['revenue_yoy']))+'<small>'+_esc(f"{r['r_pos']}/{r['r_n']}檔年增")+'</small>') if r['r_n'] else '—'
        profit = (_esc(f"{r['o_pos']}/{r['o_n']} 利益率為正") if r['o_n'] else '金融業不適用' if r['group']=='金融' else '—')
        money = (_esc(f"{r['i_pos']}/{r['i_n']} 合計買超") if r['i_n'] else '—')
        table.append('<tr><td><b>'+_esc(r['group'])+'</b><small>'+_esc(f'{n}檔研究池')+'</small></td>'
                     '<td>'+price+'</td><td>'+yoy+'</td><td>'+profit+'</td><td>'+money+'</td>'
                     '<td>'+_esc(r['status'])+'</td></tr>')
    return '''<h2>🇹🇼 台股｜產業交叉驗證總控台・1.26</h2>
    <p class="muted">將本雷達固定50檔台股依自訂族群彙整，<b>不是官方產業指數，也不是買賣評分</b>。
    當期股票價格、月營收、季度累計營業利益及三大法人並非同期數據；只能用來發現矛盾，不能證明因果。</p>
    <div class="industry-cross-v126" id="industry-cross-v126">
      <div class="cross-highlights"><strong>🔎 一眼看出值得研究的矛盾</strong><ul>''' + top + '''</ul></div>
      <p class="muted">資料基準：價格／法人 '''+_esc(data['trade_day'] or '待更新')+'''；月營收 '''+_esc(data['month'] or '待更新')+'''；季報 '''+_esc(data['quarter'] or '待更新')+'''。
      價格採最近20個交易日調整收盤價的<b>產業樣本中位數</b>，不是產業類指數；相對0050單位為百分點。</p>
      <details class="cross-more" open><summary>展開全產業交叉比較（可左右滑動）</summary>
      <div class="cross-scroll"><table><thead><tr>
      <th>研究族群</th><th>20日股價</th><th>月營收年增</th><th>累計營利率</th><th>法人當日</th><th>觀察狀態</th>
      </tr></thead><tbody>'''+''.join(table)+'''</tbody></table></div></details>
      <p class="muted">「多項方向偏正／偏弱」只描述本次資料中，多數公司的方向是否一致；
      至少3檔、各項覆蓋率達75%才納入方向判斷，缺資料不算零。小族群標註樣本少。
      法人欄是官方核對之<b>當日三大法人合計買賣超方向</b>，並非買賣超金額；
      盈利欄僅觀察累計營業利益率正負，<b>不是獲利增長</b>，金融業財報不同而排除。
      這不是完整回測，不能當成買進、賣出或風險已消除的判斷。</p>
    </div><style>
    .industry-cross-v126 .cross-highlights{background:#eef5fd;border:1px solid #d5e3f1;border-radius:14px;padding:14px 16px;line-height:1.65}
    .industry-cross-v126 .cross-highlights strong{color:#255b84}
    .industry-cross-v126 .cross-highlights ul{margin:8px 0 0;padding-left:20px}
    .industry-cross-v126 .cross-highlights li{margin:5px 0}
    .industry-cross-v126 .cross-more{margin-top:12px}
    .industry-cross-v126 .cross-more summary{background:#e6f1fc;border-radius:12px;padding:12px;cursor:pointer;font-weight:750;color:#245f8d}
    .industry-cross-v126 .cross-scroll{overflow-x:auto;max-width:100%;margin-top:10px;border:1px solid #dae4f1;border-radius:12px;background:#fff}
    .industry-cross-v126 table{border-collapse:collapse;width:100%;min-width:790px;font-size:.85rem}
    .industry-cross-v126 th,.industry-cross-v126 td{padding:10px 9px;border-bottom:1px solid #e7ebf1;text-align:left;vertical-align:top}
    .industry-cross-v126 th{background:#edf3fa;white-space:nowrap}
    .industry-cross-v126 td:first-child{position:sticky;left:0;background:white;z-index:1;min-width:110px}
    .industry-cross-v126 td small{display:block;color:#637486;font-size:.73rem;margin-top:3px;white-space:nowrap}
    </style>'''
