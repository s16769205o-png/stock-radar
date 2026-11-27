"""No market-data recomputation and no holdings leakage in quick deploy."""
import tempfile
import unittest
from pathlib import Path

from risk_house_release import MARKER, build_static_release

REPO=Path(__file__).resolve().parents[1]


class FastPrivateDeployTests(unittest.TestCase):
    def fixture(self, root):
        (root/"data").mkdir()
        page='<!doctype html><html><head></head><body>STOCK RESEARCH LAB · 1.38'
        page+='/* stock-radar-villa-1.18 */<section id="panel-kitchen"></section></body></html>'
        (root/"index.html").write_text(page,encoding="utf-8")
        (root/"holdings-risk.html").write_bytes((REPO/"holdings-risk.html").read_bytes())
        (root/"risk_house_v1.js").write_bytes((REPO/"risk_house_v1.js").read_bytes())
        for name in ("history.csv","monthly_revenue.csv","quarterly_profit.csv"):
            (root/"data"/name).write_text("header\npublic-data\n",encoding="utf-8")
        (root/"my-private-holdings.json").write_text('{"secret":"never publish"}')
        return page

    def test_release_contains_only_allowlisted_public_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);original=self.fixture(root)
            build_static_release(root,root/"_site")
            names=sorted(str(x.relative_to(root/"_site")) for x in
                         (root/"_site").rglob("*") if x.is_file())
            self.assertEqual(names,[
                "data/history.csv","data/monthly_revenue.csv",
                "data/quarterly_profit.csv","holdings-risk.html",
                "index.html","risk_house_v1.js",
            ])
            result=(root/"_site"/"index.html").read_text(encoding="utf-8")
            self.assertIn(MARKER,result)
            self.assertIn("./holdings-risk.html",result)
            self.assertNotIn("never publish",result)
            self.assertEqual((root/"index.html").read_text(encoding="utf-8"),original)

    def test_original_market_csv_bytes_unmodified(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            before=(root/"data"/"history.csv").read_bytes()
            build_static_release(root,root/"_site")
            self.assertEqual(before,(root/"data"/"history.csv").read_bytes())
            self.assertEqual(before,(root/"_site"/"data/history.csv").read_bytes())

    def test_refuse_broken_report_without_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            (root/"index.html").write_text("<!doctype html>broken</html>")
            with self.assertRaisesRegex(ValueError,"既有已驗收"):
                build_static_release(root,root/"_site")
            self.assertFalse((root/"_site"/"index.html").exists())

    def test_refuse_missing_app_without_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            (root/"risk_house_v1.js").write_text("broken")
            with self.assertRaisesRegex(ValueError,"程式不完整"):
                build_static_release(root,root/"_site")
            self.assertFalse((root/"_site"/"index.html").exists())

    def test_skip_entry_insertion_if_already_present(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            file=root/"index.html"
            original=file.read_text(encoding="utf-8").replace(
                "</body>",'<a href="./holdings-risk.html">風控屋</a></body>')
            file.write_text(original,encoding="utf-8")
            build_static_release(root,root/"_site")
            self.assertEqual(
                (root/"_site"/"index.html").read_text(encoding="utf-8"),
                original,
            )


if __name__=="__main__":
    unittest.main()
