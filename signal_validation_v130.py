"""Stock Radar 1.30: prospective signal-versus-market and fixed-pool validation.

Only observations actually archived by 1.29 are eligible. 1.30 never reconstructs
historical signal membership using newly learned fundamentals. The same-day
fixed TW50 research pool is a descriptive comparator, not a random portfolio
or a genuinely signal-free control group. Missing dates are never forward-filled.
"""
from __future__ import annotations

import html
import json
import math
from collections import defaultdict
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

from history_lab_v129 import _load as load_signals, _prices, _status, KINDS, HORIZONS

FIELD = '訊號同日對照v130'
SCHEMA = ('kind', 'horizon', 'end_date', 'pool_count', 'eligible_count',
          'pool_median_pct', 'signal_minus_pool_pp', 'calculated_at')


def _esc(value):
    return html.escape(str(value), quote=True)


def _num(value):
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _saved_controls(history_rows):
    """Validate already-persisted comparisons, and fail closed on broken history."""
    saved = {}
    for source in history_rows:
        raw = source.get(FIELD, '')
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError('1.30 對照存檔格式錯誤：不更新歷史') from exc
        if not isinstance(data, list):
            raise RuntimeError('1.30 對照存檔不是清單：不更新歷史')
        for value in data:
            if (not isinstance(value, dict) or
                not all(k in value for k in SCHEMA) or
                value['kind'] not in dict(KINDS) or
                value['horizon'] not in HORIZONS or
                not isinstance(value['end_date'], str) or len(value['end_date']) != 10 or
                _num(value['pool_count']) is None or _num(value['eligible_count']) is None or
                _num(value['pool_median_pct']) is None or
                _num(value['signal_minus_pool_pp']) is None or
                not isinstance(value['calculated_at'], str) or
                source.get('市場') != '台股'):
                raise RuntimeError('1.30 對照存檔欄位錯誤：不更新歷史')
            key = (source.get('交易日期'), source.get('股票'),
                   value['kind'], value['horizon'])
            if key in saved:
                raise RuntimeError('1.30 對照存檔重複：不更新歷史')
            saved[key] = dict(value)
    return saved


