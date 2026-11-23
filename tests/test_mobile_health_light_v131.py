"""Offline checks for the mobile 1.31 health light.

HTML is a snapshot of a successful scan; it must not claim to be live data.
"""
import unittest
from datetime import datetime

import pandas as pd

import radar
from health_light_v131 import health_light_section, snapshot_health
from trading_sessions import last_completed_session, recent_sessions


SCAN_TIME = datetime.fromisoformat('2026-11-23T16:40:00+08:00')


class MobileHealthLightTests(unittest.TestCase):
    def setUp(self):
        self.records = []
        self.benchmarks = {}
        for market, symbols in radar.UNIVERSE.items():
            day = last_completed_session(market, SCAN_TIME)
            self.records.extend(
                {'市場': market, '股票': code, '交易日期': day} for code in symbols
            )
            trading_days = recent_sessions(market, day, 61)
            self.benchmarks[market] = pd.DataFrame(
                {'Close': [100.0] * 61},
                index=pd.to_datetime(trading_days),
            )

    def status(self):
        return snapshot_health(self.records, self.benchmarks, radar.UNIVERSE, SCAN_TIME)

    def page(self):
        return health_light_section(
            self.records, self.benchmarks, radar.UNIVERSE, SCAN_TIME
        )

    def test_complete_tw_and_us_show_expected_date_and_50_of_50(self):
        statuses = self.status()
        self.assertEqual([r['covered'] for r in statuses], [50, 50])
        self.assertTrue(all(r['ready'] for r in statuses))
        self.assertEqual(statuses[0]['expected'], '2026-11-23')
        self.assertEqual(statuses[1]['expected'], '2026-11-20')
        page = self.page()
        self.assertIn('id="radar-health-light-v131"', page)
        self.assertIn('本次報告行情完整', page)
        self.assertEqual(page.count('50 / 50'), 2)
        self.assertIn('2026-11-23', page)
        self.assertIn('2026-11-20', page)
        self.assertIn('0050.TW：完整', page)
        self.assertIn('SPY：完整', page)

    def test_missing_stock_does_not_falsely_show_green(self):
        missing_code = radar.UNIVERSE['台股'][0]
        self.records = [r for r in self.records if r['股票'] != missing_code]
        status = self.status()
        self.assertFalse(status[0]['ready'])
        self.assertEqual(status[0]['covered'], 49)
        self.assertTrue(status[1]['ready'])
        self.assertIn('本次報告有行情異常', self.page())
        self.assertIn('49 / 50', self.page())

    def test_duplicate_stock_is_not_counted_as_extra_coverage(self):
        self.records.append(dict(self.records[0]))
        status = self.status()
        self.assertEqual(status[0]['covered'], 49)
        self.assertFalse(status[0]['ready'])

    def test_stale_market_date_and_missing_benchmark_detected(self):
        self.records[0]['交易日期'] = '2026-11-20'
        self.benchmarks['美股'] = self.benchmarks['美股'].iloc[:-1]
        status = self.status()
        self.assertEqual(status[0]['covered'], 49)
        self.assertFalse(status[0]['ready'])
        self.assertFalse(status[1]['benchmark_ok'])
        self.assertIn('SPY：有缺口', self.page())

    def test_browser_warns_after_72_hours_without_live_fetches(self):
        page = self.page()
        self.assertIn('data-generated-at="2026-11-23T16:40:00+08:00"', page)
        self.assertIn('72*60*60*1000', page)
        self.assertIn("document.addEventListener('visibilitychange'", page)
        self.assertIn('資料較舊，請核對日期', page)
        self.assertIn('不是即時行情', page)
        self.assertNotIn('fetch(', page)
        self.assertNotIn('XMLHttpRequest', page)

    def test_naive_timestamp_is_refused(self):
        with self.assertRaisesRegex(ValueError, '含時區'):
            snapshot_health(
                self.records, self.benchmarks, radar.UNIVERSE,
                datetime.fromisoformat('2026-11-23T16:40:00'),
            )
