"""Stock Radar 1.17 health dashboard: traceable snapshots, not a promise of live CI status.

Checks latest scan's market dates / completeness and locally archived TWSE
financial data. Older GitHub workflows are independently managed by the 1.17
weekly maintenance workflow, which records verified API outcomes in JSON.
"""
from __future__ import annotations

import csv
import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
REPORT = BASE / 'data' / 'maintenance_status.json'
ARCHIVES = {
    '月營收': (BASE / 'data' / 'monthly_revenue.csv', '資料年月'),
    '季報獲利': (BASE / 'data' / 'quarterly_profit.csv', '季度'),
}
GITHUB_ACTIONS = 'https://github.com/s16769205o-png/stock-radar/actions'


def _esc(value):
    return html.escape(str(value), quote=True)


def _csv_rows(path):
    try:
        with path.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error, UnicodeError, ValueError):
        return []


def _freshness(day_value, now):
    try:
        stamp = date.fromisoformat(str(day_value))
        days = (now - stamp).days
    except (ValueError, TypeError):
        return '查無有效日期', 'bad'
    if days < 0:
        return '日期超前，請核對', 'bad'
    if days > 6:
        return f'{days} 天前（可能過期，請查交易日）', 'warn'
    return f'{days} 天前（仍須核對交易所假期）', 'ok'


def _period_gap(period, now):
    """Calendar distance since the completed reporting period, not filing lateness."""
    try:
        if len(period) == 7 and period[4] == '-':
            year, month = map(int, period.split('-'))
            if not 1 <= month <= 12: raise ValueError('month')
            if month == 12: end = date(year + 1, 1, 1) - timedelta(days=1)
            else: end = date(year, month + 1, 1) - timedelta(days=1)
            return (now-end).days, 80
        if len(period) == 6 and period[4] == 'Q' and period[5] in '1234':
            year, quarter = int(period[:4]), int(period[5])
            month = quarter * 3
            end = date(year, month+1, 1)-timedelta(days=1) if month < 12 else date(year,12,31)
            return (now-end).days, 180
    except (ValueError, OverflowError, TypeError):
        return None, 0
    return None, 0


def _health_row(name, observation, status, notes):
    sign = {'ok': '●', 'warn': '▲', 'bad': '!', 'unknown': '?'}[status]
    color = {'ok': '#17764e', 'warn': '#a56813', 'bad': '#a13d3d', 'unknown': '#607184'}[status]
    return (f'<tr><td><span style="color:{color};font-weight:800">{sign}</span> '
            f'{_esc(name)}</td><td>{_esc(observation)}</td><td>{_esc(notes)}</td></tr>')


def _status_report():
    try:
        info=json.loads(REPORT.read_text(encoding='utf-8'))
        if isinstance(info, dict): return info
    except (OSError, ValueError, UnicodeError):
        pass
    return {}


