"""v1.31 read-only stock radar health check.

Fetches quotes without writing history, reports, rankings or production files.
The publication gate is inspected, never invoked as a publisher.
"""
from __future__ import annotations

import argparse
import io
import json
import time
from contextlib import redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo

import radar
from history_lab_v129 import _prices
from trading_sessions import last_completed_session, recent_sessions


def _error_for(code, errors):
    return [str(e) for e in errors if str(e).startswith(code + ':')]


def analyze_quotes(records, benchmarks, *, now, errors=(), recovered=(), retry_errors=None):
    """Pure diagnostic: no downloads and no filesystem writes."""
    retry_errors = retry_errors or {}
    markets = []
    for market, codes in radar.UNIVERSE.items():
        expected = last_completed_session(market, now)
        candidates = [r for r in records if r.get('市場') == market]
        by_code = {}
        for row in candidates:
            by_code.setdefault(row.get('股票'), []).append(row)

        problems = []
        passed = 0
        for code in codes:
            matches = by_code.get(code, [])
            if len(matches) == 1 and matches[0].get('交易日期') == expected:
                passed += 1
                continue
            if not matches:
                reason = '無有效行情'
            elif len(matches) > 1:
                reason = '重複股票紀錄'
            else:
                reason = '行情日期 ' + str(matches[0].get('交易日期') or '未知')
            provider_errors = _error_for(code, errors)
            if provider_errors:
                reason += '；來源錯誤：' + provider_errors[-1][:150]
            if code in retry_errors:
                reason += '；重試：' + retry_errors[code][:120]
            problems.append({'symbol': code, 'reason': reason})

        benchmark_code = radar.BENCHMARKS[market][0]
        prices, dates = _prices(benchmarks.get(market))
        expected_days = recent_sessions(market, expected, radar.TECHNICAL_WINDOW)
        missing_days = [d for d in expected_days if d not in prices]
        if not dates:
            benchmark_problem = '基準沒有有效收盤資料'
        elif dates[-1] != expected:
            benchmark_problem = '基準最新日期 ' + dates[-1] + '，預期 ' + expected
        elif missing_days:
            benchmark_problem = '基準近 61 個交易日缺 ' + str(len(missing_days)) + ' 天：' + ', '.join(missing_days[:5])
        else:
            benchmark_problem = None
        if benchmark_code in retry_errors and benchmark_problem:
            benchmark_problem += '；重試：' + retry_errors[benchmark_code][:120]

        ready = passed == len(codes) and benchmark_problem is None
        markets.append({
            'name': market, 'expected_day': expected, 'complete': passed,
            'total': len(codes), 'ready': ready, 'missing_or_stale': problems,
            'benchmark': benchmark_code, 'benchmark_problem': benchmark_problem,
            'recovered': [x for x in recovered if x in codes or x == benchmark_code],
        })

    # Recheck against the real v1.30 publication validator to prevent
    # diagnostic claims accidentally drifting from production's gate.
    with redirect_stdout(io.StringIO()):
        try:
            radar.require_complete_markets(records, benchmarks, now)
            actual_gate_passes = True
            gate_reason = ''
        except RuntimeError as exc:
            actual_gate_passes = False
            gate_reason = str(exc)

    all_ready = all(m['ready'] for m in markets)
    return {
        'scanned_at': now.isoformat(timespec='seconds'),
        'status': 'READY' if all_ready and actual_gate_passes else 'BLOCKED',
        'publish_gate_passes': actual_gate_passes,
        'gate_reason': gate_reason,
        'markets': markets,
        'initial_provider_errors': list(errors),
        'read_only': True,
    }


