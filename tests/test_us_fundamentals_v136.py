"""Offline tests for cautious US quarter financials prototype."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, Mock

import pandas as pd

import us_fundamentals_v136 as us

ASOF=datetime.fromisoformat("2026-11-26T00:15:00+08:00")


def statement(quarters, revenue, net_income):
    return pd.DataFrame(
        {pd.Timestamp(day): [rev, inc]
         for day,rev,inc in zip(quarters,revenue,net_income)},
        index=["Total Revenue","Net Income"],
    )


class UsFundamentalsTests(unittest.TestCase):
    def test_match_same_company_prior_year_quarter(self):
        df=statement(
            ["2026-09-30","2026-06-30","2025-09-30"],
            [120,110,100],[15,8,10],
        )
        r=us.parse_statement("NVDA",df,ASOF)
        self.assertEqual(r["quarter_end"],"2026-09-30")
        self.assertEqual(r["prior_end"],"2025-09-30")
        self.assertEqual(r["revenue_yoy"],20)
        self.assertEqual(r["margin"],12.5)

    def test_only_four_quarters_does_not_fabricate_year_ago(self):
        df=statement(["2026-09-30","2026-06-30","2026-03-31","2025-12-31"],
                     [120,110,100,90],[12,11,10,9])
        r=us.parse_statement("AAPL",df,ASOF)
        self.assertIsNone(r["revenue_yoy"])
        self.assertEqual(r["margin"],10)
        self.assertIn("—",us.render_pilot([r]))

    def test_no_missing_lineitem_substitution(self):
        df=statement(["2026-09-30"],[110],[10])
        df=df.rename(index={"Net Income":"Net Income Common Stockholders"})
        self.assertIsNone(us.parse_statement("MSFT",df,ASOF))
        df=df.rename(index={"Total Revenue":"Operating Revenue"})
        self.assertIsNone(us.parse_statement("MSFT",df,ASOF))

    def test_future_period_and_invalid_values_ignored(self):
        df=statement(["2026-12-31","2026-09-30","2025-09-30"],
                     [999,120,100],[10,12,10])
        self.assertEqual(us.parse_statement("META",df,ASOF)["quarter_end"],"2026-09-30")
        zero=statement(["2026-09-30"],[0],[10])
        self.assertIsNone(us.parse_statement("META",zero,ASOF))

    def test_not_claimed_to_be_sec_verified_or_investment_rank(self):
        html=us.render_pilot([{"symbol":"XOM","quarter_end":"2026-09-30",
                              "revenue_yoy":-3.5,"margin":7.2,"age_days":57}])
        self.assertIn("未逐筆核對 SEC 原始申報",html)
        self.assertIn("有資料 1/8",html)
        self.assertIn("-3.5%",html)
        self.assertIn("+7.2%",html)
        self.assertEqual(html.count('class="uf136-company"'),8)
        self.assertNotIn("100 分",html.split("研究樣本")[0] if "研究樣本" in html else "")
        self.assertIn("SEC EDGAR",html)
        self.assertNotIn("買入建議",html)

    def test_stale_and_missing_data_explicit(self):
        html=us.render_pilot([{"symbol":"LLY","quarter_end":"2025-09-30",
                              "revenue_yoy":None,"margin":None,"age_days":420}])
        self.assertIn("較舊，請核對公告",html)
        self.assertIn("本次季度財報缺漏",html)

    def test_broker_quote_mock_or_network_failure_is_nonfatal(self):
        with patch("yfinance.Ticker",side_effect=ConnectionError("offline")):
            rows=us.fetch_pilot(ASOF)
        self.assertEqual(len(rows),8)
        self.assertTrue(all(not r.get("quarter_end") for r in rows))

    def test_mount_only_with_us_hours_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"index.html"
            path.write_text(
                '<!doctype html><html><head></head><body>'
                '<style>/* us-hours-v135 */</style></body></html>',
                encoding="utf-8",
            )
            us.install_us_fundamentals(path,[])
            first=path.read_text(encoding="utf-8")
            self.assertIn("/* stock-radar-us-fundamentals-v136 */",first)
            self.assertIn("panel-us",first)
            us.install_us_fundamentals(path,[])
            self.assertEqual(path.read_text(encoding="utf-8"),first)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.html"
            content="<html><head></head><body></body></html>"
            path.write_text(content,encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"缺少美股時段入口"):
                us.install_us_fundamentals(path,[])
            self.assertEqual(content,path.read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
