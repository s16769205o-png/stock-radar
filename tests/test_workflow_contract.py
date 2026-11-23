"""Offline contract checks for the main daily workflow; no Actions deployment."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'radar.yml'


class PublicationWorkflowContractTest(unittest.TestCase):
    def test_report_and_source_snapshots_share_commit_and_pages_artifact(self):
        workflow = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('group: stock-radar-daily-publish', workflow)
        self.assertIn('cancel-in-progress: false', workflow)
        for filename in ('history.csv', 'monthly_revenue.csv', 'quarterly_profit.csv'):
            self.assertIn('data/' + filename, workflow)
            self.assertIn(
                f'cp data/{filename} _site/data/{filename}', workflow
            )
        self.assertIn(
            'git add index.html data/history.csv data/monthly_revenue.csv data/quarterly_profit.csv',
            workflow
        )
