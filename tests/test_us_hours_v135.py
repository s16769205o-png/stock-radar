"""US session table is informational and independent of stock rankings."""
import tempfile
import unittest
from pathlib import Path

from us_hours_v135 import guide_html, install_us_hours


class UsHoursTests(unittest.TestCase):
    def test_et_to_taipei_summer_and_winter(self):
        page=guide_html()
        for fragment in (
            "09:30–16:00", "21:30–次日04:00", "22:30–次日05:00",
            "08:00–15:50", "09:00–16:50",
        ):
            self.assertIn(fragment,page)
        self.assertIn("不是即時夜盤報價",page)
        self.assertIn("IBKR",page)
        self.assertIn("Nasdaq",page)
        self.assertNotIn("即時成交價",page)
        self.assertNotIn("買進訊號",page)

    def test_install_safe_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/"index.html"
            file.write_text("<html><head></head><body>"
                            "<style>/* stock-radar-villa-1.18 */</style>"
                            "</body></html>",encoding="utf-8")
            install_us_hours(file)
            first=file.read_text(encoding="utf-8")
            self.assertIn("/* us-hours-v135 */",first)
            self.assertIn("us-hours-v135",first)
            self.assertIn("panel-us",first)
            self.assertNotIn("<section id=\"us-hours-v135\"",first)
            install_us_hours(file)
            self.assertEqual(first,file.read_text(encoding="utf-8"))

    def test_bad_structure_fails_without_mutating_file(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/"broken.html"
            original="<html><body><div>no head</div></body></html>"
            file.write_text(original,encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"HTML"):
                install_us_hours(file)
            self.assertEqual(original,file.read_text(encoding="utf-8"))

    def test_missing_tab_script_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/"absent.html"
            original="<html><head></head><body></body></html>"
            file.write_text(original,encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"缺少美股分頁"):
                install_us_hours(file)
            self.assertEqual(original,file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
