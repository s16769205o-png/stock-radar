"""Stock Radar 1.29 — forward-only, audited research-signal evidence archive.

No retroactive fundamental signals: a row enters this archive only when a run
first observes a qualifying divergence with dated market and disclosure data.
Future close-to-close comparisons are descriptive, not tradeable strategy P/L.
"""
from __future__ import annotations

import json
import html
import math
from datetime import date, datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from sector_treasure_v127 import research_rows
from trading_sessions import first_later_session, last_completed_session, session_after

ARCHIVE_FIELD = '研究訊號歷史v129'  # in the already-archived history.csv
HORIZONS = (5, 10, 20)
PROSPECTIVE_METHOD = 'next_session_close'
KINDS = (
    ('price_revenue', '營收年增／股價20日下跌'),
    ('revenue_margin', '營收年增／累計營利率未轉正'),
)
CORE = ('first_seen', 'price_day', 'symbol', 'name', 'sector', 'kind',
        'revenue_month', 'profit_quarter', 'price20_pct', 'revenue_yoy_pct',
        'margin_pct', 'stock_base', 'benchmark_base')
OUTCOME = tuple(f'{prefix}_{h}d' for h in HORIZONS for prefix in
                ('stock_return', 'benchmark_return', 'excess_return', 'mature_date'))
FIELDS = CORE + ('method', 'start_date') + OUTCOME


def _esc(value):
    return html.escape(str(value), quote=True)


def _num(value):
    try:
        if isinstance(value, bool) or value in (None, ''):
            return None
        v = float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def _prices(frame):
    """Date-indexed adjusted closes from the fetched history; no invented dates."""
    if frame is None or getattr(frame, 'empty', True) or 'Close' not in frame:
        return {}, []
    found = {}
    for stamp, value in frame['Close'].items():
        try:
            day = stamp.strftime('%Y-%m-%d')
        except AttributeError:
            day = str(stamp)[:10]
        v = _num(value)
        if v is not None and v > 0 and len(day) == 10:
            found[day] = v
    return found, sorted(found)


def _load(history_rows):
    """Read immutable first-seen evidence embedded in historic daily CSV rows."""
    events = []
    for source in history_rows:
        raw = source.get(ARCHIVE_FIELD, '')
        if not raw:
            continue
        try:
            decoded = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise RuntimeError('1.29 歷史欄位格式有誤：拒絕覆寫舊資料') from exc
        if not isinstance(decoded, list):
            raise RuntimeError('1.29 歷史欄位不是事件清單：拒絕覆寫舊資料')
        for value in decoded:
            if (not isinstance(value, dict) or
                value.get('price_day') != source.get('交易日期') or
                value.get('symbol') != source.get('股票') or
                value.get('kind') not in dict(KINDS)):
                raise RuntimeError('1.29 歷史欄位的股票／日期／類型錯誤：拒絕覆寫舊資料')
            events.append(value)
    keys = [(r['price_day'], r['symbol'], r['kind']) for r in events]
    if len(keys) != len(set(keys)):
        raise RuntimeError('1.29 歷史有重複事件：拒絕覆寫舊資料')
    return events


def _save(rows, history_rows):
    """Update the existing CSV row dictionaries; radar.save_history persists them.

    This avoids editing the GitHub scheduled workflow, which already commits
    and publishes data/history.csv after every scan.
    """
    source = {(r.get('交易日期'),r.get('股票')):r for r in history_rows
              if r.get('市場') == '台股'}
    grouped = {}
    for event in rows:
        key = (event['price_day'], event['symbol'])
        if key not in source:
            raise RuntimeError('1.29 歷史記錄缺少所屬交易日，拒絕遺失事件')
        grouped.setdefault(key, []).append(event)
    for key, group in grouped.items():
        previous = source[key].get(ARCHIVE_FIELD)
        if not previous or json.loads(previous) != group:
            source[key][ARCHIVE_FIELD] = json.dumps(group, ensure_ascii=False,
                                                   separators=(',', ':'), allow_nan=False)


