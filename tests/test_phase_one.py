import csv
import json
import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

import history_lab_v129 as lab
import radar
import signal_validation_v130 as validation
from trading_sessions import calendar_for, last_completed_session, session_after


OBSERVED = datetime.fromisoformat('2026-11-22T15:20:55+08:00')
SIGNAL_DAY = '2026-11-20'
START_DAY = '2026-11-23'
SYMBOLS = ('2330.TW', '2454.TW', '2317.TW', '2308.TW')


def prices(values):
    return pd.DataFrame({'Close': list(values.values())},
                        index=pd.to_datetime(list(values)))


def record(symbol, market='台股', day=SIGNAL_DAY):
    return {'市場': market, '股票': symbol, '交易日期': day, '調整收盤價': 100}


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.universe = {'台股': SYMBOLS}
        self.records = [record(symbol) for symbol in SYMBOLS]
        self.history = [dict(row) for row in self.records]
        self.snapshot = {
            'day': SIGNAL_DAY, 'month': '2026-10', 'quarter': '2026Q3',
            'groups': [{'group': '半導體', 'stocks': [
                {'symbol': SYMBOLS[0], 'name': '台積電', 'price': -2, 'yoy': 5, 'margin': 10},
            ]}],
        }
        self.benchmarks = {'台股': prices({SIGNAL_DAY: 100})}

    def measure(self, **kwargs):
        params = dict(now=OBSERVED, research_data=self.snapshot)
        params.update(kwargs)
        return lab.record_and_measure(self.universe, {}, {}, self.records, self.histories,
                                      self.benchmarks, self.history, **params)

    def test_weekend_observation_waits_for_next_session_and_uses_same_window_for_pool(self):
        self.histories = {}
        added = self.measure()
        signal = added['rows'][0]
        self.assertEqual(signal['first_seen'], OBSERVED.isoformat())
        self.assertEqual(signal['price_day'], SIGNAL_DAY)
        self.assertEqual(signal['start_date'], START_DAY)
        self.assertEqual(added['matured'], 0)
        self.assertEqual(self.measure()['new'], 0)

        end = session_after('台股', START_DAY, 5)
        self.histories = {symbol: prices({SIGNAL_DAY: 1, START_DAY: 200, end: 240})
                          for symbol in SYMBOLS}
        self.histories[SYMBOLS[0]] = prices({SIGNAL_DAY: 1, START_DAY: 100, end: 130})
        self.benchmarks['台股'] = prices({SIGNAL_DAY: 1, START_DAY: 100, end: 110})
        later = datetime.fromisoformat(end + 'T17:00:00+08:00')
        result = self.measure(now=later)
        self.assertEqual(result['matured'], 1)
        self.assertEqual(result['rows'][0]['stock_return_5d'], 30)
        self.assertEqual(result['rows'][0]['benchmark_return_5d'], 10)
        self.assertEqual(self.measure(now=later)['matured'], 0)
        report = validation.validate_signals(self.universe, self.history,
                                             self.histories, self.benchmarks)
        control = report['results'][0]['control']
        self.assertEqual(control['start_date'], START_DAY)
        self.assertEqual(control['end_date'], end)
        self.assertEqual(control['pool_median_pct'], 20)
        self.assertEqual(control['signal_minus_pool_pp'], 10)

    def test_missing_entry_quote_is_never_replaced_with_another_date(self):
        self.histories = {}
        self.measure()
        end = session_after('台股', START_DAY, 5)
        self.histories = {SYMBOLS[0]: prices({SIGNAL_DAY: 100, end: 130})}
        self.benchmarks['台股'] = prices({SIGNAL_DAY: 100, START_DAY: 100, end: 110})
        result = self.measure(now=datetime.fromisoformat(end + 'T17:00:00+08:00'))
        self.assertEqual(result['matured'], 0)
        self.assertEqual(lab._status(result['rows'][0], 5, end), 'unavailable')

    def test_missing_end_quote_is_never_shifted_to_next_session(self):
        self.histories = {}
        self.measure()
        later = session_after('台股', START_DAY, 6)
        self.histories = {SYMBOLS[0]: prices({START_DAY: 100, later: 130})}
        self.benchmarks['台股'] = prices({START_DAY: 100, later: 110})
        result = self.measure(now=datetime.fromisoformat(later + 'T17:00:00+08:00'))
        self.assertEqual(result['matured'], 0)
        self.assertEqual(lab._status(result['rows'][0], 5, later), 'unavailable')

    def test_incomplete_stock_pool_cannot_record_signals(self):
        self.records.pop()
        self.histories = {}
        result = self.measure()
        self.assertFalse(result['capture_ok'])
        self.assertEqual(result['rows'], [])

    def load_original_signals(self):
        with radar.DATA_FILE.open(encoding='utf-8-sig', newline='') as handle:
            self.history = [row for row in csv.DictReader(handle)
                            if any(event.get('first_seen') == OBSERVED.isoformat()
                                   for event in json.loads(row[lab.ARCHIVE_FIELD] or '[]'))]
        for row in self.history:
            archived = json.loads(row[lab.ARCHIVE_FIELD])
            row[lab.ARCHIVE_FIELD] = json.dumps(
                [event for event in archived if event.get('first_seen') == OBSERVED.isoformat()])

    def test_existing_36_signals_are_preserved_and_excluded(self):
        self.load_original_signals()
        existing = [row[lab.ARCHIVE_FIELD] for row in self.history]
        self.histories = {}
        self.records = []
        outcome = self.measure()
        self.assertEqual(len(outcome['rows']), 36)
        self.assertEqual(outcome['matured'], 0)
        self.assertEqual([row[lab.ARCHIVE_FIELD] for row in self.history], existing)
        report = validation.validate_signals(radar.UNIVERSE, self.history, {}, self.benchmarks)
        self.assertEqual(report['legacy_events'], 36)
        self.assertEqual(report['total_events'], 0)
        self.assertEqual(report['results'], [])
        self.assertEqual(report['saved_controls'], 0)


    def test_history_lab_renders_the_36_original_signals(self):
        self.load_original_signals()
        with patch.object(lab, 'research_rows', return_value=self.snapshot):
            page = lab.history_lab_section(self.universe, {}, {}, [], {},
                                           self.benchmarks, self.history)
        self.assertIn('前瞻訊號 0 筆，舊制封存 36 筆', page)
        self.assertIn('最近12筆原始線索', page)
        self.assertIn(OBSERVED.isoformat(), page)
        self.assertIn('<div>舊制封存</div>', page)


