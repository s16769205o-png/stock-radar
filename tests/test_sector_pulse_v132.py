"""Offline proof that 1.32 describes evidence without fabricating scores."""
import unittest
from unittest.mock import patch

import industry_readiness as readiness
from sector_pulse_v132 import analyze, classify, render_section, sector_pulse_section


class SectorPulseTests(unittest.TestCase):
    def setUp(self):
        self.universe = {'台股': [], '美股': ['NVDA']}
        self.industry = {}
        self.monthly = []
        self.quarterly = []

    def add_group(self, group, codes, old_growth, new_growth, old_margin, new_margin,
                  active_codes=None, paired_codes=None):
        active_codes = set(codes if active_codes is None else active_codes)
        paired_codes = set(codes if paired_codes is None else paired_codes)
        for c in codes:
            stock = c + '.TW'
            self.universe['台股'].append(stock)
            self.industry[stock] = group
            if c in active_codes:
                self.monthly.append({
                    '公司代號': c, '資料年月': '2026-10', '年增率': str(new_growth),
                })
                self.quarterly.append({
                    '公司代號': c, '季度': '2026Q3',
                    '累計營業利益率%': str(new_margin),
                })
            if c in paired_codes:
                self.monthly.append({
                    '公司代號': c, '資料年月': '2026-09', '年增率': str(old_growth),
                })
                self.quarterly.append({
                    '公司代號': c, '季度': '2025Q3',
                    '累計營業利益率%': str(old_margin),
                })

    def data(self):
        return analyze(self.universe, self.industry, self.monthly, self.quarterly)

    def by_name(self, name):
        return next(r for r in self.data()['rows'] if r['產業'] == name)

    def test_three_unscored_direction_labels_and_exact_same_company_deltas(self):
        self.add_group('成長改善', ['1111','1112','1113','1114'], 4, 11, 5, 8)
        self.add_group('成長放緩', ['2111','2112','2113','2114'], 12, 3, 8, 6)
        self.add_group('方向分歧', ['3111','3112','3113','3114'], 4, 11, 8, 6)
        self.assertEqual(self.by_name('成長改善')['研判'], '兩項同向改善')
        self.assertEqual(self.by_name('成長放緩')['研判'], '兩項同向放緩')
        self.assertEqual(self.by_name('方向分歧')['研判'], '營收與獲利分歧')
        good = self.by_name('成長改善')
        self.assertEqual(good['月營收年增變化pp'], 7)
        self.assertEqual(good['去年同季累計營利率變化pp'], 3)
        report = self.data()
        self.assertEqual(report['month'], '2026-10')
        self.assertEqual(report['previous_month'], '2026-09')
        self.assertEqual(report['quarter'], '2026Q3')
        self.assertEqual(report['year_ago_quarter'], '2025Q3')
        page = render_section(report)
        for phrase in ('兩項同向改善','兩項同向放緩','營收與獲利分歧',
                       '2026-10', '2025Q3', '+7.0 百分點'):
            self.assertIn(phrase, page)
        self.assertNotIn('/100', page)
        self.assertNotIn('/30', page)

    def test_missing_monthly_pair_is_unknown_not_negative(self):
        codes = ['1111','1112','1113','1114']
        self.add_group('資料不齊', codes, 3, 12, 3, 9, paired_codes=codes[:2])
        result = self.by_name('資料不齊')
        self.assertEqual(result['研判'], '跨期資料不足')
        self.assertEqual(result['營收配對'], 2)
        self.assertIn('—', render_section(self.data()))
        self.assertNotIn('兩項同向改善', [result['研判']])

    def test_75_percent_coverage_prevents_false_success(self):
        codes = ['1111','1112','1113','1114','1115','1116']
        self.add_group('不足七成五', codes, 0, 10, 0, 10,
                       active_codes=codes[:4], paired_codes=codes)
        result = self.by_name('不足七成五')
        self.assertEqual(result['同時有數據'], 4)
        self.assertEqual(result['研判'], '最新資料不足')

    def test_three_of_four_is_enough_for_comparison(self):
        codes = ['1111','1112','1113','1114']
        self.add_group('恰好七成五', codes, 0, 10, 0, 10,
                       active_codes=codes[:3], paired_codes=codes)
        self.assertEqual(self.by_name('恰好七成五')['研判'], '兩項同向改善')

    def test_tiny_sector_and_financial_sector_cannot_be_misread_as_comparable(self):
        self.add_group('小樣本', ['1111','1112'], 0, 5, 0, 5)
        self.add_group('金融', ['2111','2112','2113','2114'], 0, 5, 0, 5)
        result = self.data()
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['研判'], '樣本太少')
        self.assertNotIn('金融', render_section(result))

    def test_zero_changes_and_unavailable_history(self):
        self.add_group('持平', ['1111','1112','1113'], 10, 10, 5, 5)
        self.assertEqual(self.by_name('持平')['研判'], '變化持平／混合')
        no_prior = [r for r in self.quarterly if r['季度'] != '2025Q3']
        result = analyze(self.universe,self.industry,self.monthly,no_prior)
        self.assertEqual(result['rows'][0]['研判'], '跨期資料不足')
        self.assertNotIn('兩項同向放緩', [x['研判'] for x in result['rows']])

    def test_html_escapes_untrusted_sector_labels(self):
        malicious = '<img src=x onerror=alert(1)>'
        self.add_group(malicious, ['1111','1112','1113'], 2, 8, 1, 4)
        page = render_section(self.data())
        self.assertNotIn(malicious, page)
        self.assertIn('&lt;img', page)
        self.assertIn('id="sector-pulse-v132"', page)

    def test_source_render_uses_archived_inputs_and_does_not_fetch(self):
        self.add_group('測試產業', ['1111','1112','1113'], 2, 8, 1, 4)
        with patch.object(readiness, '_load', side_effect=[self.monthly, self.quarterly]) as load:
            html = sector_pulse_section(self.universe, self.industry)
        self.assertEqual(load.call_count, 2)
        self.assertIn('兩項同向改善', html)


if __name__ == '__main__':
    unittest.main()