def prospective_start(row):
    """Legacy events have no prospective method and remain descriptive archives."""
    if row.get('method') != PROSPECTIVE_METHOD:
        return None
    try:
        observed = datetime.fromisoformat(row['first_seen'])
        if observed.utcoffset() is None:
            return None
        expected = first_later_session('台股', observed)
        start = row.get('start_date')
        if start == expected and date.fromisoformat(row['price_day']) < date.fromisoformat(start):
            return start
    except (KeyError, ValueError, TypeError):
        return None
    return None


def _status(row, horizon, latest_day):
    start = prospective_start(row)
    if start is None:
        return 'legacy'
    end = session_after('台股', start, horizon)
    if (row.get(f'mature_date_{horizon}d') == end
            and all(_num(row.get(f'{field}_{horizon}d')) is not None
                    for field in ('stock_return', 'benchmark_return', 'excess_return'))):
        return 'matured'
    if latest_day and end > latest_day:
        return 'pending'
    return 'unavailable'


def record_and_measure(universe, industry, names, records, histories, benchmarks, history_rows,
                       now=None, archive_rows=None, research_data=None):
    """Deterministic entry point; tests can inject archive, time and evidence."""
    now = now or datetime.now(ZoneInfo('Asia/Taipei'))
    old = _load(history_rows) if archive_rows is None else [dict(row) for row in archive_rows]
    snapshot = (research_rows(universe, industry, names, records, histories,
                             benchmarks, history_rows) if research_data is None else research_data)
    bench_map, bench_dates = _prices(benchmarks.get('台股'))
    day = snapshot.get('day', '')
    by_symbol = {r.get('股票'): r for r in records
                 if r.get('市場') == '台股' and r.get('交易日期') == day}
    archive_keys = {(r['price_day'],r['symbol'],r['kind']) for r in old}
    positions = {d:i for i,d in enumerate(bench_dates)}
    expected = last_completed_session('台股', now)
    latest_day = bench_dates[-1] if bench_dates and bench_dates[-1] <= expected else ''
    can_capture = bool(day == expected == latest_day and by_symbol
                       and set(by_symbol) == set(universe.get('台股', ()))
                       and snapshot.get('month') and snapshot.get('quarter'))
    added = 0
    if can_capture:
        start_date = first_later_session('台股', now)
        for group in snapshot['groups']:
            for stock in group['stocks']:
                sym = stock['symbol']
                current = by_symbol.get(sym)
                value = _num(current.get('調整收盤價')) if current else None
                if value is None or value <= 0 or stock['yoy'] is None:
                    continue
                triggers = []
                if stock['yoy'] > 0 and stock['price'] is not None and stock['price'] < 0:
                    triggers.append('price_revenue')
                if (group['group'] != '金融' and stock['yoy'] > 0
                        and stock['margin'] is not None and stock['margin'] <= 0):
                    triggers.append('revenue_margin')
                for kind in triggers:
                    key = (day,sym,kind)
                    if key in archive_keys:
                        continue
                    # One episode per stock and kind per 20 actual benchmark sessions.
                    recent = any((r['symbol'] == sym and r['kind'] == kind
                                  and r['price_day'] in positions
                                  and 0 <= positions[day]-positions[r['price_day']] < 20)
                                 for r in old)
                    if recent:
                        continue
                    row = {field:'' for field in FIELDS}
                    row.update(first_seen=now.isoformat(timespec='seconds'),
                               price_day=day, symbol=sym, name=stock['name'],
                               sector=group['group'], kind=kind,
                               revenue_month=snapshot['month'], profit_quarter=snapshot['quarter'],
                               price20_pct=stock['price'] if stock['price'] is not None else '',
                               revenue_yoy_pct=stock['yoy'],
                               margin_pct=stock['margin'] if stock['margin'] is not None else '',
                               method=PROSPECTIVE_METHOD, start_date=start_date)
                    old.append(row)
                    archive_keys.add(key)
                    added += 1
    matured = 0
    price_cache = {}
    for row in old:
        origin = prospective_start(row)
        if origin is None or not latest_day or origin > latest_day:
            continue
        symbol = row['symbol']
        if symbol not in price_cache:
            price_cache[symbol] = _prices(histories.get(symbol))[0]
        stock_map = price_cache[symbol]
        start_stock = stock_map.get(origin)
        start_bench = bench_map.get(origin)
        if start_stock is None or start_bench is None:
            continue
        for horizon in HORIZONS:
            if row.get(f'mature_date_{horizon}d'):
                continue
            end_date = session_after('台股', origin, horizon)
            if end_date > latest_day:
                continue
            close_stock = stock_map.get(end_date)
            close_bench = bench_map.get(end_date)
            if close_stock is None or close_bench is None:
                continue
            stock_gain = 100 * (close_stock / start_stock - 1)
            bench_gain = 100 * (close_bench / start_bench - 1)
            row[f'stock_return_{horizon}d'] = round(stock_gain, 4)
            row[f'benchmark_return_{horizon}d'] = round(bench_gain, 4)
            row[f'excess_return_{horizon}d'] = round(stock_gain-bench_gain, 4)
            row[f'mature_date_{horizon}d'] = end_date
            matured += 1
    # The existing daily CSV and Pages flow persists all events automatically.
    if archive_rows is None and (added or matured):
        _save(old, history_rows)
    return {'rows':old,'new':added,'matured':matured,
            'capture_ok':can_capture,'day':day,
            'latest_day':latest_day}


