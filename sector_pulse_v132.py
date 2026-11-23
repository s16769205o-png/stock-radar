"""v1.32 — Unscored Taiwan sector operating trend observations.

Uses ONLY already archived TWSE revenue and non-financial quarterly filings.
Comparisons are matched by company: month-on-month *change in YoY revenue
growth*, and year-on-year *change in YTD operating margin at the same quarter*.
Neither direction is a return forecast, a broad industry index, or a score.
"""
from __future__ import annotations

from collections import Counter
from html import escape
from math import ceil

import industry_readiness as readiness


def classify(row):
    """Conservative, deterministic label; missing evidence is never zero."""
    size = row['股票數']
    if size < 3:
        return '樣本太少'
    enough = max(3, ceil(size * .75))
    if row['同時有數據'] < enough:
        return '最新資料不足'
    if row['營收配對'] < enough or row['獲利配對'] < enough:
        return '跨期資料不足'
    revenue = row['月營收年增變化pp']
    margin = row['去年同季累計營利率變化pp']
    if revenue is None or margin is None:
        return '跨期資料不足'
    if revenue > 0 and margin > 0:
        return '兩項同向改善'
    if revenue < 0 and margin < 0:
        return '兩項同向放緩'
    if revenue * margin < 0:
        return '營收與獲利分歧'
    return '變化持平／混合'


def analyze(universe, industry, monthly_rows, quarterly_rows):
    """Pure function; deterministic evidence and explicit comparability."""
    month, old_month, quarter, old_quarter, rows = (
        readiness.compute_industry_readiness(
            universe, industry, monthly_rows, quarterly_rows
        )
    )
    result = []
    for data in rows:
        result.append({**data, '研判': classify(data)})
    order = {
        '兩項同向改善': 0, '營收與獲利分歧': 1, '兩項同向放緩': 2,
        '變化持平／混合': 3, '跨期資料不足': 4,
        '最新資料不足': 5, '樣本太少': 6,
    }
    result.sort(key=lambda r: (order[r['研判']], r['產業']))
    return {
        'month': month, 'previous_month': old_month,
        'quarter': quarter, 'year_ago_quarter': old_quarter,
        'rows': result,
    }


def _change(value):
    return '—' if value is None else f'{value:+.1f} 百分點'


def _level(value):
    return '—' if value is None else f'{value:+.1f}%'


def _e(value):
    return escape(str(value), quote=True)


