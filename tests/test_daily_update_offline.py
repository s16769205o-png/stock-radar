import csv
import io
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd

import history_lab_v129 as lab
import institutional_flow
import profitability
import radar
import revenue
import sector_indices
import world_events_v125
from trading_sessions import last_completed_session, recent_sessions


LEGACY_PRICE_DAY = '2026-11-20'
SCAN_TIME = datetime.fromisoformat('2026-11-23T16:40:00+08:00')
MONTHLY = 'data/monthly_revenue.csv'
QUARTERLY = 'data/quarterly_profit.csv'


def archived_signals(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return {(event['price_day'], event['symbol'], event['kind']): event
                for event in lab._load(csv.DictReader(stream))}


class DailyUpdateOfflineTest(unittest.TestCase):
    def test_daily_update_publishes_complete_fixture_and_leaves_files_when_quotes_are_missing(self):
        days = {market: last_completed_session(market, SCAN_TIME) for market in radar.UNIVERSE}
        quotes = {}
        for market, symbols in radar.UNIVERSE.items():
            dates = pd.to_datetime(recent_sessions(market, days[market], 85))
            frame = pd.DataFrame({'Close': 100.0, 'Volume': 1000}, index=dates)
            for symbol in (*symbols, radar.BENCHMARKS[market][0]):
                quotes[symbol] = frame
        quotes.update({symbol: quotes['SPY'] for symbol in sector_indices.ETF_INFO})

        code = '2330'
        monthly = [{'公司代號': code, '資料年月': '202610',
                    '營業收入-去年同月增減(%)': '10'}]
        quarterly = [{'公司代號': code, '年度': '2026', '季別': '3',
                      '營業收入': '1000', '營業利益（損失）': '-10'}]
        flows = {symbol.split('.')[0]: [1000, 2000, 3000, 6000]
                 for symbol in radar.UNIVERSE['台股']}
        tw_indices = {'date': days['台股'], 'rows': [
            {'name': '測試指數', 'close': 100, 'day_pct': 1, 'week_pct': 2}]}

        with TemporaryDirectory() as folder, ExitStack() as patches:
            root = Path(folder)
            history = root / 'data/history.csv'
            site = root / 'index.html'
            history.parent.mkdir()
            # Freeze the historical input at the legacy archive boundary.
            with (radar.DATA_FILE.open(encoding='utf-8-sig', newline='') as source,
                  history.open('w', encoding='utf-8-sig', newline='') as target):
                rows = csv.DictReader(source)
                writer = csv.DictWriter(target, fieldnames=rows.fieldnames)
                writer.writeheader()
                writer.writerows(row for row in rows if row['交易日期'] <= LEGACY_PRICE_DAY)
            site.write_text('原網站測試快照', encoding='utf-8')
            original = archived_signals(history)
            self.assertEqual(len(original), 36)

            for name, value in {'ROOT': root, 'DATA_FILE': history, 'SITE_FILE': site}.items():
                patches.enter_context(patch.object(radar, name, value))
            for module, attributes in {
                'revenue': {'ARCHIVE': MONTHLY},
                'profitability': {'ARCHIVE': QUARTERLY},
                'industry_lens': {'MONTHLY': MONTHLY, 'QUARTERLY': QUARTERLY},
                'industry_briefs': {'MONTHLY': MONTHLY, 'QUARTERLY': QUARTERLY},
                'industry_readiness': {'MONTHLY': MONTHLY, 'QUARTERLY': QUARTERLY},
                'fundamental_crosscheck': {'MONTHLY': MONTHLY, 'QUARTERLY': QUARTERLY},
                'sector_evidence_v123': {'REVENUE': MONTHLY, 'PROFIT': QUARTERLY},
                'sector_dashboard_v126': {'REVENUE_FILE': MONTHLY, 'PROFIT_FILE': QUARTERLY},
                'sector_treasure_v127': {'REVENUE_FILE': MONTHLY, 'PROFIT_FILE': QUARTERLY},
                'sector_diagnostics_v128': {'REVENUE_FILE': MONTHLY, 'PROFIT_FILE': QUARTERLY},
                'famous_13f': {'CACHE': 'data/berkshire_13f.json'},
                'system_health': {'REPORT': 'data/maintenance_status.json'},
            }.items():
                for name, relative_path in attributes.items():
                    patches.enter_context(patch.object(import_module(module), name, root / relative_path))

            # Stub data acquisition only. Keep scoring, rendering and persistence real.
            for module in (radar, lab, profitability, institutional_flow):
                clock = Mock(wraps=datetime)
                clock.now.return_value = SCAN_TIME
                patches.enter_context(patch.object(module, 'datetime', clock))
            patches.enter_context(patch.object(radar.time, 'sleep'))
            patches.enter_context(patch('socket.socket.connect', side_effect=AssertionError('network access')))
            patches.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('network access')))
            patches.enter_context(patch.object(radar.yf, 'download', side_effect=lambda tickers, **_:
                                               pd.concat({symbol: quotes[symbol] for symbol in tickers}, axis=1)))
            patches.enter_context(patch.object(radar.yf, 'Ticker', side_effect=lambda symbol:
                                               Mock(history=Mock(return_value=quotes[symbol]))))
            patches.enter_context(patch.object(revenue, '_fetch_rows', return_value=(monthly, 'fixture', None)))
            patches.enter_context(patch.object(profitability, '_fetch_official', return_value=quarterly))
            patches.enter_context(patch.object(institutional_flow, 'fetch_t86', return_value=flows))
            patches.enter_context(patch.object(sector_indices, 'fetch_twse', return_value=tw_indices))
            patches.enter_context(patch.object(world_events_v125, '_fetch', side_effect=lambda source, _:
                                               {'source': source, 'events': [], 'error': ''}))
            patches.enter_context(redirect_stdout(io.StringIO()))
            radar.main()

            page = site.read_text(encoding='utf-8')
            self.assertEqual(page.count('<article class="card"'), 100)
            self.assertIn('前瞻訊號 1 筆，舊制封存 36 筆', page)
            self.assertIn('訊號有效性驗證室・1.30', page)
            saved = archived_signals(history)
            self.assertEqual({key: saved[key] for key in original}, original)
            new = saved[(days['台股'], f'{code}.TW', 'revenue_margin')]
            self.assertEqual(new['start_date'], '2026-11-24')
            self.assertEqual(new['first_seen'], SCAN_TIME.isoformat())
            self.assertTrue((root / MONTHLY).is_file())
            self.assertTrue((root / QUARTERLY).is_file())

            outputs = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}

            # The market gate passes, but HTML rendering fails. Neither the
            # existing site nor historical evidence may be changed.
            with patch.object(radar, 'render', side_effect=RuntimeError('simulated render failure')):
                with self.assertRaisesRegex(RuntimeError, 'simulated render failure'):
                    radar.main()
            self.assertEqual(
                {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()},
                outputs,
            )

            for symbol in ('2330.TW', 'SPY'):
                with self.subTest(missing_session=symbol):
                    complete = quotes[symbol]
                    quotes[symbol] = complete.drop(complete.index[-10])
                    try:
                        with self.assertRaisesRegex(RuntimeError, '行情驗收未通過'):
                            radar.main()
                    finally:
                        quotes[symbol] = complete
                    self.assertEqual(
                        {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()},
                        outputs,
                    )
