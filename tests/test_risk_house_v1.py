"""Safety and deployment checks for the separately hosted, client-only risk house."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RiskHouseStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/"holdings-risk.html").read_text(encoding="utf-8")
        cls.js=(ROOT/"risk_house_v1.js").read_text(encoding="utf-8")
        cls.workflow=(ROOT/".github/workflows/radar.yml").read_text(encoding="utf-8")
        cls.kitchen=(ROOT/"villa_hub.py").read_text(encoding="utf-8")

    def test_separate_page_and_kitchen_link(self):
        self.assertIn('<title>🛡️ 小G持股風控屋',self.html)
        self.assertIn('src="./risk_house_v1.js"',self.html)
        self.assertIn('href="./holdings-risk.html"',self.kitchen)
        self.assertIn('risk_house_v1.js',self.workflow)
        self.assertIn('cp holdings-risk.html _site/holdings-risk.html',self.workflow)

    def test_client_storage_and_kitchen_import_not_public_accounts(self):
        self.assertIn('soso-stock-radar-holdings-v1',self.js)
        self.assertIn('soso-stock-radar-watchlist-v1',self.js)
        self.assertIn('soso-risk-house-v1',self.js)
        self.assertIn("m.status!==\"holding\"",self.js)
        self.assertIn('localStorage.setItem',self.js)
        self.assertNotIn('fetch(',self.js)
        self.assertNotIn('XMLHttpRequest',self.js)
        self.assertNotIn('sendBeacon',self.js)
        self.assertNotIn('WebSocket',self.js)
        self.assertNotIn('navigator.clipboard',self.js)
        self.assertNotIn('new Image(',self.js)

    def test_unverified_prices_never_act_as_sell_orders(self):
        self.assertIn('價格日期',self.html)
        self.assertIn('自訂單檔比重上限',self.html)
        self.assertIn('自訂從高點回撤警報',self.html)
        self.assertIn('不會自動交易',self.html)
        self.assertIn('暫停依整體持股比重發出減碼警報',self.js)
        self.assertIn('沒有觸發已設定的警報；不代表資產沒有風險',self.js)
        self.assertNotIn('券商登入',self.html)
        self.assertNotIn('apikey',self.html.lower())

    def test_user_data_added_only_via_text_nodes(self):
        self.assertIn('e.textContent=String(text)',self.js)
        self.assertNotIn('.innerHTML',self.js)
        self.assertNotIn('.outerHTML',self.js)
        self.assertNotIn('eval(',self.js)
        self.assertNotIn('new Function(',self.js)

    def test_current_scanner_and_tickers_not_modified(self):
        # Source is an entirely independent page; it does not change stock pool.
        self.assertNotIn('import radar',self.js)
        self.assertNotIn('data/history.csv',self.js)
        self.assertNotIn('data/monthly_revenue.csv',self.js)
        self.assertNotIn('git push',self.js)
        self.assertIn('render();',self.js)

if __name__ == "__main__":
    unittest.main()
