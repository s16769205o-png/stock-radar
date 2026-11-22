"""Stock Radar 1.27: mobile-first Taiwan sector-to-stock research explorer.

Uses only the existing fixed Taiwan stock universe and archived official evidence.
This is a dated research aid, not a recommendation or a 30/25-point score.
"""
from __future__ import annotations

from collections import defaultdict
import html

from sector_dashboard_v126 import analyze, _as_index, _num, _rows, _stock_return, REVENUE_FILE, PROFIT_FILE


def esc(value):
    return html.escape(str(value), quote=True)


def signed_pct(value):
    return '—' if value is None else f'{value:+.1f}%'


def shares(value):
    return '—' if value is None else f'{value / 1000:+,.2f} 張'


def _verified_institution(row):
    if row.get('法人資料狀態') != '官方已核對':
        return None
    cols = ('外資買賣超股數', '投信買賣超股數',
            '自營商買賣超股數', '三大法人買賣超股數')
    nums = [_num(row.get(col)) for col in cols]
    if any(n is None or not n.is_integer() for n in nums) or sum(nums[:3]) != nums[3]:
        return None
    return nums


def research_rows(universe, industry, names, records, histories, benchmarks, history_rows,
                  revenue_rows=None, profit_rows=None):
    """Build dated company evidence, matching the sector logic in v1.26."""
    sector_data = analyze(universe, industry, records, histories, benchmarks, history_rows,
                          revenue_rows, profit_rows)
    wanted = tuple(universe.get('台股', ()))
    codes = {symbol.split('.')[0] for symbol in wanted}
    monthly = _rows(REVENUE_FILE) if revenue_rows is None else revenue_rows
    quarterly = _rows(PROFIT_FILE) if profit_rows is None else profit_rows
    month, revenue = _as_index(monthly, '資料年月', codes)
    quarter, profit = _as_index(quarterly, '季度', codes)
    day = sector_data['trade_day']
    today = {r.get('股票'): r for r in records if r.get('市場') == '台股'
             and r.get('股票') in wanted and r.get('交易日期') == day}
    official = {r.get('股票'): r for r in history_rows if r.get('市場') == '台股'
                and r.get('股票') in wanted and r.get('交易日期') == day}
    by_sector = defaultdict(list)
    for symbol in wanted:
        code = symbol.split('.')[0]
        group = industry.get(symbol, '未分類')
        row = today.get(symbol)
        price = _stock_return(histories.get(symbol), day) if row is not None else None
        yoy = _num(revenue.get(code, {}).get('年增率'))
        margin = (_num(profit.get(code, {}).get('累計營業利益率%'))
                  if group != '金融' else None)
        if margin is not None and not -100 <= margin <= 100:
            margin = None
        inst = _verified_institution(official.get(symbol, {}))
        # A clue is not evidence that the stock is undervalued or will rebound.
        conflict_price = price is not None and price < 0 and yoy is not None and yoy > 0
        conflict_profit = (group != '金融' and yoy is not None and yoy > 0
                           and margin is not None and margin <= 0)
        clues = []
        if conflict_price:
            clues.append('營收年增、股價20日下跌')
        if conflict_profit:
            clues.append('營收年增、累計營利率未轉正')
        by_sector[group].append({
            'symbol': symbol, 'code': code, 'name': names.get(code) or (row or {}).get('中文名稱') or code,
            'price': price, 'yoy': yoy, 'margin': margin, 'inst': inst,
            'clues': clues, 'signal': conflict_price or conflict_profit,
        })
    sector_order = sorted(sector_data['groups'], key=lambda g: (g['priority'], g['group']))
    groups = []
    for group in sector_order:
        stocks = by_sector[group['group']]
        # Show research clues first, then the most negative price change.
        stocks.sort(key=lambda s: (not s['signal'],
                       s['price'] is None, s['price'] if s['price'] is not None else 0,
                       s['code']))
        groups.append({'group': group['group'], 'status': group['status'],
                       'stocks': stocks, 'clues': sum(s['signal'] for s in stocks)})
    return {'day': day, 'month': month, 'quarter': quarter,
            'groups': groups, 'total': len(wanted)}


