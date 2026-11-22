"""Stock radar 1.28: Taiwan stock anomaly evidence checklist.

Structural research, not causal attribution or investment advice. Dated price,
monthly revenue, YTD accounting and official institutional flow never become
one combined score. Missing source observations remain missing.
"""
from __future__ import annotations

import html
from collections import defaultdict

from sector_dashboard_v126 import _num, _rows, _as_index, _stock_return, REVENUE_FILE, PROFIT_FILE
from sector_treasure_v127 import research_rows, _verified_institution


def _esc(value):
    return html.escape(str(value), quote=True)


def _pct(value, unit='%'):
    return '—' if value is None else f'{value:+.1f}{unit}'


def _shares(value):
    return '—' if value is None else f'{value / 1000:+,.2f} 張'


def _period_last_year(quarter):
    if (len(quarter) == 6 and quarter[4] == 'Q' and quarter[5] in '1234'
            and quarter[:4].isdigit()):
        return str(int(quarter[:4])-1) + quarter[4:]
    return ''


def _official_5day(history_rows, symbol, trade_day):
    """Exact 5 most recent archived scan dates, never implied calendar continuity."""
    dates = sorted({str(r.get('交易日期', '')) for r in history_rows
                    if r.get('市場') == '台股' and r.get('交易日期')
                    and r['交易日期'] <= trade_day}, reverse=True)
    selected = dates[:5]
    if len(selected) < 5:
        return None, 0, len(selected)
    by_date = {r.get('交易日期'): r for r in history_rows
               if r.get('市場') == '台股' and r.get('股票') == symbol
               and r.get('交易日期') in selected}
    valid = [_verified_institution(by_date.get(d, {})) for d in selected]
    count = sum(v is not None for v in valid)
    if count != 5:
        return None, count, 5
    return sum(v[3] for v in valid), 5, 5


def diagnose(universe, industry, names, records, histories, benchmarks, history_rows,
             revenue_rows=None, profit_rows=None):
    base = research_rows(universe, industry, names, records, histories,
                         benchmarks, history_rows, revenue_rows, profit_rows)
    codes = {s.split('.')[0] for s in universe.get('台股', ())}
    monthly = _rows(REVENUE_FILE) if revenue_rows is None else revenue_rows
    quarterly = _rows(PROFIT_FILE) if profit_rows is None else profit_rows
    month, mr = _as_index(monthly, '資料年月', codes)
    quarter, qr = _as_index(quarterly, '季度', codes)
    prior_q = _period_last_year(quarter)
    prior_profit = {str(r.get('公司代號', '')): r for r in quarterly
                    if prior_q and r.get('季度') == prior_q
                    and str(r.get('公司代號','')) in codes}
    trade_day = base['day']
    bench20 = _stock_return(benchmarks.get('台股'), trade_day) if trade_day else None
    output = []
    for sector in base['groups']:
        stocks = []
        for stock in sector['stocks']:
            if not stock['signal']:
                continue  # v1.28 is the drill-down for v1.27 anomaly clues
            code = stock['code']
            price = stock['price']
            relative = price - bench20 if price is not None and bench20 is not None else None
            monthly_row = mr.get(code, {})
            accumulated_yoy = _num(monthly_row.get('累計年增率'))
            margin = stock['margin']
            comparison = (_num(prior_profit.get(code, {}).get('累計營業利益率%'))
                          if sector['group'] != '金融' else None)
            margin_delta = (margin-comparison if margin is not None and comparison is not None
                            and -100 <= comparison <= 100 else None)
            flow5, flow_valid, flow_expected = _official_5day(history_rows, stock['symbol'], trade_day)
            current_inst = stock['inst']
            # Report observed clues and specific follow-up checks, NEVER "reasons" or signals to buy.
            checklist = []
            if relative is None:
                checklist.append('缺少與0050同日的20交易日比較；先補齊價格基準')
            elif relative < -5:
                checklist.append('相對0050額外走弱：查公司公告、產業價格與市場估值變動')
            elif relative > 5:
                checklist.append('相對0050較抗跌：仍須檢查價格與營收是否同期間')
            else:
                checklist.append('與0050的20日漲跌差距不大：先檢查整體市場因素')
            if stock['yoy'] is not None and stock['yoy'] > 0:
                if accumulated_yoy is None:
                    checklist.append('單月營收年增，但累計營收比較缺資料：查基期與持續性')
                elif accumulated_yoy <= 0:
                    checklist.append('單月營收年增、累計年增未轉正：留意低基期與持續性')
                else:
                    checklist.append('單月與累計營收皆年增：仍要確認是否轉化為營業獲利')
            if sector['group'] == '金融':
                checklist.append('金融業不適用一般業營利率；需另看其專用財務指標')
            elif margin is None:
                checklist.append('尚缺有效季度累計營利率，先回查原始季報')
            elif margin <= 0:
                checklist.append('累計營業利益率未轉正：核對毛利、費用與業外損益')
            elif margin_delta is None:
                checklist.append('累計營利率為正，但缺去年同期資料，無法判斷是否改善')
            elif margin_delta < -2:
                checklist.append('累計營利率較去年同季下降：檢查成本與產品組合')
            if flow5 is None:
                checklist.append('最近5個存檔交易日的法人資料不足，不推定連續買賣方向')
            elif flow5 < 0:
                checklist.append('最近5個保存交易日法人合計賣超：再核對個別法人及公告')
            elif flow5 > 0:
                checklist.append('最近5個保存交易日法人合計買超：不等於股價將反彈')
            stocks.append({**stock, 'relative':relative, 'benchmark20':bench20,
                           'accumulated_yoy':accumulated_yoy,
                           'margin_delta':margin_delta, 'flow5':flow5,
                           'flow_valid':flow_valid, 'flow_expected':flow_expected,
                           'checklist':checklist})
        if stocks:
            output.append({'group':sector['group'], 'stocks':stocks,
                           'status':sector['status']})
    return {'day':trade_day,'month':month,'quarter':quarter,
            'prior_quarter':prior_q,'benchmark20':bench20,
            'groups':output,'count':sum(len(s['stocks']) for s in output)}