def render_section(data):
    """Mobile-first HTML. Nothing clickable pretends to trade or fetch live data."""
    rows = data['rows']
    counts = Counter(r['研判'] for r in rows)
    labels = ('兩項同向改善', '營收與獲利分歧', '兩項同向放緩', '待資料')
    summary = {
        '兩項同向改善': counts['兩項同向改善'],
        '營收與獲利分歧': counts['營收與獲利分歧'],
        '兩項同向放緩': counts['兩項同向放緩'],
        '待資料': sum(counts[s] for s in (
            '變化持平／混合', '跨期資料不足', '最新資料不足', '樣本太少'
        )),
    }
    counters = ''.join(
        '<span class="sp132-counter"><b>' + str(summary[label])
        + '</b><span>' + _e(label) + '</span></span>' for label in labels
    )
    cards = []
    for r in rows:
        verdict = r['研判']
        is_qualified = verdict in (
            '兩項同向改善', '營收與獲利分歧', '兩項同向放緩',
            '變化持平／混合'
        )
        revenue = _change(r['月營收年增變化pp']) if is_qualified else '—'
        margin = _change(r['去年同季累計營利率變化pp']) if is_qualified else '—'
        current_coverage = (r['股票數'] >= 3
                            and r['同時有數據'] >= max(3, ceil(.75 * r['股票數'])))
        yoy_level = (_level(r['月營收年增中位數'])
                     if current_coverage else '—')
        margin_level = (_level(r['營業利益率中位數'])
                        if current_coverage else '—')
        tone = ('up' if verdict == '兩項同向改善'
                else 'down' if verdict == '兩項同向放緩'
                else 'mixed' if verdict == '營收與獲利分歧'
                else 'unknown')
        cards.append(
            '<article class="sp132-card"><div class="sp132-card-head">'
            '<strong>' + _e(r['產業']) + '</strong>'
            '<span class="sp132-tag sp132-' + tone + '">' + _e(verdict)
            + '</span></div>'
            '<dl><div><dt>最新月營收年增率中位數</dt><dd>'
            + _e(yoy_level) + '</dd></div>'
            '<div><dt>最新累計營業利益率中位數</dt><dd>'
            + _e(margin_level) + '</dd></div>'
            '<div><dt>月營收年增率的跨月變化</dt><dd>'
            + _e(revenue) + '</dd></div>'
            '<div><dt>累計營業利益率的同季跨年變化</dt><dd>'
            + _e(margin) + '</dd></div></dl>'
            '<p class="sp132-coverage">研究池 ' + str(r['股票數'])
            + ' 檔｜最新兩項皆有 ' + str(r['同時有數據'])
            + ' 檔｜跨月配對 ' + str(r['營收配對'])
            + ' 檔｜跨年同季配對 ' + str(r['獲利配對'])
            + ' 檔</p></article>'
        )
    if not rows:
        cards = ['<p class="sp132-empty">尚無可研究的台股非金融族群。</p>']
    periods = (
        '月營收 ' + _e(data['month'] or '未取得')
        + ' vs ' + _e(data['previous_month'] or '未取得')
        + '；累計營利率 ' + _e(data['quarter'] or '未取得')
        + ' vs ' + _e(data['year_ago_quarter'] or '未取得')
    )
    return (
        '<section id="sector-pulse-v132" class="sp132-wrap" aria-label="台股產業營運方向">'
        '<h2>🧭 台股產業景氣雷達・1.32（不打分）</h2>'
        '<p class="muted">只用本雷達已存的證交所月營收與一般業季報，觀察'
        '<b>固定台股研究池</b>的營運方向。不是全產業景氣指數、'
        '不是股價預測，也不加入技術排名。</p>'
        '<div class="sp132-summary">' + counters + '</div>'
        '<p class="sp132-period">資料所屬期間：' + periods
        + '。月營收與季度財報並非同一段期間。</p>'
        '<div class="sp132-grid">' + ''.join(cards) + '</div>'
        '<details class="sp132-explain"><summary>這些狀態怎麼判斷？</summary>'
        '<p>最新水準是本研究池的當期中位數，不是整個產業的成長率；'
        '只有最新兩項資料覆蓋至少 75% 且至少 3 檔才顯示。'
        '「年增為正」不代表「成長正在加速」。</p>'
        '<p>每個族群至少 3 檔，且兩項最新資料、跨月與跨年配對'
        '都要覆蓋至少 75% 的研究池股票（且不少於 3 檔），'
        '才會比較兩種變化的方向。只對同一家公司做跨期比較，'
        '再取各公司變化的中位數。</p>'
        '<p>「同向改善」是兩項<b>變化</b>皆為正，'
        '不是保證營收或獲利為正；「同向放緩」不等於衰退；'
        '一正一負是分歧。資料不足就不判斷、也不當作零分。'
        '金融業一般業營利率口徑不適用；美股目前沒有同等來源'
        '的營收／季報配對資料，因此本版不推論美股產業。</p>'
        '<p>歷史官方資料只從真正保存快照的時間開始累積；'
        '不會把後來才公布的資訊假裝成當時已知，'
        '也沒有足夠樣本外驗證來聲稱能預測報酬。</p></details>'
        '<style>'
        '#sector-pulse-v132{margin:20px 0;max-width:100%;}'
        '#sector-pulse-v132 .sp132-summary{display:grid;'
        'grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:12px 0;}'
        '#sector-pulse-v132 .sp132-counter{border:1px solid #d7e2ee;'
        'border-radius:11px;background:#f6f9fc;padding:9px;min-width:0;}'
        '#sector-pulse-v132 .sp132-counter b{display:block;font-size:1.28rem;}'
        '#sector-pulse-v132 .sp132-counter span{font-size:.73rem;color:#536477;}'
        '#sector-pulse-v132 .sp132-period{color:#55677b;line-height:1.6;'
        'font-size:.8rem;overflow-wrap:anywhere;}'
        '#sector-pulse-v132 .sp132-grid{display:grid;'
        'grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));'
        'gap:10px;}'
        '#sector-pulse-v132 .sp132-card{min-width:0;border:1px solid #dfe7ee;'
        'border-radius:13px;background:white;padding:12px;}'
        '#sector-pulse-v132 .sp132-card-head{display:flex;gap:8px;'
        'justify-content:space-between;align-items:start;flex-wrap:wrap;}'
        '#sector-pulse-v132 .sp132-card-head strong{font-size:.95rem;color:#2b455e;}'
        '#sector-pulse-v132 .sp132-tag{border-radius:30px;padding:4px 8px;'
        'font-size:.72rem;line-height:1.3;background:#edf0f4;color:#455565;}'
        '#sector-pulse-v132 .sp132-up{background:#e5f4ed;color:#176947;}'
        '#sector-pulse-v132 .sp132-down{background:#fff0e6;color:#9b4e26;}'
        '#sector-pulse-v132 .sp132-mixed{background:#eaf0ff;color:#405e9b;}'
        '#sector-pulse-v132 dl{margin:10px 0 7px;}'
        '#sector-pulse-v132 dl div{margin:8px 0;display:flex;'
        'justify-content:space-between;gap:8px;flex-wrap:wrap;}'
        '#sector-pulse-v132 dt{font-size:.77rem;color:#576879;}'
        '#sector-pulse-v132 dd{font-size:.86rem;font-weight:700;'
        'margin:0;color:#263d56;font-variant-numeric:tabular-nums;}'
        '#sector-pulse-v132 .sp132-coverage{margin:8px 0 0;'
        'font-size:.71rem;line-height:1.6;color:#6a7786;}'
        '#sector-pulse-v132 .sp132-explain{margin-top:12px;'
        'border:1px solid #dce5ef;border-radius:12px;padding:11px 13px;'
        'line-height:1.7;font-size:.82rem;}'
        '#sector-pulse-v132 .sp132-explain summary{cursor:pointer;font-weight:700;}'
        '@media(max-width:420px){#sector-pulse-v132 .sp132-summary{'
        'grid-template-columns:repeat(2,minmax(0,1fr));}}'
        '</style></section>'
    )


def sector_pulse_section(universe, industry):
    """Render from archived snapshots; never download or write sources."""
    return render_section(analyze(
        universe, industry,
        readiness._load(readiness.MONTHLY),
        readiness._load(readiness.QUARTERLY),
    ))