def history_lab_section(universe, industry, names, records, histories, benchmarks, history_rows):
    data = record_and_measure(universe, industry, names, records, histories, benchmarks, history_rows)
    rows = data['rows']
    count_days = len({r.get('交易日期') for r in history_rows
                      if r.get('市場') == '台股' and r.get('交易日期')})
    prospective = [r for r in rows if prospective_start(r) is not None]
    cards = []
    for kind, title in KINDS:
        subset = [r for r in prospective if r['kind'] == kind]
        unique_days = len({r['price_day'] for r in subset})
        items = []
        for horizon in HORIZONS:
            mature = [r for r in subset if _status(r,horizon,data['latest_day']) == 'matured']
            pending = sum(_status(r,horizon,data['latest_day']) == 'pending'
                          for r in subset)
            gaps = len(subset)-len(mature)-pending
            if mature:
                extras = [_num(r[f'excess_return_{horizon}d']) for r in mature]
                med = median(extras)
                above = sum(v>0 for v in extras)
                date_count = len({r['price_day'] for r in mature})
                label = ('仍不足以判斷' if len(mature) < 30 or date_count < 10
                         else '初步描述・仍非可靠預測')
                result = (f'超額中位數 {med:+.2f}pp｜跑贏0050 {above}/{len(mature)}｜'
                          f'{date_count}個訊號日期｜{label}')
            else:
                result = '尚無成熟樣本，不顯示成功率'
            items.append('<tr><td>'+str(horizon)+' 日</td><td>'+str(len(mature))+'</td>'
                         '<td>'+str(pending)+'</td><td>'+str(gaps)+'</td><td>'+_esc(result)+'</td></tr>')
        cards.append('<section class="hl-group"><h3>'+_esc(title)+'</h3>'
                     '<p class="muted">已封存 '+str(len(subset))+' 筆｜'+str(unique_days)+' 個觀察交易日</p>'
                     '<div class="hl-scroll"><table><thead><tr><th>追蹤</th><th>成熟</th><th>待成熟</th>'
                     '<th>缺資料</th><th>後續表現（只供描述）</th></tr></thead><tbody>'
                     +''.join(items)+'</tbody></table></div></section>')
    kind_label = dict(KINDS)
    recent = sorted(rows, key=lambda r: (r['price_day'],r['first_seen']), reverse=True)[:12]
    latest = []
    for r in recent:
        pieces = []
        for h in HORIZONS:
            state = _status(r, h, data['latest_day'])
            if state == 'matured':
                parts = _num(r[f'excess_return_{h}d'])
                pieces.append(f'{h}日超額 {parts:+.2f}pp')
            elif state == 'legacy':
                pieces.append('舊制封存')
                break
            elif state == 'pending':
                pieces.append(f'{h}日待成熟')
            else:
                pieces.append(f'{h}日缺資料')
        latest.append('<li><strong>'+_esc(r['name'])+'</strong> <small>'+_esc(r['symbol'])
                      +' · '+_esc(r['price_day'])+' · '+_esc(r.get('first_seen', ''))+' · '+_esc(kind_label.get(r['kind'],r['kind']))
                      +'</small><div>'+_esc('｜'.join(pieces))+'</div></li>')
    recent_html = '<ol class="hl-events">'+''.join(latest)+'</ol>' if recent else '<p class="muted">尚無首次觀察紀錄；下次成功掃描後會依當時條件開始保存。</p>'
    capture_note = ('本次完整台股資料與來源日期符合入庫條件。'
                    if data['capture_ok'] else '本次資料不完整、日期過舊或缺少官方月份／季度；沒有新增假訊號。')
    return '''<h2>🗂️ 台股｜歷史訊號與可信度研究室・1.29</h2>
    <p class="muted">只把<b>本版安裝後實際觀察到的</b>跨面向線索寫入既有歷史 CSV；
    同一股票／線索至少間隔20個0050交易日才重複入庫，減少同一段行情反覆計數。
    沒有替舊日期補造營收訊號，也沒有買賣指令。</p>
    <div class="history-lab-v129" id="history-lab-v129">
    <p class="hl-status">舊有技術歷史存檔涵蓋 '''+str(count_days)+''' 個台股掃描日期；
    前瞻訊號 '''+str(len(prospective))+''' 筆，舊制封存 '''+str(len(rows)-len(prospective))+''' 筆，本次新增 '''+str(data['new'])+''' 筆、成熟結果新增 '''+str(data['matured'])+''' 項。
    '''+_esc(capture_note)+'''</p>
    <p class="muted">前瞻訊號從首次觀察日之後第一個台股交易日的收盤價起算，再追蹤5／10／20個交易日。舊制封存仍可查閱，前瞻統計只計入新制；
    以0050同日價格漲跌作對照。若個股缺該日價格則留空，不用前一日代替。
    當期比較不包含交易成本與可成交性。</p>
    '''+''.join(cards)+'''
    <details><summary class="hl-details">最近12筆原始線索及後續狀態</summary>'''+recent_html+'''</details>
    <p class="muted">信心限制：<b>至少30筆成熟、10個不同訊號日期</b>才可顯示初步描述，仍不代表統計顯著；
    多檔股票受同一市場事件影響，觀察結果不獨立。訊號資料日期、首次取得時間與收益基準一併保存；
    既有的「績效游泳池」追蹤技術前十，兩者不可混算。
    季報、月營收與股價的時間範圍不同，任何結果均非因果或低估證明。</p>
    <p class="muted"><a href="data/history.csv">查看原始歷史 CSV</a>（新增「研究訊號歷史v129」欄，保留首次觀察與到期結果）</p>
    </div><style>
    .history-lab-v129{display:grid;gap:13px;max-width:100%}
    .history-lab-v129 .hl-status{border:1px solid #d7e5f1;background:#f2f7fc;border-radius:11px;
      color:#315873;padding:13px;font-weight:650;font-size:.88rem;line-height:1.7;margin:0}
    .history-lab-v129 .hl-group{border:1px solid #dee7f1;border-radius:14px;background:#fff;padding:13px;min-width:0}
    .history-lab-v129 .hl-group h3{font-size:1.04rem;margin:4px 0 3px;color:#275476}
    .history-lab-v129 .hl-scroll{overflow:auto;max-width:100%;border-radius:9px;border:1px solid #e6ebf2}
    .history-lab-v129 table{min-width:700px;width:100%;font-size:.81rem;border-collapse:collapse}
    .history-lab-v129 th,.history-lab-v129 td{padding:10px 8px;border-bottom:1px solid #e8edf4;text-align:left;vertical-align:top}
    .history-lab-v129 th{background:#edf5fc;white-space:nowrap}
    .history-lab-v129 .hl-details{padding:12px;border-radius:10px;background:#eaf3fc;
      color:#245781;font-weight:750}
    .history-lab-v129 .hl-events{padding-left:26px;margin:8px 0;line-height:1.7}
    .history-lab-v129 .hl-events li{padding:9px 3px;border-bottom:1px solid #e7edf3;font-size:.85rem}
    .history-lab-v129 .hl-events small{color:#718091}
    </style>'''
