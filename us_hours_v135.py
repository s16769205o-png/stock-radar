"""Mobile US-market session guide: local clock reference, not live prices."""
import json
from pathlib import Path

IBKR = "https://www.interactivebrokers.com/en/trading/us-overnight-trading.php"
NASDAQ = "https://www.nasdaq.com/23-5-trading"

def guide_html():
    rows = [
        ("盤前", "04:00–09:30", "16:00–21:30", "17:00–22:30"),
        ("正規盤", "09:30–16:00", "21:30–次日04:00", "22:30–次日05:00"),
        ("盤後", "16:00–20:00", "次日04:00–08:00", "次日05:00–09:00"),
        ("IBKR隔夜夜盤（部分標的）", "20:00–次日03:50",
         "08:00–15:50", "09:00–16:50"),
    ]
    trs = "".join(
        f"<tr><th>{label}</th><td>{et}</td><td>{summer}</td><td>{winter}</td></tr>"
        for label, et, summer, winter in rows
    )
    return (
        '<section id="us-hours-v135" class="us135" aria-label="美股交易時段速查">'
        '<h2>🌙 美股時段速查</h2>'
        '<p>這是<b>時刻表，不是即時夜盤報價</b>。'
        '台灣沒有夏令時間；美國採夏令時間時，台灣對照會提前一小時。</p>'
        '<div class="us135-table"><table><thead><tr>'
        '<th>時段</th><th>美東時間</th><th>台灣夏令</th><th>台灣冬令</th>'
        '</tr></thead><tbody>' + trs + '</tbody></table></div>'
        '<p><b>注意：</b>隔夜夜盤不等於正式交易所的正規盤。'
        'IBKR 只有支援的股票及 ETF 能透過夜盤系統交易；'
        '各平台、休市日、提前收盤日可能不同。'
        '夜盤價差可能更大、流動性可能更低。</p>'
        '<details><summary>交易所 23/5 計畫與行情限制</summary>'
        '<p>截至 2026-11-26，Nasdaq 公告計畫 2026-12-06 '
        '啟用擴大交易時段，實際啟用與交易規則以官方最新消息為準。'
        '本雷達只保留正規盤技術資料，不把不同來源夜盤價格混入排名。</p>'
        '</details>'
        '<p>官方說明：<a href="' + IBKR + '" target="_blank" '
        'rel="noopener noreferrer">IBKR 夜盤</a> · '
        '<a href="' + NASDAQ + '" target="_blank" '
        'rel="noopener noreferrer">Nasdaq 23/5</a></p></section>'
    )

CSS = """
/* us-hours-v135 */
#us-hours-v135{max-width:100%;border:1px solid #dce6f0;border-radius:15px;
 background:white;padding:14px;margin:12px 0 20px;min-width:0}
#us-hours-v135 h2{font-size:1.1rem;margin:0 0 9px}
#us-hours-v135 p{font-size:.82rem;line-height:1.7;color:#516479}
#us-hours-v135 .us135-table{overflow-x:auto;max-width:100%;border-radius:10px}
#us-hours-v135 table{min-width:490px;font-size:.78rem;border-collapse:collapse;width:100%}
#us-hours-v135 th,#us-hours-v135 td{text-align:left;white-space:nowrap;
 padding:10px;border-bottom:1px solid #e8eff6}
#us-hours-v135 th{background:#f0f5fb}
#us-hours-v135 details{padding:8px;border:1px solid #e1e8ef;border-radius:9px}
#us-hours-v135 summary{font-size:.83rem;font-weight:650;cursor:pointer}
"""

def install_us_hours(path):
    path=Path(path)
    page=path.read_text(encoding="utf-8")
    if "/* us-hours-v135 */" in page:
        return
    if page.count("</head>")!=1 or page.count("</body>")!=1:
        raise ValueError("美股時段指南：HTML 結構不完整")
    if "/* stock-radar-villa-1.18 */" not in page:
        raise ValueError("缺少美股分頁")
    safe=json.dumps(guide_html(),ensure_ascii=False).replace("<",r"\u003c").replace(">",r"\u003e").replace("&",r"\u0026")
    script="(function(){const p=document.getElementById('panel-us');if(!p||document.getElementById('us-hours-v135'))return;const d=document.createElement('div');d.innerHTML="+safe+";p.insertBefore(d.firstElementChild,p.firstChild);})();"
    page=page.replace("</head>","<style>"+CSS+"</style></head>",1)
    page=page.replace("</body>","<script>"+script+"</script></body>",1)
    path.write_text(page,encoding="utf-8")