def fetch_live_report(*, now=None, retry_attempts=1, sleep_seconds=0.5):
    """Read real Yahoo quotes; retry missing/stale symbols, without publishing."""
    now = now or datetime.now(ZoneInfo('Asia/Taipei'))
    records, errors, _histories = radar.latest_snapshot()
    recovered, retry_errors = [], {}
    for market, codes in radar.UNIVERSE.items():
        expected = last_completed_session(market, now)
        by_code = {r.get('股票'): r for r in records if r.get('市場') == market}
        for code in codes:
            row = by_code.get(code)
            if row and row.get('交易日期') == expected:
                continue
            for attempt in range(retry_attempts):
                try:
                    frame = radar.yf.Ticker(code).history(period='6mo', auto_adjust=True)
                    fresh = radar.calculate(frame, market, code)
                    if fresh.get('交易日期') != expected:
                        raise ValueError('行情仍停在 ' + str(fresh.get('交易日期')))
                    records = [r for r in records if r.get('股票') != code]
                    records.append(fresh)
                    recovered.append(code)
                    retry_errors.pop(code, None)
                    break
                except Exception as exc:
                    retry_errors[code] = type(exc).__name__ + ': ' + str(exc)[:120]
                    if attempt + 1 < retry_attempts and sleep_seconds:
                        time.sleep(sleep_seconds)

    benchmarks = {}
    for market, (ticker, _description) in radar.BENCHMARKS.items():
        expected = last_completed_session(market, now)
        for attempt in range(1 + retry_attempts):
            try:
                frame = radar.yf.Ticker(ticker).history(period='6mo', auto_adjust=True)
                prices, dates = _prices(frame)
                expected_days = recent_sessions(market, expected, radar.TECHNICAL_WINDOW)
                if not dates or dates[-1] != expected or any(x not in prices for x in expected_days):
                    raise ValueError('基準行情過舊或最近 61 日有缺口')
                benchmarks[market] = frame
                if attempt:
                    recovered.append(ticker)
                retry_errors.pop(ticker, None)
                break
            except Exception as exc:
                retry_errors[ticker] = type(exc).__name__ + ': ' + str(exc)[:120]
                if attempt < retry_attempts and sleep_seconds:
                    time.sleep(sleep_seconds)
    return analyze_quotes(
        records, benchmarks, now=now, errors=errors,
        recovered=recovered, retry_errors=retry_errors,
    )


def format_markdown(report):
    labels = {'READY': '可通過行情門檻', 'BLOCKED': '未通過行情門檻'}
    lines = [
        '# 🕸️ 股票別墅 1.31｜唯讀行情體檢',
        '',
        '掃描時間：' + report['scanned_at'],
        '',
        '**狀態：' + labels[report['status']] + '**',
        '',
        '| 市場 | 預期收盤日 | 個股有效數 | 基準 | 可發布 |',
        '| --- | --- | ---: | --- | --- |',
    ]
    for market in report['markets']:
        bench_status = '完整' if market['benchmark_problem'] is None else '異常'
        lines.append(
            '| ' + market['name'] + ' | ' + market['expected_day']
            + ' | ' + str(market['complete']) + '/' + str(market['total'])
            + ' | ' + market['benchmark'] + '：' + bench_status
            + ' | ' + ('是' if market['ready'] else '否') + ' |'
        )

    for market in report['markets']:
        if market['ready'] and not market['recovered']:
            continue
        lines += ['', '### ' + market['name'] + ' 診斷']
        if market['recovered']:
            lines.append('- 自動重新抓取後恢復：' + ', '.join(market['recovered']))
        if market['benchmark_problem']:
            lines.append('- 基準異常：' + market['benchmark_problem'])
        for problem in market['missing_or_stale']:
            lines.append('- ' + problem['symbol'] + '：' + problem['reason'])
    lines += [
        '', '> 本次僅從行情來源讀取資料並檢查發布條件；沒有執行正式更新、',
        '> 沒有修改 GitHub 歷史、排名或網站。此報告不是股票買賣建議。',
    ]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='1.31 stock radar read-only market check')
    parser.add_argument('--json', action='store_true', help='print machine-readable report')
    parser.add_argument('--retry', type=int, default=1, choices=range(0, 4))
    args = parser.parse_args()
    report = fetch_live_report(retry_attempts=args.retry)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(report))
    # BLOCKED is data quality status, not a tool execution error.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
