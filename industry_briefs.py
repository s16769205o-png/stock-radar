"""Short, evidence-led industry observations for Stock Radar 1.15.

Uses only existing TWSE archived monthly/quarterly snapshots and the current
scanner's technical rows. Does not infer causes, predict prices, backfill past
filings, or issue buy/sell recommendations. This is not the 30-point score.
"""
from __future__ import annotations

import csv
import html
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MONTHLY = ROOT / 'data' / 'monthly_revenue.csv'
QUARTERLY = ROOT / 'data' / 'quarterly_profit.csv'
MARKER = 'STOCK_RADAR_BRIEF_V115'


def _read(path):
    try:
        with path.open(newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeError, csv.Error, ValueError):
        return []


def _number(raw):
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(str(raw).strip().replace(',', '').replace('%', ''))
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def _snapshots(allowed):
    mr = _read(MONTHLY)
    pr = _read(QUARTERLY)
    months = [r['資料年月'] for r in mr if r.get('公司代號') in allowed
              and re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', r.get('資料年月',''))]
    quarters = [r['季度'] for r in pr if r.get('公司代號') in allowed
                and re.fullmatch(r'20\d\dQ[1-4]', r.get('季度',''))]
    month = max(months, default='')
    quarter = max(quarters, default='')
    monthly = {r['公司代號']:r for r in mr if r.get('公司代號') in allowed and
               r.get('資料年月') == month}
    quarterly = {r['公司代號']:r for r in pr if r.get('公司代號') in allowed and
                 r.get('季度') == quarter}
    return month, quarter, monthly, quarterly


def industry_brief_texts(universe, industry, records):
    """Compute one transparent summary per Taiwan industry, never a forecast."""
    groups = defaultdict(list)
    for symbol in universe.get('台股', []):
        groups[industry.get(symbol, '未分類')].append(symbol)
    allowed = {symbol.split('.')[0] for symbols in groups.values() for symbol in symbols}
    month, quarter, monthly, quarterly = _snapshots(allowed)
    scanned = {r.get('股票'):r for r in records
               if r.get('市場') == '台股' and r.get('股票')}
    outputs = {}
    for sector, members in groups.items():
        rev = [_number(monthly.get(symbol.split('.')[0], {}).get('年增率'))
               for symbol in members]
        rev = [v for v in rev if v is not None]
        valid_ops = [_number(quarterly.get(symbol.split('.')[0], {}).get('累計營業利益率%'))
                     for symbol in members]
        # A >100% operating margin may have an accounting explanation and
        # should not be counted as straightforwardly comparable.
        valid_ops = [v for v in valid_ops if v is not None and abs(v) <= 100]
        trend = [scanned.get(symbol,{}).get('符合趨勢')
                 for symbol in members]
        trend = [value for value in trend if value in ('是','否')]
        n = len(members)
        growth_count = sum(v > 0 for v in rev)
        not_profit_count = sum(v <= 0 for v in valid_ops)
        trend_count = sum(v == '是' for v in trend)
        if not rev:
            lead = '最新月營收年增資料尚不足，暫不能判斷這個族群的營收方向'
        else:
            yoy = statistics.median(rev)
            lead = (f'{month} 月營收年增中位數 {yoy:+.1f}%（{growth_count}/{len(rev)} 檔為正）')
        parts = [lead]
        if sector == '金融':
            parts.append('金融股不適用一般業的營業利益率比較')
        elif valid_ops:
            parts.append(f'{quarter} 累計營業利益率未轉正 {not_profit_count}/{len(valid_ops)} 檔')
        else:
            parts.append('累計營業利益率尚缺可比資料')
        if trend:
            parts.append(f'本次符合均線趨勢 {trend_count}/{len(trend)} 檔')
        else:
            parts.append('本次技術走勢資料不足')
        if not rev:
            takeaway = '營收資料不足，暫時不下結論'
        elif sector == '金融':
            takeaway = '金融業需另看適用的獲利與資產品質指標'
        elif growth_count == len(rev) and valid_ops and not_profit_count > 0 and trend and trend_count == 0:
            takeaway = '營收普遍年增，但部分公司累計營業仍未獲利，均線趨勢也尚未轉強'
        elif growth_count == len(rev) and valid_ops and not_profit_count > 0:
            takeaway = '營收普遍年增，但部分公司累計營業仍未獲利'
        elif growth_count == len(rev) and trend and trend_count == 0:
            takeaway = '營收普遍年增，但均線趨勢尚未同步轉強'
        elif growth_count == 0 and rev:
            takeaway = '營收年增普遍偏弱，需留意後續改善情況'
        else:
            takeaway = '各項數據方向未必一致，仍宜回到個股研究'
        sentence = '；'.join(parts) + '——' + takeaway + '。'
        cautions = []
        if n < 3:
            cautions.append('本群樣本少，不能代表整個產業')
        if 0 < len(rev) < n:
            cautions.append('月營收並未涵蓋本群全部公司')
        if sector != '金融' and len(valid_ops) < n:
            cautions.append('部分公司缺少可比的累計獲利資料')
        # Explain possible base effect as a verification question, not a diagnosis.
        if rev and statistics.median(rev) >= 50:
            cautions.append('年增幅較大，仍需核對去年基期')
        outputs[sector] = (sentence, '；'.join(cautions))
    return outputs


def add_industry_briefs(path, universe, industry, records):
    """Insert a one-sentence note into each already-built accordion in static HTML.

    Must run before install_mobile_tabs(), which copies existing detail nodes.
    The original HTML still works without JavaScript.
    """
    path = Path(path)
    page = path.read_text(encoding='utf-8')
    if MARKER in page:
        return
    if page.count('</head>') != 1:
        raise ValueError('Cannot find a unique HTML head')
    observations = industry_brief_texts(universe, industry, records)
    css = '''<style>/* STOCK_RADAR_BRIEF_V115 */
    .lens-brief{margin:12px 13px 16px;padding:13px 14px;background:#f1f6fd;
      color:#233a53;border-left:4px solid #477db8;border-radius:9px;line-height:1.7}
    .lens-brief strong{display:block;color:#184c7b;font-size:.93rem;margin-bottom:4px}
    .lens-brief p{margin:0;font-size:.91rem;overflow-wrap:anywhere}
    .lens-brief small{display:block;margin-top:5px;font-size:.78rem;color:#606f83}
    </style>'''
    page = page.replace('</head>',css+'</head>',1)
    pattern = re.compile(r'(<details\s+class="lens-sector"\s+data-lens-sector="([^"]+)"[^>]*>\s*<summary>.*?</summary>)', re.S)
    seen = set()
    def inject(match):
        sector = html.unescape(match.group(2))
        info = observations.get(sector)
        if not info:
            return match.group(1)
        sentence, caution = info
        seen.add(sector)
        note = ('<div class="lens-brief"><strong>💡 懶人一句話</strong><p>'+
                html.escape(sentence,quote=True)+'</p>'+
                ('<small>提醒：'+html.escape(caution,quote=True)+'</small>' if caution else '')+
                '</div>')
        return match.group(1)+note
    page, count = pattern.subn(inject, page)
    if not count or not seen:
        raise ValueError('Cannot find industry lens accordions; leaving report intact')
    path.write_text(page,encoding='utf-8')
    return count
