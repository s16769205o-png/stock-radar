"""Offline tests for four-file staged publication (history, sources, HTML)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import radar
import revenue
import profitability
import industry_readiness
import sector_dashboard_v126
from snapshot_transaction_v132 import staged_official_archives


class SnapshotTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        data = self.root / 'data'
        data.mkdir()
        self.monthly = data / 'monthly_revenue.csv'
        self.quarterly = data / 'quarterly_profit.csv'
        self.history = data / 'history.csv'
        self.site = self.root / 'index.html'
        self.stage_site = self.root / 'index.stage.html'
        self.monthly.write_bytes(b'ORIGINAL MONTHLY')
        self.quarterly.write_bytes(b'ORIGINAL QUARTERLY')
        self.history.write_bytes(b'ORIGINAL HISTORY')
        self.site.write_bytes(b'ORIGINAL SITE')
        self.patch_history = patch.object(radar, 'DATA_FILE', self.history)
        self.patch_site = patch.object(radar, 'SITE_FILE', self.site)
        self.patch_history.start()
        self.patch_site.start()
        self.addCleanup(self.patch_history.stop)
        self.addCleanup(self.patch_site.stop)

    def original(self):
        return {
            path: path.read_bytes()
            for path in (self.monthly, self.quarterly, self.history, self.site)
        }

    def assert_same(self, old):
        self.assertEqual(self.original(), old)
        self.assertFalse((self.root / 'data/monthly_revenue.csv.stage').exists())
        self.assertFalse((self.root / 'data/quarterly_profit.csv.stage').exists())

    def test_stage_redirects_every_reader_and_restores_module_constants(self):
        self.assertNotEqual(revenue.ARCHIVE, self.monthly)
        orig_revenue, orig_profit, orig_sector = (
            revenue.ARCHIVE, profitability.ARCHIVE, sector_dashboard_v126.REVENUE_FILE
        )
        with staged_official_archives(self.root) as pairs:
            self.assertEqual(revenue.ARCHIVE, self.monthly.with_name('monthly_revenue.csv.stage'))
            self.assertEqual(profitability.ARCHIVE, self.quarterly.with_name('quarterly_profit.csv.stage'))
            self.assertEqual(industry_readiness.MONTHLY, revenue.ARCHIVE)
            self.assertEqual(sector_dashboard_v126.REVENUE_FILE, revenue.ARCHIVE)
            self.assertEqual(len(pairs), 2)
            self.assertEqual(pairs[0][0].read_bytes(), b'ORIGINAL MONTHLY')
            self.assertEqual(pairs[1][0].read_bytes(), b'ORIGINAL QUARTERLY')
        self.assertEqual(revenue.ARCHIVE, orig_revenue)
        self.assertEqual(profitability.ARCHIVE, orig_profit)
        self.assertEqual(sector_dashboard_v126.REVENUE_FILE, orig_sector)

    def test_late_render_failure_cleans_stages_and_preserves_originals(self):
        old = self.original()
        with self.assertRaisesRegex(RuntimeError, 'simulated html failure'):
            with staged_official_archives(self.root) as pairs:
                for stage, _ in pairs:
                    stage.write_bytes(b'UNVERIFIED UPDATED SOURCE')
                raise RuntimeError('simulated html failure')
        self.assert_same(old)

    def test_four_file_publish_success(self):
        self.stage_site.write_bytes(b'NEW SITE')
        with staged_official_archives(self.root) as pairs:
            for stage, final in pairs:
                stage.write_bytes(b'UPDATED '+final.name.encode())
            radar.publish_verified_report([], self.stage_site, pairs)
        self.assertEqual(self.site.read_bytes(), b'NEW SITE')
        self.assertIn(b'\xef\xbb\xbf', self.history.read_bytes())
        self.assertEqual(self.monthly.read_bytes(), b'UPDATED monthly_revenue.csv')
        self.assertEqual(self.quarterly.read_bytes(), b'UPDATED quarterly_profit.csv')
        self.assertFalse(self.stage_site.exists())
        self.assertFalse(list(self.root.rglob('*.rollback.*')))

    def test_site_replace_failure_rolls_back_all_four_files(self):
        old = self.original()
        self.stage_site.write_bytes(b'NEW SITE')
        original_replace = Path.replace

        def fail_site(source, target):
            if Path(source) == self.stage_site and Path(target) == self.site:
                raise OSError('last step failed')
            return original_replace(source, target)

        with staged_official_archives(self.root) as pairs:
            for stage, _ in pairs:
                stage.write_bytes(b'NEW SOURCE')
            with patch.object(Path, 'replace', autospec=True, side_effect=fail_site):
                with self.assertRaisesRegex(OSError, 'last step failed'):
                    radar.publish_verified_report([], self.stage_site, pairs)
        self.assert_same(old)
        self.assertFalse(list(self.root.rglob('*.rollback.*')))

    def test_missing_new_source_keeps_absent_when_official_fetch_unavailable(self):
        self.monthly.unlink()
        self.quarterly.unlink()
        self.stage_site.write_bytes(b'NEW SITE')
        with staged_official_archives(self.root) as pairs:
            self.assertFalse(pairs[0][0].exists())
            self.assertFalse(pairs[1][0].exists())
            radar.publish_verified_report([], self.stage_site, pairs)
        self.assertFalse(self.monthly.exists())
        self.assertFalse(self.quarterly.exists())
        self.assertEqual(self.site.read_bytes(), b'NEW SITE')


if __name__ == '__main__':
    unittest.main()
