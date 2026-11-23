"""Stage official TWSE source archives before publishing a validated report.

The renderer previously wrote monthly / quarterly snapshots directly to their
committed paths before verify_site(), so a late HTML error left mismatched files.
This context remaps ALL research readers/writers to temporary copies. The
publisher later commits these alongside the HTML and history with rollback.
No network requests, no extra market data, no source-date backfill.
"""
from __future__ import annotations

import importlib
import shutil
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch


READERS = {
    'revenue': {'ARCHIVE': 'monthly'},
    'profitability': {'ARCHIVE': 'quarterly'},
    'industry_readiness': {'MONTHLY': 'monthly', 'QUARTERLY': 'quarterly'},
    'industry_lens': {'MONTHLY': 'monthly', 'QUARTERLY': 'quarterly'},
    'industry_briefs': {'MONTHLY': 'monthly', 'QUARTERLY': 'quarterly'},
    'fundamental_crosscheck': {'MONTHLY': 'monthly', 'QUARTERLY': 'quarterly'},
    'sector_evidence_v123': {'REVENUE': 'monthly', 'PROFIT': 'quarterly'},
    'sector_dashboard_v126': {'REVENUE_FILE': 'monthly', 'PROFIT_FILE': 'quarterly'},
    # These two modules import constants BY VALUE, not dynamically from v126.
    'sector_treasure_v127': {'REVENUE_FILE': 'monthly', 'PROFIT_FILE': 'quarterly'},
    'sector_diagnostics_v128': {'REVENUE_FILE': 'monthly', 'PROFIT_FILE': 'quarterly'},
    'sector_pulse_v132': {},  # Reads via patched industry_readiness.
}


@contextmanager
def staged_official_archives(root: Path):
    """Yield (stage, final) pairs; no live source is touched until publication."""
    data = Path(root) / 'data'
    finals = {
        'monthly': data / 'monthly_revenue.csv',
        'quarterly': data / 'quarterly_profit.csv',
    }
    stages = {name: path.with_name(path.name + '.stage')
              for name, path in finals.items()}
    data.mkdir(parents=True, exist_ok=True)
    # A crash from a PREVIOUS run must not leak unverified staged files.
    for stage in stages.values():
        stage.unlink(missing_ok=True)
    try:
        for name, final in finals.items():
            if final.is_file():
                shutil.copy2(final, stages[name])
        with ExitStack() as patches:
            for module_name, attrs in READERS.items():
                if not attrs:
                    continue
                module = importlib.import_module(module_name)
                for attr, source in attrs.items():
                    patches.enter_context(patch.object(module, attr, stages[source]))
            yield tuple((stages[k], finals[k]) for k in ('monthly', 'quarterly'))
    finally:
        for stage in stages.values():
            stage.unlink(missing_ok=True)
