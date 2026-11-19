"""Best-effort GitHub workflow migration audit for Stock Radar 1.17.

Only disables three explicit obsolete *weekly* workflows. Leaves daily radar,
one-time installation workflows, and the 1.17 workflow untouched. API results
are verified by a second GET. A permission failure is recorded, never hidden.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / 'data' / 'maintenance_status.json'
LEGACY = ('revenue-v19.yml', 'profit-v110.yml', 'readiness-v113.yml')


def _api(repo, filename, token, verb='GET'):
    endpoint = (f'https://api.github.com/repos/{repo}/actions/workflows/'
                + urllib.parse.quote(filename, safe='')
                + ('/disable' if verb == 'PUT' else ''))
    request = urllib.request.Request(endpoint, method=verb, headers={
        'Authorization': 'Bearer '+token,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'soso-stock-radar-maintenance-1.17',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    with urllib.request.urlopen(request, timeout=12) as response:
        data = response.read(150_000)
        if verb == 'PUT':
            if response.status != 204:
                raise RuntimeError('停用未回傳204')
            return {}
        return json.loads(data.decode('utf-8'))


def audit_old_weekly_workflows(repo=None, token=None):
    repo = repo or os.environ.get('GITHUB_REPOSITORY', '')
    token = token or os.environ.get('GITHUB_TOKEN', '')
    results=[]
    for filename in LEGACY:
        item={'filename': filename, 'verified_disabled': False, 'state': 'unknown'}
        try:
            if not repo or not token:
                raise RuntimeError('工作流程未提供 GitHub Actions 身分或權限')
            before = _api(repo, filename, token, 'GET')
            state = str(before.get('state','unknown'))
            item['previous_state'] = state
            if state == 'active':
                _api(repo,filename,token,'PUT')
                after = _api(repo,filename,token,'GET')
                state = str(after.get('state','unknown'))
            item['state'] = state
            item['verified_disabled'] = state.startswith('disabled_')
            if not item['verified_disabled']:
                item['error'] = 'GitHub 未確認已停用，請人工檢查'
        except Exception as ex:
            code = getattr(ex,'code',None)
            item['error'] = (f'GitHub HTTP {code}' if isinstance(code,int)
                             else f'{type(ex).__name__}: {str(ex)[:80]}')
        results.append(item)
        print('檢查舊排程:',filename,item['state'],'verified:',item['verified_disabled'],item.get('error',''))
    report = {
        'checked_at': datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M'),
        'purpose': 'Verify retired weekly workflows, not daily-market scan success',
        'legacy_workflows': results,
        'all_disabled': all(r['verified_disabled'] for r in results),
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('三套舊週日排程全部停用:',report['all_disabled'])
    return report


if __name__=='__main__':
    audit_old_weekly_workflows()