class StockWindowTests(unittest.TestCase):
    def stock_frame(self, market):
        end = last_completed_session(market, OBSERVED)
        calendar = calendar_for(market)
        dates = calendar.sessions_in_range(session_after(market, end, -64), end)
        frame = prices({day.date().isoformat(): 100 for day in dates})
        return frame.assign(Volume=1000)

    def test_complete_stock_window_accepts_exchange_sessions(self):
        for market, symbols in radar.UNIVERSE.items():
            with self.subTest(market=market):
                frame = self.stock_frame(market)
                row = radar.calculate(frame, market, symbols[0])
                self.assertEqual(row['交易日期'], last_completed_session(market, OBSERVED))
                self.assertEqual(row['MA60'], 100)

    def test_stock_window_rejects_missing_session_even_with_enough_rows(self):
        for market, symbols in radar.UNIVERSE.items():
            frame = self.stock_frame(market)
            missing_day = frame.index[-10]
            missing = frame.drop(missing_day)
            missing_close = frame.copy()
            missing_close.loc[missing_day, 'Close'] = float('nan')
            duplicated = pd.concat([missing, frame.iloc[[-11]]]).sort_index()
            for case, data in [('缺列', missing), ('缺收盤價', missing_close), ('重複交易日', duplicated)]:
                with self.subTest(market=market, case=case):
                    self.assertGreaterEqual(len(data.dropna()), 61)
                    with self.assertRaisesRegex(ValueError, '最近 61 個交易日'):
                        radar.calculate(data, market, symbols[0])


class MarketGateTests(unittest.TestCase):
    def setUp(self):
        self.records = []
        self.benchmarks = {}
        for market, symbols in radar.UNIVERSE.items():
            expected = last_completed_session(market, OBSERVED)
            self.records.extend(record(s, market, expected) for s in symbols)
            calendar = calendar_for(market)
            dates = calendar.sessions_in_range(session_after(market, expected, -60), expected)
            self.benchmarks[market] = prices({day.date().isoformat(): 100 for day in dates})

    def test_valid_different_market_sessions_are_accepted(self):
        scan = datetime.fromisoformat('2026-11-23T16:40:00+08:00')
        self.assertEqual(last_completed_session('台股', scan), '2026-11-23')
        self.assertEqual(last_completed_session('美股', scan), '2026-11-20')
        self.assertEqual(last_completed_session(
            '美股', datetime.fromisoformat('2026-11-26T17:00:00-05:00')), '2026-11-25')
        radar.require_complete_markets(self.records, self.benchmarks, OBSERVED)

    def test_missing_stock_in_either_market_fails(self):
        for market in radar.UNIVERSE:
            with self.subTest(market=market):
                removed = next(row for row in self.records if row['市場'] == market)
                with self.assertRaisesRegex(RuntimeError, market):
                    radar.require_complete_markets(
                        [r for r in self.records if r is not removed], self.benchmarks, OBSERVED)

    def test_stale_or_incomplete_benchmark_fails(self):
        for market in radar.UNIVERSE:
            with self.subTest(market=market):
                for frame in (None, self.benchmarks[market].iloc[:-1],
                              self.benchmarks[market].drop(self.benchmarks[market].index[-2])):
                    with self.assertRaisesRegex(RuntimeError, market + ' 基準'):
                        radar.require_complete_markets(
                            self.records, dict(self.benchmarks, **{market: frame}), OBSERVED)

    def test_main_rejects_mixed_dates_before_any_write_or_render(self):
        self.records[0]['交易日期'] = '2026-11-19'
        frames = [self.benchmarks[market] for market in radar.BENCHMARKS]
        with (patch.object(radar, 'datetime') as clock,
              patch.object(radar, 'latest_snapshot', return_value=(self.records, [], {})),
              patch.object(radar.yf, 'Ticker') as ticker,
              patch.object(radar, 'persist') as persist,
              patch.object(radar, 'render') as render,
              patch.object(radar, 'save_history') as save):
            clock.now.return_value = OBSERVED
            ticker.return_value.history.side_effect = frames
            with self.assertRaisesRegex(RuntimeError, '台股'):
                radar.main()
        persist.assert_not_called()
        render.assert_not_called()
        save.assert_not_called()
