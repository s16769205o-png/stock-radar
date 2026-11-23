"""Sector UI consolidation: distinct source scopes, one visible price-strength entry."""
import unittest

import radar
import sector_indices


class SectorViewConsolidationTests(unittest.TestCase):
    def test_one_market_research_section_never_contains_other_market(self):
        tw = radar.industry_strength_section([], {}, {}, markets=('台股',))
        us = radar.industry_strength_section([], {}, {}, markets=('美股',))
        self.assertIn('🏗️ 台股研究池｜族群強弱', tw)
        self.assertNotIn('🏗️ 美股研究池｜族群強弱', tw)
        self.assertIn('🏗️ 美股研究池｜族群強弱', us)
        self.assertNotIn('🏗️ 台股研究池｜族群強弱', us)

    def test_official_tw_index_keeps_tw_research_detail_folded(self):
        fake = '<h2>🏗️ 台股研究池｜族群強弱</h2><p>樣本研究資料</p>'
        tw, us = sector_indices.render_sections(
            {'date': '2026-11-23', 'prior': '2026-11-16',
             'rows':[{'name':'電子類指數','close':400.0,'day_pct':1.5,'week_pct':2.3}]},
            {'rows':[], 'error':'test fixture'},
            tw_research_html=fake,
        )
        self.assertEqual(tw.count('id="sector-index-tw"'), 1)
        self.assertIn('證交所', tw)
        self.assertIn('class="sector-detail sector-research-extra"', tw)
        self.assertIn('🏗️ 台股研究池｜族群強弱', tw)
        self.assertIn('展開自選50檔族群技術比較', tw)
        self.assertNotIn('台股研究池｜族群強弱', us)

    def test_official_api_missing_does_not_hide_separate_research_evidence(self):
        tw, _ = sector_indices.render_sections(
            {'rows':[], 'error':'network unavailable'},
            {'rows':[], 'error':'network unavailable'},
            tw_research_html='<h2>🏗️ 台股研究池｜族群強弱</h2>',
        )
        self.assertIn('目前無法自動取得證交所產業指數', tw)
        self.assertIn('🏗️ 台股研究池｜族群強弱', tw)

    def test_empty_research_argument_keeps_backward_compatible_index(self):
        tw, us = sector_indices.render_sections(
            {'rows':[], 'error':'fixture'}, {'rows':[], 'error':'fixture'},
        )
        self.assertNotIn('sector-research-extra', tw)
        self.assertIn('id="sector-index-us"', us)


if __name__ == '__main__':
    unittest.main()
