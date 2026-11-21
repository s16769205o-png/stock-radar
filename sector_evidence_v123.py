"""Preliminary TW sector fundamentals evidence, not a 30-point investment score.

Revenue direction is not profitability. Sector membership is custom and limited.
Never compare absolute margins of unrelated businesses, or turn absent historical
filings into a fabricated year-over-year improvement score.
"""
from __future__ import annotations

import csv
import html
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVENUE = ROOT / 'data' / 'monthly_revenue.csv'
PROFIT = ROOT / 'data' / 'quarterly_profit.csv'


def _escape(x): return html.escape(str(x), quote=True)


def _read(path):
    try:
        with path.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    except (OSError, ValueError, UnicodeError, csv.Error):
        return []


def _number(x):
    try:
        v = float(str(x).strip().replace(',', ''))
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def _percent(x):
    return '—' if x is None else f'{x:+.1f}%'


def compute(universe, industry, revenues, profits):
    """Return plain records for deterministic tests and auditing.

    Known directional evidence up to 16 points (8 revenue breadth + 8 profitable
    operating margins); 14 future points require same-quarter prior-year margins.
    Full 30-point scores are deliberately disabled pending data sufficiency.
    """
    allowed = {symbol.split('.')[0]:symbol for symbol in universe.get('台股', [])}
    month = max((str(r.get('資料年月', '')) for r in revenues if r.get('公司代號') in allowed and len(str(r.get('資料年月','')))==7),default='')
    quarter = max((str(r.get('季度', '')) for r in profits if r.get('公司代號') in allowed and len(str(r.get('季度','')))==6),default='')
    rev = {str(r.get('公司代號')):r for r in revenues if r.get('資料年月') == month and r.get('公司代號') in allowed}
    current = {str(r.get('公司代號')):r for r in profits if r.get('季度') == quarter and r.get('公司代號') in allowed}
    prior_year = (str(int(quarter[:4])-1) + quarter[4:]) if quarter else ''
    older = {str(r.get('公司代號')):r for r in profits if r.get('季度') == prior_year and r.get('公司代號') in allowed}
    groups=defaultdict(list)
    for code, sym in allowed.items():
        groups[industry.get(sym, '未分類')].append(code)
    output=[]
    for sector, codes in groups.items():
        sample=len(codes)
        mon=[(_number(rev.get(c,{}).get('年增率')),_number(rev.get(c,{}).get('累計年增率'))) for c in codes]
        op=[_number(current.get(c,{}).get('累計營業利益率%')) for c in codes]
        usable_rev=[(y,c) for y,c in mon if y is not None and c is not None]
        usable_op=[x for x in op if x is not None]
        same=[(_number(older[c].get('累計營業利益率%')),_number(current[c].get('累計營業利益率%'))) for c in codes if c in older and c in current]
        same=[(prev,now) for prev,now in same if prev is not None and now is not None]
        result={'sector':sector,'sample':sample,'month':month,'quarter':quarter,
                'revenue_coverage':len(usable_rev),'profit_coverage':len(usable_op),
                'prior_coverage':len(same),'median_yoy':statistics.median([x[0] for x in usable_rev]) if usable_rev else None,
                'revenue_positive':sum(y>0 for y,c in usable_rev),'cumulative_positive':sum(c>0 for y,c in usable_rev),
                'operating_positive':sum(x>0 for x in usable_op),
                'improving':sum(now>prev for prev,now in same),
                'pilot':None,'full_score':None,'note':''}
        if sector=='金融':
            result['note']='金融業不能使用一般業營業利益率，暫不評分'
        elif sample<3:
            result['note']='樣本少於 3 檔，僅列研究證據、不評分'
        elif len(usable_rev)<max(2,math.ceil(sample*.75)) or len(usable_op)<max(2,math.ceil(sample*.75)):
            result['note']='營收或季報覆蓋不足 75%，暫不評分'
        else:
            # Rounded discrete trial points; these are OBSERVATION SIGNALS only.
            rev_score=4*result['revenue_positive']/len(usable_rev)+4*result['cumulative_positive']/len(usable_rev)
            op_score=8*result['operating_positive']/len(usable_op)
            result['pilot']=round(rev_score+op_score,1)
            # No full 30-score until a full comparable company set exists in prior year.
            if len(same)>=max(2,math.ceil(sample*.75)):
                result['full_score']=round(rev_score+op_score+14*result['improving']/len(same),1)
                result['note']='30 分實驗試算，尚未經回測驗證，未接入排行榜'
            else:
                result['note']='暫僅 16 分方向訊號；缺少去年同季累計利益率，不能補齊 30 分'
        output.append(result)
    return sorted(output,key=lambda x:(x['pilot'] is None, -(x['pilot'] or 0),x['sector']))


def sector_evidence_section(universe, industry):
    data=compute(universe,industry,_read(REVENUE),_read(PROFIT))
    rmonth=max((r['month'] for r in data),default='')
    pquarter=max((r['quarter'] for r in data),default='')
    parts=['<h2>🇹🇼 台股｜產業前景引擎・基本面試算 1.23</h2>',
      '<div class="note"><b>產業前景 30% 仍未正式啟用。</b>'
      '<p class="muted">已保存月營收：'+_escape(rmonth or '無')+'；已保存季報：'+_escape(pquarter or '無')+'。'
      '先建置可稽核的試算指標，尚不與技術分數相加、不調整排名。</p>'
      '<p class="muted"><b>試算規則：</b>營收月年增為正比例 4 分、累計營收年增為正比例 4 分、'
      '營業利益率為正比例 8 分；另預留 14 分給去年同季累計營業利益率改善比例。'
      '目前缺跨年比較時，僅顯示 16 分方向訊號；小樣本或缺資料不計分。'
      '此規則尚未回測，不能把「16 分」等同產業預測能力。</p>'
      '<div class="table-wrap"><table><thead><tr><th>產業（研究分組）</th><th>營收年增中位數</th><th>營收資料</th>'
      '<th>營業獲利公司</th><th>基本面方向訊號</th><th>研究限制</th></tr></thead><tbody>']
    for row in data:
        signal=('—' if row['pilot'] is None else f"{row['pilot']:.1f}/16")
        if row['full_score'] is not None:
            signal=f"{row['full_score']:.1f}/30（實驗）"
        profit=f"{row['operating_positive']}/{row['profit_coverage']}" if row['profit_coverage'] else '—'
        parts.append('<tr><td><b>'+_escape(row['sector'])+'</b><small>'+str(row['sample'])+' 檔樣本</small></td>'
                     '<td>'+_percent(row['median_yoy'])+'</td><td>'+str(row['revenue_coverage'])+'/'+str(row['sample'])+'</td>'
                     '<td>'+_escape(profit)+'</td><td>'+_escape(signal)+'</td><td>'+_escape(row['note'])+'</td></tr>')
    parts.append('</tbody></table></div><p class="muted">同產業不等於同一營運模式；正成長不保證獲利或股價上漲。'
                 '排除金融業特殊財報口徑。此處依目前研究池等權統計，未做回測、樣本外驗證或歷史時點防前視偏差修正。</p></div>')
    return ''.join(parts)
