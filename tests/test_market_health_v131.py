"""Deterministic offline tests for the read-only v1.31 quote inspector."""
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd

import radar
import market_health_v131 as health
from trading_sessions import last_completed_session, recent_sessions


NOW = datetime.fromisoformat('2026-11-23T16:40:00+08:00')


class MarketHealthTests(unittest.TestCase):
    def setUp(self):
        self.records = []
        self.benchmarks = {}
        self.frames = {}
        for market, codes in radar.UNIVERSE.items():
            expected = last_completed_session(market, NOW)
            for code in codes:
                self.records.append({'市場': market, '股票': code, '交易日期': expected})
            days = recent_sessions(market, expected, 85)
            frame = pd.DataFrame(
                {'Close': [100.0]*85, 'Volume': [1000]*85},
                index=pd.to_datetime(days),
            )
            self.benchmarks[market] = frame
            self.frames[radar.BENCHMARKS[market][0]] = frame
            for code in codes:
                self.frames[code] = frame

    def report(self, **kwargs):
        return health.analyze_quotes(self.records, self.benchmarks, now=NOW, **kwargs)

    def test_both_markets_and_benchmarks_complete(self):
        report = self.report()
        self.assertEqual(report['status'], 'READY')
        self.assertTrue(report['publish_gate_passes'])
        self.assertTrue(report['read_only'])
        self.assertEqual([x['complete'] for x in report['markets']], [50, 50])
        self.assertTrue(all(x['ready'] for x in report['markets']))

    def test_missing_stock_is_identified_with_original_error(self):
        code = radar.UNIVERSE['美股'][0]
        self.records = [x for x in self.records if x['股票'] != code]
        report = self.report(errors=[code + ': source timeout'])
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertTrue(report['markets'][0]['ready'])
        self.assertEqual(report['markets'][1]['complete'], 49)
        self.assertEqual(report['markets'][1]['missing_or_stale'][0]['symbol'], code)
        self.assertIn('source timeout', report['markets'][1]['missing_or_stale'][0]['reason'])
        self.assertIn(code, health.format_markdown(report))

    def test_stale_stock_is_identified_without_falsely_marking_ready(self):
        self.records[0]['交易日期'] = '2026-11-20'
        report = self.report()
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['markets'][0]['complete'], 49)
        self.assertIn('行情日期', report['markets'][0]['missing_or_stale'][0]['reason'])

    def test_missing_benchmark_day_is_identified(self):
        day = self.benchmarks['台股'].index[-4]
        self.benchmarks['台股'] = self.benchmarks['台股'].drop(day)
        report = self.report()
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['markets'][0]['complete'], 50)
        self.assertIn('缺 1 天', report['markets'][0]['benchmark_problem'])
        self.assertEqual(report['markets'][1]['benchmark_problem'], None)

    def test_retry_restores_missing_stock_and_does_not_write_website_or_history(self):
        code = radar.UNIVERSE['台股'][0]
        initial = [x for x in self.records if x['股票'] != code]
        with TemporaryDirectory() as root:
            history = Path(root) / 'history.csv'
            site = Path(root) / 'index.html'
            history.write_bytes(b'ORIGINAL CSV')
            site.write_bytes(b'ORIGINAL HTML')

            def ticker_factory(symbol):
                return Mock(history=Mock(return_value=self.frames[symbol]))

            with (
                patch.object(radar, 'DATA_FILE', history),
                patch.object(radar, 'SITE_FILE', site),
                patch.object(radar, 'latest_snapshot', return_value=(initial, [code+': initial timeout'], {})),
                patch.object(radar.yf, 'Ticker', side_effect=ticker_factory),
            ):
                report = health.fetch_live_report(now=NOW, retry_attempts=1, sleep_seconds=0)
            self.assertEqual(report['status'], 'READY')
            self.assertEqual(report['markets'][0]['recovered'], [code])
            self.assertEqual(history.read_bytes(), b'ORIGINAL CSV')
            self.assertEqual(site.read_bytes(), b'ORIGINAL HTML')

    def test_retry_failure_returns_blocked_diagnostic_without_writing(self):
        code = radar.UNIVERSE['台股'][0]
        initial = [x for x in self.records if x['股票'] != code]
        def ticker_factory(symbol):
            if symbol == code:
                return Mock(history=Mock(side_effect=ValueError('provider offline')))
            return Mock(history=Mock(return_value=self.frames[symbol]))
        with (
            patch.object(radar, 'latest_snapshot', return_value=(initial, [], {})),
            patch.object(radar.yf, 'Ticker', side_effect=ticker_factory),
        ):
            report = health.fetch_live_report(now=NOW, retry_attempts=1, sleep_seconds=0)
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertIn('provider offline', report['markets'][0]['missing_or_stale'][0]['reason'])
