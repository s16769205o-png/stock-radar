"""Regression tests for two-file publication safety. No live network or market data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import radar


class SafePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = self.root / 'data' / 'history.csv'
        self.history.parent.mkdir(parents=True)
        self.site = self.root / 'index.html'
        self.stage = self.root / 'index.stage.html'
        self.history.write_bytes(b'ORIGINAL HISTORY')
        self.site.write_bytes(b'ORIGINAL SITE')
        self.p1 = patch.object(radar, 'DATA_FILE', self.history)
        self.p2 = patch.object(radar, 'SITE_FILE', self.site)
        self.p1.start()
        self.p2.start()
        self.addCleanup(self.p1.stop)
        self.addCleanup(self.p2.stop)

    def test_success_replaces_both_files_and_cleans_stages(self):
        self.stage.write_bytes(b'NEW SITE')
        radar.publish_verified_report([], self.stage)
        self.assertIn(b'\xef\xbb\xbf', self.history.read_bytes())
        self.assertIn('交易日期', self.history.read_text(encoding='utf-8-sig'))
        self.assertEqual(self.site.read_bytes(), b'NEW SITE')
        self.assertFalse(self.stage.exists())
        self.assertFalse(self.history.with_name('history.csv.stage').exists())

    def test_history_stage_write_failure_keeps_existing_files(self):
        self.stage.write_bytes(b'NEW SITE')
        with patch.object(radar, 'save_history', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                radar.publish_verified_report([], self.stage)
        self.assertEqual(self.history.read_bytes(), b'ORIGINAL HISTORY')
        self.assertEqual(self.site.read_bytes(), b'ORIGINAL SITE')

    def test_second_replace_failure_restores_first_file(self):
        self.stage.write_bytes(b'NEW SITE')
        original_replace = Path.replace

        def fail_site_replace(path, target):
            if Path(path) == self.stage and Path(target) == self.site:
                raise OSError('site publication failed')
            return original_replace(path, target)

        with patch.object(Path, 'replace', autospec=True, side_effect=fail_site_replace):
            with self.assertRaisesRegex(OSError, 'site publication failed'):
                radar.publish_verified_report([], self.stage)
        self.assertEqual(self.history.read_bytes(), b'ORIGINAL HISTORY')
        self.assertEqual(self.site.read_bytes(), b'ORIGINAL SITE')
        self.assertFalse(self.history.with_name('history.csv.stage').exists())
        self.assertFalse(list(self.root.rglob('*.rollback.*')))

    def test_render_failure_does_not_publish_any_file(self):
        self.stage.write_bytes(b'partial webpage')
        with patch.object(radar, 'render', side_effect=RuntimeError('HTML rendering failed')):
            with self.assertRaisesRegex(RuntimeError, 'HTML rendering failed'):
                radar.render([], [], [], {}, {}, [], publish=False)
        self.assertEqual(self.history.read_bytes(), b'ORIGINAL HISTORY')
        self.assertEqual(self.site.read_bytes(), b'ORIGINAL SITE')
