"""No network; VIX snapshots must be dated and never masquerade as live."""
import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

import vix_overview_v134 as vix


ASOF = datetime.fromisoformat('2026-11-25T12:51:00+08:00')


class VixOverviewTests(unittest.TestCase):
    @staticmethod
    def frame(values, dates=('2026-11-20','2026-11-23','2026-11-24')):
        return pd.DataFrame({'Close': values}, index=pd.to_datetime(dates))

    def test_daily_snapshot_has_us_market_date_and_point_change(self):
        report = vix.observation_from_frame(self.frame([19.5,21,20.1]), ASOF)
        self.assertEqual(report['date'], '2026-11-24')
        self.assertEqual(report['value'],20.1)
        self.assertEqual(report['change_points'],-0.9)
        self.assertEqual(report['age_days'],1)
        page = vix.render_vix_card(report)
        self.assertIn('20.10',page)
        self.assertIn('-0.90',page)
        self.assertIn('2026-11-24',page)
        self.assertIn('非即時行情',page)
        self.assertIn('不代表必然下跌',page)
        self.assertNotIn('立即買進',page)

    def test_future_dated_values_are_not_trusted(self):
        report = vix.observation_from_frame(
            self.frame([19,20,22], dates=('2026-11-20','2026-11-24','2026-11-27')),
            ASOF,
        )
        self.assertEqual(report['date'],'2026-11-24')
        self.assertEqual(report['value'],20)

    def test_missing_or_invalid_data_never_fabricates_a_quote(self):
        self.assertIsNone(vix.observation_from_frame(pd.DataFrame(),ASOF))
        self.assertIsNone(vix.observation_from_frame(self.frame([float('nan'), -5, 0]),ASOF))
        page = vix.render_vix_card(None)
        self.assertIn('本次未取得可核對的 VIX 資料',page)
        self.assertIn('>—</strong>',page)
        self.assertIn('非即時行情',page)

    def test_stale_snapshot_is_explicitly_warned(self):
        report = vix.observation_from_frame(
            self.frame([18,20],dates=('2026-11-04','2026-11-05')), ASOF
        )
        self.assertIn('資料較舊',vix.render_vix_card(report))

    def test_one_valid_daily_value_has_no_fake_day_change(self):
        report = vix.observation_from_frame(
            self.frame([20],dates=('2026-11-24',)),ASOF
        )
        self.assertIsNone(report['change_points'])
        self.assertIn('前次交易日資料不足',vix.render_vix_card(report))

    def test_invalid_snapshot_html_falls_back_safely(self):
        result = vix.render_vix_card({'date':'<script>', 'value':'bad', 'age_days':0})
        self.assertIn('本次未取得可核對的 VIX 資料',result)
        self.assertNotIn('<script>',result)

    def test_fetch_failure_is_nonfatal(self):
        with patch('yfinance.Ticker',side_effect=ConnectionError('offline')):
            self.assertIsNone(vix.fetch_vix(ASOF))


if __name__ == '__main__':
    unittest.main()