def health_section(records, errors, history_rows, universe, industry):
    """Produce one standalone HTML section that will go to the overview tab."""
    now_dt = datetime.now(ZoneInfo('Asia/Taipei'))
    now = now_dt.date()
    rows=[]
    caution=[]
    missing_names=[]
    for market in ('台股','美股'):
        expected = set(universe.get(market, []))
        pool = [r for r in records if r.get('市場')==market and r.get('股票') in expected]
        latest = max((str(r.get('交易日期', '')) for r in pool),default='')
        latest_symbols = {r.get('股票') for r in pool if r.get('交易日期') == latest}
        present = len(latest_symbols)
        missing = sorted(expected-latest_symbols)
        if missing: missing_names.append(f'{market}未取得：'+', '.join(missing[:8])+('…' if len(missing)>8 else ''))
        age_text, age_status = _freshness(latest, now)
        if present == len(expected) and age_status=='ok':
            status, msg = 'ok', f'完整掃描；交易日距今 {age_text}'
        else:
            status = 'bad' if present<max(1,int(len(expected)*.7)) else 'warn'
            msg=f'日期：{age_text}；不完整掃描或可能有假日延遲'
        rows.append(_health_row(market+'行情', f'{present}/{len(expected)} 檔｜{latest or "無日期"}',status,msg))
        if status!='ok': caution.append(market+'行情')

    latest_revenue=''
    latest_quarter=''
    for kind,(path,col) in ARCHIVES.items():
        allrows = _csv_rows(path)
        latest = max((str(r.get(col,'')) for r in allrows if r.get(col)),default='')
        recent = [r for r in allrows if r.get(col)==latest]
        covered = {str(r.get('公司代號','')) for r in recent if r.get('公司代號')}
        if kind=='月營收':
            expected={code.split('.')[0] for code in universe.get('台股', [])}
            latest_revenue=latest
        else:
            expected={code.split('.')[0] for code in universe.get('台股', []) if industry.get(code)!='金融'}
            latest_quarter=latest
        n = len(covered & expected)
        diff,limit = _period_gap(latest,now)
        stale = diff is not None and diff > limit
        if not latest or n==0:
            status='bad'; msg='存檔缺失或無有效資料'
        elif stale or n < max(1,int(len(expected)*.8)):
            status='warn'; msg='可能需要檢查官方資料或缺漏公司'
        else:
            status='ok'; msg='已保存的官方資料；不等於當日重新公告'
        rows.append(_health_row(kind+'存檔',f'{latest or "尚無"}｜{n}/{len(expected)} 檔',status,msg))
        if status!='ok': caution.append(kind+'存檔')
    # Date coverage is only for observations successfully saved, not proof of
    # a backtest or an always-on workflow.
    completed=[]
    for market in ('台股','美股'):
        expected={code for code in universe.get(market,[])}
        by_date={}
        for row in history_rows:
            if row.get('市場')!=market or row.get('股票') not in expected: continue
            d = row.get('交易日期')
            if not d: continue
            by_date.setdefault(d,set()).add(row.get('股票'))
        complete=sum(len(v)==len(expected) for v in by_date.values())
        completed.append(f'{market} {complete} 日')
    rows.append(_health_row('歷史掃描檔','；'.join(completed),'unknown','完整日期數；不代表已完成績效回測'))
    if errors:
        rows.append(_health_row('本次資料錯誤',f'{len(errors)} 檔','warn','詳情請看 GitHub Actions 記錄'))
        caution.append('掃描錯誤')

    state = _status_report()
    workflows = state.get('legacy_workflows') if isinstance(state.get('legacy_workflows'),list) else []
    updated = str(state.get('checked_at',''))
    if workflows:
        not_closed = [w.get('filename','') for w in workflows if not w.get('verified_disabled',False)]
        if not_closed:
            check_text = '仍有待確認的舊週日排程：'+', '.join(not_closed)
            check_status = 'warn'
            caution.append('舊排程')
        else:
            check_text = '三套舊週日流程已經 API 查證停用'
            check_status = 'ok'
        rows.append(_health_row('舊週日排程',check_text,check_status,f'最近核對：{updated or "未知"}'))
    else:
        rows.append(_health_row('舊週日排程','尚未核實','unknown','需要查看 GitHub 工作流程狀態'))

    if caution:
        headline = '有項目值得檢查：'+'、'.join(caution)
    else:
        headline = '此次已保存的資料完整度檢查沒有發現異常'
    notes = ('這裡檢查的是<b>目前這份報告的快照</b>、歷史檔與上次排程核對結果，'
             '不是 GitHub Actions 的即時執行監測。若排程日後失敗，舊網頁仍可能保留；'
             '請核對<b>報告產生時間</b>和 GitHub 工作流程。假日也可能導致交易日期延後。')
    return (
      '<h2>🛠️ 別墅機電總控室・1.17</h2>'
      '<p class="muted">資料健康燈｜報告產生時間（台灣）：<b>'+_esc(now_dt.strftime('%Y-%m-%d %H:%M'))+'</b>。'
      ' 綠色圓點＝快照檢查通過；黃色三角＝應核對；問號＝僅資訊、不做通過判定。</p>'
      '<div class="note"><b>'+_esc(headline)+'</b>'
      '<div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>檢查</th><th>記錄</th><th>說明</th>'
      '</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
      '<details style="margin-top:12px"><summary>如何讀懂健康燈、排程與資料缺漏？</summary>'
      '<p class="muted">'+notes+'</p>'
      + ('<p class="muted">'+_esc('；'.join(missing_names))+'</p>' if missing_names else '')
      + '<p class="muted">排程規劃：保留原每日掃描；1.17 每週日另行存檔財報。過時週日流程若未成功停用，會標示待確認。</p>'
      '</details>'
      '<p class="muted"><a href="'+GITHUB_ACTIONS+'">查看 GitHub Actions 最新執行紀錄</a>。'
      '這個連結可確認真正的成功或失敗，勿僅憑網頁仍可開啟就判定正常。</p></div>'
    )
