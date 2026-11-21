"""Stock Radar v1.23: fail closed on an incomplete generated HTML report.

Checks static output, not external data accuracy or live GitHub availability.
Do not publish a partial report if a post-render enhancer crashes.
"""
from __future__ import annotations

from pathlib import Path
import re

REQUIRED = (
    'STOCK RESEARCH LAB · 1.23',
    '/* Stock Radar 1.12: market navigation */',
    '/* stock-radar-villa-1.18 */',
    '/* stock-radar-famous-1.19 */',
    'villa-quickfind',
    '/* stock-radar-sector-indices-1.21 */',
    '🛠️ 別墅機電總控室',
    '🇺🇸 美股｜行情日期一致性診斷・1.23',
    '🇹🇼 台股｜產業前景引擎・基本面試算 1.23',
)


def verify_site(path: Path, records) -> None:
    """Guard the final generated report before atomically replacing index.html."""
    page = Path(path).read_text(encoding='utf-8')
    if len(page) < 65_000 or not page.lstrip().lower().startswith('<!doctype html>'):
        raise RuntimeError('網站驗收失敗：HTML 太短或格式錯誤；保留原本正式網頁')
    if page.count('</head>') != 1 or page.count('</body>') != 1 or page.count('</html>') != 1:
        raise RuntimeError('網站驗收失敗：HTML 結構缺漏；保留原本正式網頁')
    absent = [marker for marker in REQUIRED if marker not in page]
    if absent:
        raise RuntimeError('網站驗收失敗：部分房間未安裝（'+', '.join(absent)+ '）；保留原本正式網頁')
    expected = len(records)
    actual = len(re.findall(r'<article\s+class="card"', page))
    if actual != expected or expected < 70 or expected > 100:
        raise RuntimeError(f'網站驗收失敗：股票卡片數 {actual} 與掃描 {expected} 不一致；保留原本正式網頁')
    if 'soso-stock-radar-watchlist-v1' not in page:
        raise RuntimeError('網站驗收失敗：私人清單程式缺失；保留原本正式網頁')
    print(f'✅ 完工驗收：{actual} 檔股票、五分頁、私人廚房、搜尋、指數觀景台與健康檢查標記齊全')