def diagnostics_section(universe, industry, names, records, histories, benchmarks, history_rows,
                        revenue_rows=None, profit_rows=None):
    data = diagnose(universe, industry, names, records, histories, benchmarks, history_rows,
                    revenue_rows, profit_rows)
    sector_sections = []
    for idx, group in enumerate(data['groups']):
        cards = []
        for s in group['stocks']:
            relative_note = ('個股相對0050的20日漲跌差距（百分點）'
                             if s['relative'] is not None else '0050比較資料不足')
            inst_day = _shares(s['inst'][3]) if s['inst'] is not None else '—'
            flow_5text = (_shares(s['flow5']) if s['flow5'] is not None
                          else f'待累積（{s["flow_valid"]}/{s["flow_expected"]}日）')
            margin_text = ('不適用' if group['group'] == '金融' else _pct(s['margin']))
            previous_note = ('不適用' if group['group'] == '金融' else _pct(s['margin_delta'], 'pp'))
            checks = ''.join('<li>'+_esc(t)+'</li>' for t in s['checklist'])
            cards.append('''<details class="diag-stock"><summary><span><b>'''+_esc(s['name'])+'''</b><small>'''+_esc(s['code'])+''' · '''+_esc('／'.join(s['clues']))+'''</small></span><span class="diag-angle">展開排查 ▾</span></summary>
                <div class="diag-body"><h4>① 市場對照</h4><div class="diag-grid">
                <div><small>個股20交易日</small><b>'''+_esc(_pct(s['price']))+'''</b></div>
                <div><small>0050 同期</small><b>'''+_esc(_pct(s['benchmark20']))+'''</b></div>
                <div><small>相對0050</small><b>'''+_esc(_pct(s['relative'], 'pp'))+'''</b></div></div>
                <p class="diag-help">'''+_esc(relative_note)+'''</p>
                <h4>② 營收持續性</h4><div class="diag-grid">
                <div><small>當月營收年增</small><b>'''+_esc(_pct(s['yoy']))+'''</b></div>
                <div><small>年初至今累計營收年增</small><b>'''+_esc(_pct(s['accumulated_yoy']))+'''</b></div></div>
                <h4>③ 獲利品質</h4><div class="diag-grid">
                <div><small>本年截至季末累計營利率</small><b>'''+_esc(margin_text)+'''</b></div>
                <div><small>對去年同季累計營利率變化</small><b>'''+_esc(previous_note)+'''</b></div></div>
                <h4>④ 法人方向</h4><div class="diag-grid">
                <div><small>當日三大法人合計</small><b>'''+_esc(inst_day)+'''</b></div>
                <div><small>最近保存且核對5個交易日合計</small><b>'''+_esc(flow_5text)+'''</b></div></div>
                <h4>下一步查證</h4><ul class="diag-checks">'''+checks+'''</ul>
                </div></details>''')
        sector_sections.append('''<details class="diag-sector"'''+(' open' if idx==0 else '')+'''><summary><b>'''+_esc(group['group'])+'''</b><small>'''+str(len(group['stocks']))+''' 檔待排查</small></summary><div class="diag-cards">'''+''.join(cards)+'''</div></details>''')
    empty = '<p class="muted">本次沒有同時符合1.27跨面向條件的股票，或資料尚未齊全。</p>' if not sector_sections else ''
    return '''<h2>🧭 台股｜異常原因排查室・1.28</h2>
      <p class="muted">接續1.27，只展開有跨面向線索的股票，依序核對「相對大盤、營收持續性、獲利品質、法人方向」。
      <b>這是可追查的證據清單，不是AI已查明股價漲跌原因</b>，也不提供買賣評分。</p>
      <div class="diagnostics-v128" id="diagnostics-v128"><p class="diag-dates">股價／法人 '''+_esc(data['day'] or '待更新')+'''｜月營收 '''+_esc(data['month'] or '待更新')+'''｜累計季報 '''+_esc(data['quarter'] or '待更新')+'''</p>
      <p class="diag-help">固定台股50檔研究池中，本次有 '''+str(data['count'])+''' 檔值得進一步排查。點產業，再點股票展開四項核對；尚無資料一律顯示「—」或待累積。</p>
      '''+''.join(sector_sections)+empty+'''
      <p class="diag-help">不同期間數據不能推定因果。營收年增 ≠ 淨利成長；本年累計營利率 ≠ 最近單季；法人5日是「最近已存檔的5個交易日」，若缺日或未核對就不合計，不代表完整連續5交易日。股價採調整後收盤價，基準0050同日比較；金融股不套一般業利潤率。</p>
      <p class="diag-help">官方資料原始入口：<a href="https://openapi.twse.com.tw/v1/opendata/t187ap05_L" target="_blank" rel="noopener noreferrer">證交所月營收</a>、<a href="https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci" target="_blank" rel="noopener noreferrer">一般業季報</a>、<a href="https://www.twse.com.tw/fund/T86?date=&amp;response=html" target="_blank" rel="noopener noreferrer">三大法人買賣超</a>。</p>
      </div><style>
      .diagnostics-v128{display:grid;gap:12px;max-width:100%}
      .diagnostics-v128 .diag-dates{font-size:.88rem;color:#3a5c79;font-weight:700;margin:0}
      .diagnostics-v128 .diag-help{color:#66788b;font-size:.82rem;line-height:1.7;margin:3px 0}
      .diagnostics-v128 .diag-sector,.diagnostics-v128 .diag-stock{border:1px solid #dbe5ef;border-radius:13px;min-width:0;background:white;overflow:hidden}
      .diagnostics-v128 .diag-sector>summary{background:#eef5fb;display:flex;justify-content:space-between;gap:12px;align-items:center;padding:13px 16px;font-weight:700}
      .diagnostics-v128 .diag-sector>summary small{font-size:.76rem;color:#607487}
      .diagnostics-v128 .diag-cards{display:grid;gap:9px;padding:10px}
      .diagnostics-v128 .diag-stock>summary{display:flex;justify-content:space-between;gap:8px;padding:13px;align-items:center;cursor:pointer}
      .diagnostics-v128 .diag-stock>summary span:first-child{display:grid;gap:4px;min-width:0}
      .diagnostics-v128 .diag-stock>summary b{color:#274c6a}
      .diagnostics-v128 .diag-stock>summary small{font-size:.73rem;color:#6a7a8d;line-height:1.5}
      .diagnostics-v128 .diag-angle{font-size:.75rem;color:#527395;white-space:nowrap}
      .diagnostics-v128 .diag-body{padding:0 14px 14px;border-top:1px solid #edf0f5}
      .diagnostics-v128 h4{font-size:.93rem;color:#244e70;margin:15px 0 8px}
      .diagnostics-v128 .diag-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
      .diagnostics-v128 .diag-grid>div{background:#f7f9fc;border-radius:9px;padding:10px;min-width:0}
      .diagnostics-v128 .diag-grid small{display:block;color:#607487;font-size:.73rem;margin-bottom:5px}
      .diagnostics-v128 .diag-grid b{display:block;font-size:1rem;color:#253f58;overflow-wrap:anywhere}
      .diagnostics-v128 .diag-checks{padding-left:19px;font-size:.85rem;line-height:1.7;margin:4px 0 0}
      .diagnostics-v128 .diag-checks li{margin:6px 0}
      @media(min-width:800px){.diagnostics-v128 .diag-cards{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}}
      </style>'''
