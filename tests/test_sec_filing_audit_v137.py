"""SEC XBRL comparison MUST fail closed and never invent a verified badge."""
import unittest
from datetime import datetime
from unittest.mock import patch

import sec_filing_audit_v137 as sec
import us_fundamentals_v136 as us

ASOF=datetime.fromisoformat("2026-11-26T09:00:00+08:00")
THIS="0000123456-26-000001"
OLD="0000123456-25-000001"


def fact(start,end,val,filed,accession,form="10-Q"):
    return {"start":start,"end":end,"val":val,"filed":filed,
            "accn":accession,"form":form,"fy":int(end[:4]),"fp":"Q3"}


def sample():
    curr_r=fact("2026-07-01","2026-09-30",120,"2026-11-04",THIS)
    prev_r=fact("2025-07-01","2025-09-30",100,"2025-11-04",OLD)
    curr_p=fact("2026-07-01","2026-09-30",12,"2026-11-04",THIS)
    prev_p=fact("2025-07-01","2025-09-30",10,"2025-11-04",OLD)
    return {"cik":123456,"entityName":"Example Corp",
            "facts":{"us-gaap":{
              "RevenueFromContractWithCustomerExcludingAssessedTax":
                 {"units":{"USD":[curr_r,prev_r]}},
              "NetIncomeLoss":{"units":{"USD":[curr_p,prev_p]}}
            }}}


def yahoo():
    return {"symbol":"NVDA","quarter_end":"2026-09-30",
            "prior_end":"2025-09-30","revenue_yoy":20.0,
            "margin":10.0,"age_days":57}


class SecCrosscheckTests(unittest.TestCase):
    def test_matching_same_accession_quarter_and_filing_date(self):
        row=sec.compare_sec_facts("NVDA",yahoo(),sample(),ASOF)
        self.assertEqual(row["state"],"matched")
        self.assertEqual(row["filing_date"],"2026-11-04")
        self.assertEqual(row["accession"],THIS)
        self.assertEqual(row["cik"],123456)
        html=us.render_pilot([yahoo()],{"NVDA":row})
        self.assertIn("SEC 10-Q 數字一致",html)
        self.assertIn("SEC 原始申報",html)
        self.assertIn("000012345626000001",html)

    def test_material_mismatch_is_flagged_not_overwritten(self):
        value=yahoo()
        value["revenue_yoy"]=12.0
        row=sec.compare_sec_facts("NVDA",value,sample(),ASOF)
        self.assertEqual(row["state"],"different")
        html=us.render_pilot([value],{"NVDA":row})
        self.assertIn("SEC 與 Yahoo 數字不一致",html)
        self.assertIn("+12.0%",html)  # Never secretly replace with SEC 20%.

    def test_ytd_six_months_rejected_as_quarter(self):
        data=sample()
        metric=data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
        metric[0]["start"]="2026-01-01"
        self.assertEqual(
            sec.compare_sec_facts("NVDA",yahoo(),data,ASOF)["state"],"unverifiable"
        )

    def test_other_filing_accession_rejected(self):
        data=sample()
        data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0]["accn"]="0000123456-26-000002"
        self.assertEqual(sec.compare_sec_facts("NVDA",yahoo(),data,ASOF)["state"],"unverifiable")

    def test_future_filed_fact_does_not_pass_as_of_gate(self):
        data=sample()
        for tags in data["facts"]["us-gaap"].values():
            tags["units"]["USD"][0]["filed"]="2026-12-03"
        self.assertEqual(sec.compare_sec_facts("NVDA",yahoo(),data,ASOF)["state"],"unverifiable")

    def test_annual_10k_cannot_become_unreported_q4(self):
        data=sample()
        for tags in data["facts"]["us-gaap"].values():
            tags["units"]["USD"][0]["form"]="10-K"
        self.assertEqual(sec.compare_sec_facts("NVDA",yahoo(),data,ASOF)["state"],"unverifiable")

    def test_missing_prior_quarter_cannot_fake_growth(self):
        data=sample()
        for tags in data["facts"]["us-gaap"].values():
            tags["units"]["USD"].pop()
        self.assertEqual(sec.compare_sec_facts("NVDA",yahoo(),data,ASOF)["state"],"unverifiable")

    def test_prior_fiscal_date_mismatch_stays_unverified(self):
        y=yahoo()
        y["prior_end"]="2025-10-01"
        self.assertEqual(sec.compare_sec_facts("NVDA",y,sample(),ASOF)["state"],"unverifiable")

    def test_missing_or_invalid_sec_identity_rejected(self):
        data=sample()
        data.pop("entityName")
        self.assertEqual(sec.compare_sec_facts("NVDA",yahoo(),data,ASOF)["state"],"unverifiable")

    def test_default_disabled_makes_zero_external_calls(self):
        with patch.dict("os.environ",{},clear=True), patch.object(sec,"_download_json") as http:
            result=sec.audit_pilot([yahoo()],ASOF)
        self.assertEqual(len(result),8)
        self.assertTrue(all(q["state"]=="disabled" for q in result.values()))
        http.assert_not_called()
        html=us.render_pilot([yahoo()],result)
        self.assertEqual(html.count("SEC 官方核對尚未啟用"),8+0 if False else 8)
        self.assertNotIn("SEC 原始申報</a>",html)

    def test_configured_api_fetch_is_official_and_read_only(self):
        def fake_download(url, useragent):
            self.assertIn("real-contact@example.org",useragent)
            if url==sec.TICKERS_URL:
                return {"0":{"ticker":"NVDA","cik_str":123456}}
            self.assertEqual(url,sec.FACTS_URL.format(123456))
            return sample()
        with patch.dict("os.environ",{"SEC_USER_AGENT":"Test Project real-contact@example.org"},clear=True), \
             patch.object(sec,"_download_json",side_effect=fake_download) as http, \
             patch.object(sec.time,"sleep"):
            result=sec.audit_pilot([yahoo()],ASOF)
        self.assertEqual(result["NVDA"]["state"],"matched")
        self.assertEqual(result["MSFT"]["state"],"unverifiable")
        self.assertEqual(http.call_count,2)

    def test_sec_api_error_never_marks_verification(self):
        with patch.dict("os.environ",{"SEC_USER_AGENT":"Test Project real-contact@example.org"},clear=True), \
             patch.object(sec,"_download_json",side_effect=TimeoutError("offline")):
            result=sec.audit_pilot([yahoo()],ASOF)
        self.assertTrue(all(x["state"]=="unverifiable" for x in result.values()))

    def test_audit_reason_html_escaped(self):
        html=us.render_pilot([yahoo()],{"NVDA":{"state":"unverifiable","reason":"<script>unsafe</script>"}})
        self.assertNotIn("<script>unsafe</script>",html)
        self.assertIn("&lt;script&gt;",html)

    def test_untrusted_filing_link_is_not_rendered(self):
        html=us.render_pilot([yahoo()],{"NVDA":{"state":"matched","cik":123456,
            "accession":'x" onclick="alert(1)'}})
        self.assertNotIn("onclick",html)
        self.assertNotIn("SEC 原始申報</a>",html)


if __name__=="__main__":
    unittest.main()
