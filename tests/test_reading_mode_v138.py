"""Offline reading-mode installer tests; no archived stock source changes."""
import tempfile
import unittest
from pathlib import Path
from reading_mode_v138 import install_reading_mode, CSS, SCRIPT


class ReadingModeTests(unittest.TestCase):
    def sample(self):
        return ('<!doctype html><html><head></head><body>'
                '<style>/* stock-radar-villa-1.18 */</style>'
                '<nav id="radar-market-tabs"></nav>'
                '<div id="radar-market-views"></div>'
                '</body></html>')

    def test_works_once_with_existing_five_tab_site(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'index.html'
            path.write_text(self.sample(),encoding='utf-8')
            install_reading_mode(path)
            one=path.read_text(encoding='utf-8')
            self.assertIn('stock-radar-reading-mode-v138-mount',one)
            self.assertIn('read138-overview',one)
            self.assertIn('重點速覽',one)
            self.assertIn('完整研究',one)
            self.assertIn('直接前往',one)
            install_reading_mode(path)
            self.assertEqual(one,path.read_text(encoding='utf-8'))

    def test_original_five_room_structure_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'index.html'
            original=self.sample()
            path.write_text(original,encoding='utf-8')
            install_reading_mode(path)
            result=path.read_text(encoding='utf-8')
            self.assertEqual(result.count('<nav id="radar-market-tabs">'),1)
            self.assertEqual(result.count('</head>'),1)
            self.assertEqual(result.count('</body>'),1)
            self.assertIn('stock-radar-villa-1.18',result)

    def test_bad_structure_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'broken.html'
            before='<html><body>No head</body></html>'
            path.write_text(before,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'HTML'):
                install_reading_mode(path)
            self.assertEqual(before,path.read_text(encoding='utf-8'))

    def test_missing_villa_cannot_create_false_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'broken.html'
            before='<!doctype html><html><head></head><body></body></html>'
            path.write_text(before,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'五分頁'):
                install_reading_mode(path)
            self.assertEqual(before,path.read_text(encoding='utf-8'))

    def test_default_compact_only_overview_and_all_data_recoverable(self):
        self.assertIn("key==='overview'?'focus':'all'",SCRIPT)
        self.assertIn("setMode('all')",SCRIPT)
        self.assertIn("sections[index].scrollIntoView",SCRIPT)
        self.assertIn("section.hidden=hide",SCRIPT)
        self.assertIn("btn.setAttribute('aria-pressed'",SCRIPT)
        self.assertNotIn("removeChild(",SCRIPT)
        self.assertNotIn(".innerHTML=",SCRIPT)
        self.assertIn("option.textContent=",SCRIPT)
        self.assertNotIn("fetch(",SCRIPT)
        self.assertIn("read138",CSS)


if __name__=='__main__':
    unittest.main()