def treasure_section(universe, industry, names, records, histories, benchmarks, history_rows,
                     revenue_rows=None, profit_rows=None):
    data = research_rows(universe, industry, names, records, histories, benchmarks,
                         history_rows, revenue_rows, profit_rows)
    sections = []
    for index, group in enumerate(data['groups']):
        cards = []
        for stock in group['stocks']:
            inst = stock['inst']
            clue = ('<div class="treasure-clue">🔍 '+esc('；'.join(stock['clues']))+'</div>'
                    if stock['clues'] else '')
            margin = ('金融業不適用' if group['group'] == '金融'
                      else signed_pct(stock['margin']))
            inst_cells = (f'<div><small>外資（當日）</small><b>{esc(shares(inst[0]))}</b></div>'
                          f'<div><small>投信（當日）</small><b>{esc(shares(inst[1]))}</b></div>'
                          f'<div><small>三大法人合計（當日）</small><b>{esc(shares(inst[3]))}</b></div>'
                          if inst else '<div class="treasure-noinst">當日法人：尚無官方核對資料</div>')
            cards.append(
                '<div class="treasure-stock"><div class="treasure-name"><strong>'
                +esc(stock['name'])+'</strong><small>'+esc(stock['code'])+'</small></div>'
                + clue +
                '<div class="treasure-grid">'
                f'<div><small>股價近20交易日</small><b>{esc(signed_pct(stock["price"]))}</b></div>'
                f'<div><small>月營收年增</small><b>{esc(signed_pct(stock["yoy"]))}</b></div>'
                f'<div><small>季度累計營利率</small><b>{esc(margin)}</b></div>'
                +inst_cells+'</div></div>')
        opener = ' open' if index == 0 else ''
        cue = f'{group["clues"]} 檔出現跨面向線索' if group['clues'] else '本次未標出跨面向線索'
        sections.append(
            '<details class="treasure-sector"'+opener+'><summary>'
            '<span class="treasure-heading"><b>'+esc(group['group'])+'</b>'
            '<small>'+esc(f'{len(group["stocks"])} 檔｜{cue}')+'</small></span>'
            '<span class="treasure-state">'+esc(group['status'])+'</span>'
            '</summary><div class="treasure-stockgrid">'+''.join(cards)+'</div></details>')
    return '''<h2>🔎 台股｜產業尋寶雷達・1.27</h2>
    <p class="muted">點開產業即可逐檔追查：誰的股價下跌、營收卻仍年增？
    每張卡片只使用目前固定的台股研究池，不涵蓋全市場；
    <b>線索不是買點、低估證明或推薦排名</b>。</p>
    <div class="treasure-v127" id="treasure-v127">
      <p class="treasure-dates">資料日期：股價及法人 '''+esc(data['day'] or '待更新')+'''｜
      月營收 '''+esc(data['month'] or '待更新')+'''｜季報 '''+esc(data['quarter'] or '待更新')+'''。</p>
      <p class="treasure-help">已按 1.26 的產業觀察順序排列；展開產業後，先看有跨面向線索的股票，
      再按近20交易日股價變動排列。點標題可收合。數字缺漏以「—」呈現，不補零。</p>
      '''+''.join(sections)+'''
      <p class="treasure-footnote">「股價近20交易日」是調整收盤價的20個交易日變化；
      「月營收年增」是最新已存檔月份對去年同月；
      「季度累計營利率」是當年度截至最新季度的累計營業利益率，不是獲利成長率；
      法人為核對無誤的<b>單一交易日</b>買賣超（單位：張）。
      四種數據時間範圍不同，不能推定因果，缺資料不是表現差；
      金融股的營利率不按一般企業口徑比較。這裡不提供產業30分或法人25分。</p>
    </div>
    <style>
      .treasure-v127{max-width:100%;display:grid;gap:12px}
      .treasure-v127 .treasure-dates{margin:0;color:#3a5875;font-size:.88rem;font-weight:650}
      .treasure-v127 .treasure-help,.treasure-v127 .treasure-footnote{color:#5d6c7a;font-size:.85rem;line-height:1.7;margin:0}
      .treasure-v127 .treasure-sector{background:#fff;border:1px solid #dce6f0;border-radius:15px;overflow:hidden;min-width:0}
      .treasure-v127 .treasure-sector>summary{list-style:none;display:flex;gap:10px;align-items:center;
        justify-content:space-between;padding:14px 14px 14px 16px;cursor:pointer;background:#f0f6fc}
      .treasure-v127 .treasure-sector>summary::-webkit-details-marker{display:none}
      .treasure-v127 .treasure-sector>summary:focus-visible{outline:3px solid #3e7ab6;outline-offset:-4px}
      .treasure-v127 .treasure-sector>summary:before{content:'▸';color:#366b9e;font-weight:900}
      .treasure-v127 .treasure-sector[open]>summary:before{content:'▾'}
      .treasure-v127 .treasure-heading{display:grid;gap:4px;flex:1;min-width:0}
      .treasure-v127 .treasure-heading b{font-size:1.03rem;color:#254c70}
      .treasure-v127 .treasure-heading small{font-size:.75rem;color:#5d7183}
      .treasure-v127 .treasure-state{font-size:.73rem;color:#4d6274;text-align:right;max-width:42%;line-height:1.45}
      .treasure-v127 .treasure-stockgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:12px}
      .treasure-v127 .treasure-stock{border:1px solid #e1e8f1;border-radius:12px;padding:13px;min-width:0}
      .treasure-v127 .treasure-name{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
      .treasure-v127 .treasure-name strong{font-size:1.05rem;color:#233c52}
      .treasure-v127 .treasure-name small{font-size:.79rem;color:#647487}
      .treasure-v127 .treasure-clue{font-size:.78rem;color:#7a5526;background:#fff7e9;border-radius:7px;
        padding:8px 9px;margin-top:9px;line-height:1.5}
      .treasure-v127 .treasure-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 8px;margin-top:12px}
      .treasure-v127 .treasure-grid>div{min-width:0}
      .treasure-v127 .treasure-grid small{display:block;font-size:.73rem;color:#607386;margin-bottom:4px}
      .treasure-v127 .treasure-grid b{display:block;font-size:.94rem;color:#263f56;overflow-wrap:anywhere}
      .treasure-v127 .treasure-noinst{grid-column:1/-1;font-size:.77rem;color:#767e89}
      @media(max-width:700px){.treasure-v127 .treasure-stockgrid{grid-template-columns:1fr}
        .treasure-v127 .treasure-state{font-size:.7rem;max-width:38%}}
    </style>'''