def _pool_comparison(signal, horizon, history_rows_by_date, valid_symbols,
                     price_cache, minimum_fraction=.80):
    """Use as-of archived pool membership and exact end date; no new look-ahead labels.

    Original daily archived adjusted close is the starting value, same method
    as v1.29. Endpoint is the fetched adjusted close for the exact horizon date.
    """
    day, symbol = signal['price_day'], signal['symbol']
    end_date = signal.get(f'mature_date_{horizon}d', '')
    stock_result = _num(signal.get(f'stock_return_{horizon}d'))
    if not end_date or stock_result is None or not valid_symbols or symbol not in valid_symbols:
        return None
    group = history_rows_by_date.get(day, {})
    others = [s for s in valid_symbols if s != symbol]
    eligible_count = len(others)
    threshold = max(3, math.ceil(eligible_count * minimum_fraction))
    # Not enough stocks stored as of the event date => no baseline at all.
    if len(set(group).intersection(others)) < threshold:
        return None
    returns = []
    for candidate in others:
        base_row = group.get(candidate)
        if base_row is None:
            continue
        base = _num(base_row.get('調整收盤價'))
        finish = price_cache.get(candidate, {}).get(end_date)
        if base is not None and base > 0 and finish is not None and finish > 0:
            returns.append((finish/base - 1) * 100)
    if len(returns) < threshold:
        return None
    med = median(returns)
    return dict(kind=signal['kind'], horizon=horizon, end_date=end_date,
                pool_count=len(returns), eligible_count=eligible_count,
                pool_median_pct=round(med, 4),
                signal_minus_pool_pp=round(stock_result-med, 4),
                calculated_at=datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'))


def validate_signals(universe, history_rows, histories, benchmarks,
                     signals=None, save=True):
    """Count matured evidence, preserve original event archive, add future pool comparisons."""
    events = load_signals(history_rows) if signals is None else [dict(x) for x in signals]
    existing = _saved_controls(history_rows)
    wanted = set(universe.get('台股', ()))
    asof_prices = defaultdict(dict)
    for source in history_rows:
        if source.get('市場') == '台股' and source.get('股票') in wanted and source.get('交易日期'):
            asof_prices[source['交易日期']][source['股票']] = source
    price_cache = {stock:_prices(histories.get(stock))[0] for stock in wanted}
    bench_map, bench_days = _prices(benchmarks.get('台股'))
    results = []
    new_controls = 0
    for signal in events:
        day, symbol, kind = signal['price_day'], signal['symbol'], signal['kind']
        if symbol not in wanted:
            continue
        for horizon in HORIZONS:
            key = (day, symbol, kind, horizon)
            status = _status(signal, horizon, bench_days, bench_map)
            control = existing.get(key)
            if status == 'matured' and control is None:
                control = _pool_comparison(signal, horizon, asof_prices, wanted, price_cache)
                if control:
                    existing[key] = control
                    new_controls += 1
            results.append({'event':signal, 'horizon':horizon,
                            'state':status, 'control':control})
    if save and new_controls:
        row_lookup = {(r.get('交易日期'),r.get('股票')):r for r in history_rows
                      if r.get('市場') == '台股'}
        grouped = defaultdict(list)
        for (day,symbol,kind,horizon),control in existing.items():
            if (day,symbol) not in row_lookup:
                raise RuntimeError('1.30 對照結果找不到原始日期：拒絕存檔')
            grouped[(day,symbol)].append(control)
        for key,values in grouped.items():
            values.sort(key=lambda r:(r['kind'],r['horizon']))
            row_lookup[key][FIELD] = json.dumps(values, ensure_ascii=False,
                                               separators=(',', ':'),allow_nan=False)
    return {'results':results, 'new_controls':new_controls,
            'total_events':len(events), 'saved_controls':len(existing)}


def validation_section(universe, history_rows, histories, benchmarks):
    report = validate_signals(universe, history_rows, histories, benchmarks)
    chunks = []
    for kind,label in KINDS:
        lines = []
        for horizon in HORIZONS:
            entries = [r for r in report['results']
                       if r['event']['kind']==kind and r['horizon']==horizon]
            mature = [r for r in entries if r['state']=='matured']
            pending = sum(r['state']=='pending' for r in entries)
            gaps = len(entries) - len(mature) - pending
            compare = [r for r in mature if r['control'] is not None]
            dates = len({r['event']['price_day'] for r in mature})
            if mature:
                benchmark_excess = [_num(r['event'].get(f'excess_return_{horizon}d')) for r in mature]
                benchmark_excess = [v for v in benchmark_excess if v is not None]
                bench_text = (f'{median(benchmark_excess):+.2f}pp／'
                              f'{sum(v>0 for v in benchmark_excess)}/{len(benchmark_excess)}'
                              if benchmark_excess else '—')
            else:
                bench_text = '待成熟'
            if compare:
                diffs = [_num(r['control']['signal_minus_pool_pp']) for r in compare]
                pool_text = f'{median(diffs):+.2f}pp／{sum(v>0 for v in diffs)}/{len(diffs)}'
            else:
                pool_text = '待累積' if not mature else '無可比資料'
            # 30 rows observed across just 1 day are not 30 independent trials.
            evidence = ('資料不足' if len(mature) < 30 or dates < 10
                        else '可作初步描述・未通過獨立驗證')
            lines.append('<tr><td>'+str(horizon)+'日</td>'
                         '<td>'+str(len(mature))+'／'+str(pending)+'／'+str(gaps)+'</td>'
                         '<td>'+str(dates)+'</td>'
                         '<td>'+_esc(bench_text)+'</td>'
                         '<td>'+_esc(pool_text)+' <small>('+str(len(compare))+'組)</small></td>'
                         '<td>'+_esc(evidence)+'</td></tr>')
        chunks.append('<section class="sv-group"><h3>'+_esc(label)+'</h3>'
                      '<div class="sv-scroll"><table><thead><tr><th>期限</th>'
                      '<th>成熟／待成熟／缺口</th><th>不同訊號日</th>'
                      '<th>對0050中位數／跑贏筆數</th>'
                      '<th>對同日研究池中位數／跑贏筆數</th><th>判讀</th>'
                      '</tr></thead><tbody>'+''.join(lines)+'</tbody></table></div></section>')
    note = ('已封存 '+str(report['total_events'])+' 筆1.29訊號；'
            '本次新增 '+str(report['new_controls'])+' 組同日研究池對照，'
            '累計完成 '+str(report['saved_controls'])+' 組對照。')
    return '''<h2>🧪 台股｜訊號有效性驗證室・1.30</h2>
    <p class="muted">只驗證<b>1.29 安裝後當時封存的訊號</b>，不回頭用新財報替過去挑股票。
    這不是交易策略回測，不能把「跑贏」當成買進訊號。</p>
    <div class="signal-valid-v130" id="signal-valid-v130">
    <p class="sv-summary">'''+_esc(note)+'''</p>
    <p class="sv-explain">同一筆訊號分別看5／10／20個0050交易日後的實際同日報酬。
    對0050沿用1.29已存的歷史結果；研究池對照使用<b>訊號日原本固定50檔中，除了訊號股以外的其他股票</b>，
    用原存收盤價和同一到期日行情計算個股報酬中位數，至少80%同日樣本完整才顯示。
    研究池不是隨機抽樣，也不是已證明「沒有訊號」的控制組。</p>
    '''+''.join(chunks)+'''
    <p class="sv-explain"><b>判讀限制：</b>每格「中位數／跑贏筆數」只描述到期樣本；
    未到期絕不算失敗，無資料也不補零。至少30筆成熟、分散於10個以上觀察日才暫列初步描述，
    但同日個股高度相關、20日觀察彼此重疊，還未進行樣本外、成本及顯著性驗證。
    原始收盤資料可能因除權息調整而重算，亦非可成交的績效。
    研究池以中位數作對照、並非可直接投資的指數，不能與0050報酬解釋成同一種基準。</p>
    <p class="sv-explain">資料保留於<a href="data/history.csv">既有歷史 CSV</a>的「研究訊號歷史v129」和新增的「訊號同日對照v130」欄位。
    1.30 未改動技術／產業／法人／新聞的原定30／30／25／15權重，也不自動交易。</p>
    </div><style>
    .signal-valid-v130{display:grid;gap:12px;max-width:100%}
    .signal-valid-v130 .sv-summary{padding:12px;border:1px solid #dce6f0;border-radius:10px;
      background:#f5f8fc;font-weight:650;color:#34546d;line-height:1.6;margin:0}
    .signal-valid-v130 .sv-explain{line-height:1.7;color:#667689;font-size:.84rem;margin:0}
    .signal-valid-v130 .sv-group{border:1px solid #dde5ed;border-radius:12px;padding:12px;background:white;min-width:0}
    .signal-valid-v130 h3{font-size:1rem;margin:4px 0 10px;color:#2a536f}
    .signal-valid-v130 .sv-scroll{overflow:auto;max-width:100%}
    .signal-valid-v130 table{min-width:830px;border-collapse:collapse;width:100%;font-size:.79rem}
    .signal-valid-v130 th,.signal-valid-v130 td{padding:10px 8px;border-bottom:1px solid #e7ecf3;text-align:left;vertical-align:top}
    .signal-valid-v130 th{background:#f0f4f9;white-space:nowrap}
    .signal-valid-v130 td small{font-size:.72rem;color:#6b7988;white-space:nowrap}
    </style>'''
