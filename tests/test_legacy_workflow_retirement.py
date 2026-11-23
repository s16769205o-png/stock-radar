"""Safety contract: retired upgrade workflows cannot start old installers.

The main daily radar.yml schedule and its fundamental data collectors remain
enabled; this test never executes or schedules a production task.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
LEGACY = {
    'famous-v119.yml': ('upgrade', 'deploy'),
    'maintenance-v117(1).yml': ('install_and_audit', 'deploy'),
    'profit-v110.yml': ('upgrade', 'publish'),
    'readiness-v113.yml': ('upgrade', 'publish'),
    'revenue-v19.yml': ('upgrade', 'publish'),
}


class LegacyWorkflowRetirementTests(unittest.TestCase):
    def test_retired_workflows_have_no_auto_triggers_and_no_executable_jobs(self):
        for filename, jobs in LEGACY.items():
            with self.subTest(workflow=filename):
                text = (ROOT / '.github' / 'workflows' / filename).read_text(encoding='utf-8')
                trigger = text.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
                self.assertIn('workflow_dispatch:', trigger)
                self.assertNotRegex(trigger, r'(?m)^  (schedule|push|pull_request):')
                self.assertIn('permissions:\n  contents: read', text)
                self.assertNotIn('contents: write', text)
                self.assertNotIn('pages: write', text)
                self.assertNotIn('actions: write', text)
                for job in jobs:
                    self.assertRegex(
                        text,
                        r'(?m)^  ' + re.escape(job)
                        + r':\s*\n    if: \$\{\{ false \}\}',
                    )

    def test_current_daily_scanner_keeps_its_schedule_and_source_modules(self):
        workflow = (ROOT / '.github' / 'workflows' / 'radar.yml').read_text(encoding='utf-8')
        self.assertIn('schedule:', workflow)
        self.assertIn('python radar.py', workflow)
        self.assertIn('data/monthly_revenue.csv', workflow)
        self.assertIn('data/quarterly_profit.csv', workflow)
        radar = (ROOT / 'radar.py').read_text(encoding='utf-8')
        self.assertIn('monthly_revenue_section(', radar)
        self.assertIn('quarterly_profit_section(', radar)
