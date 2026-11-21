"""Read-only 1.23 US data-date diagnostics, without masking stale data."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from html import escape


def _e(value):
    return escape(str(value), quote=True)


def us_date_health_section(records, universe):
    """Distinguish fetched rows from same-as-latest-session rows.

    Does not claim the most recent row is an exchange-confirmed complete session:
    yfinance can be delayed and US trading calendars have holidays.
    """
    expected = set(universe.get('美股', []))
    rows = [r for r in records if r.get('市場') == '美股' and r.get('股票') in expected]
    by_symbol = {str(r['股票']): str(r.get('交易日期') or '') for r in rows}
    by_date = defaultdict(list)
    invalid = []
    for sym, stamp in by_symbol.items():
        try:
            date.fromisoformat(stamp)
            by_date[stamp].append(sym)
        except (ValueError, TypeError):
            invalid.append(sym)
    dates = sorted(by_date, reverse=True)
    latest = dates[0] if dates else None
    aligned = sorted(by_date.get(latest, [])) if latest else []
    older = sorted((sym, day) for day, symbols in by_date.items() if day != latest for sym in symbols)
    missing = sorted(expected-set(by_symbol))
    outdated = sorted(older, key=lambda x: (x[1], x[0]))
    all_current = bool(latest and len(aligned) == len(expected) and not invalid)
    summary = (f'日期一致：{len(aligned)}/{len(expected)} 檔' if latest else '尚無有效美股交易日期')
    details = ['<h2>🇺🇸 美股｜行情日期一致性診斷・1.23</h2>',
        '<div class="note"><b>'+_e(summary)+'</b><p class="muted">本次可取得行情 '+str(len(rows))+
        '/'+str(len(expected))+' 檔；其中落在最新<b>已取得</b>日期 '+_e(latest or '無日期')+
        ' 的股票 '+str(len(aligned))+' 檔。最新已取得日期不等於交易所已確認的最新交易日。</p>']
    if all_current:
        details.append('<p>這次各股票的交易日期相同；仍不代表行情即時或資料來源完全正確。</p>')
    else:
        details.append('<p class="muted">⚠️ 日期不一致屬於資料品質提醒：較舊股票不納入同日完整比較，請勿把不同日期的排名視為嚴格同日比較。</p>')
    if outdated:
        details.append('<details><summary>查看日期落後的 '+str(len(outdated))+' 檔</summary><div class="table-wrap"><table><thead><tr><th>股票</th><th>已取得交易日</th></tr></thead><tbody>')
        details.extend('<tr><td>'+_e(sym)+'</td><td>'+_e(stamp)+'</td></tr>' for sym,stamp in outdated)
        details.append('</tbody></table></div></details>')
    if missing or invalid:
        details.append('<p class="muted">完全未取得：'+_e(', '.join(missing) or '無')+'；日期無效：'+_e(', '.join(sorted(invalid)) or '無')+'。</p>')
    details.append('<p class="muted">健康燈顯示 100 檔成功掃描，指的是取得 100 筆可計算資料，不是 100 檔都來自同一個交易日。資料由外部行情供應商提供，市場休市和延遲都可能影響日期。</p></div>')
    return ''.join(details)
