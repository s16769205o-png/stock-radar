"""Stock Radar v1.25: official international event headlines, no news-score.

Each headline is a dated official source link. This is not a complete news feed,
a recommendation, or a claim that a headline caused a stock movement.
Remote failures are shown, and never block the other stock-research rooms.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

# Official feeds only. Keep this deliberately small to avoid misinformation
# from unverified social/aggregator headlines and excessive CI network load.
SOURCES = (
    ('美國貨幣政策', 'Federal Reserve', 'federalreserve.gov',
     'https://www.federalreserve.gov/feeds/press_monetary.xml', '利率／美元／金融'),
    ('能源供需', 'U.S. EIA', 'eia.gov',
     'https://www.eia.gov/rss/todayinenergy.xml', '石油／天然氣／電力'),
    ('就業與經濟', 'U.S. BLS', 'bls.gov',
     'https://www.bls.gov/feed/bls_latest.rss', '美國經濟數據'),
    ('資安風險', 'U.S. CISA', 'cisa.gov',
     'https://www.cisa.gov/cybersecurity-advisories/all.xml', '軟體／資安／企業營運'),
)
WINDOW_DAYS = 14
MAX_FETCH_BYTES = 900_000


def _esc(value):
    return html.escape(str(value), quote=True)


def _tag(qname):
    return qname.rsplit('}', 1)[-1].lower()


def _direct_text(node, candidate):
    for sub in node:
        if _tag(sub.tag) == candidate:
            return ''.join(sub.itertext()).strip()
    return ''


def _timestamp(value):
    s = str(value or '').strip()
    if not s:
        return None
    dt = None
    try:
        dt = parsedate_to_datetime(s)
    except (ValueError, TypeError, IndexError):
        pass
    if dt is None:
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _official_article_link(candidate, permitted_domain):
    url = str(candidate or '').strip()
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or not (host == permitted_domain or host.endswith('.'+permitted_domain)):
        return None
    if p.username or p.password or len(url) > 1600:
        return None
    if (permitted_domain == 'eia.gov' and p.path.endswith('/todayinenergy/detail.php')
            and not any(v.isdigit() for v in urllib.parse.parse_qs(p.query).get('id', []))):
        return None
    return url


def parse_official_feed(payload, permitted_domain, now=None):
    """Read standard RSS 2.0 and Atom entries, keeping dated official links only."""
    if len(payload) > MAX_FETCH_BYTES:
        raise ValueError('來源回應超過大小限制')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    root = ET.fromstring(payload)
    if _tag(root.tag) not in ('rss', 'feed', 'rdf'):
        raise ValueError('非預期的 RSS/Atom 格式')
    events = []
    seen = set()
    for node in root.iter():
        if _tag(node.tag) not in ('item', 'entry'):
            continue
        title = re.sub(r'\s+', ' ', _direct_text(node,'title')).strip()
        if not title or len(title) > 500:
            continue
        raw_date = (_direct_text(node,'pubdate') or _direct_text(node,'published')
                    or _direct_text(node,'updated') or _direct_text(node,'date'))
        stamp = _timestamp(raw_date)
        if stamp is None or stamp < now-timedelta(days=WINDOW_DAYS) or stamp > now+timedelta(days=1):
            continue
        raw_link = ''
        for child in node:
            if _tag(child.tag) != 'link':
                continue
            if child.attrib.get('rel','alternate') in ('alternate',''):
                raw_link = child.attrib.get('href') or ''.join(child.itertext()).strip()
                if raw_link:
                    break
        url = _official_article_link(raw_link,permitted_domain)
        if not url:
            continue
        key = url.lower().split('#')[0]
        if key in seen:
            continue
        seen.add(key)
        events.append({'title':title, 'url':url, 'date':stamp})
    events.sort(key=lambda x:x['date'],reverse=True)
    return events[:6]


def _fetch(source, now):
    label, publisher, domain, feed_url, scope = source
    try:
        request = urllib.request.Request(feed_url, headers={
            'User-Agent':'soso-stock-radar/1.25 (public official news monitoring; github.com/s16769205o-png/stock-radar)',
            'Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml,*/*',
            'Accept-Encoding':'identity',
        })
        with urllib.request.urlopen(request,timeout=7) as resp:
            if urllib.parse.urlsplit(resp.geturl()).hostname not in (domain,'www.'+domain):
                # Redirects to any other host are not accepted as official feed data.
                raise ValueError('來源重新導向到非預期主機')
            payload=resp.read(MAX_FETCH_BYTES+1)
        return {'source':source, 'events':parse_official_feed(payload,domain,now), 'error':''}
    except (Exception) as exc:
        # Never claim there were no official events when the feed was unavailable.
        return {'source':source, 'events':[], 'error':type(exc).__name__}


def official_events_section(now=None, results=None):
    """Non-scoring review section on the existing overview tab."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    if results is None:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda s:_fetch(s,now),SOURCES))
    ready = sum(not r.get('error') for r in results)
    dated = sum(len(r.get('events',[])) for r in results)
    local_now = now.astimezone(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')
    bits = [
        '<h2>📰 國際重大事件觀察室・1.25</h2>',
        '<p class="muted">第四大引擎的<b>官方公告觀察版</b>。只收集部分國際官方機關的近期標題與原文連結，'
        '<b>不是全球完整新聞</b>，不會自動判定利多／利空，也不給原定的新聞 15 分。'
        '公告與股票漲跌可能無直接因果關係；需要另外研究才可確認。</p>',
        '<div class="note international-events" id="world-events-v125">',
        f'<b>近 {WINDOW_DAYS} 日官方公告｜{ready}/{len(SOURCES)} 個來源讀取成功</b>',
        f'<p class="muted">本次報告查詢：{_esc(local_now)}（台灣時間）；'
        f'已成功讀取來源中的近期公告合計 {_esc(dated)} 則（每個來源最多列出 6 則），'
        '不代表全部官方新聞皆已涵蓋。每則以原始發布日期為準。</p>'
    ]
    for result in results:
        (label, publisher, domain, feed, scope) = result['source']
        items = result.get('events',[])
        problem = result.get('error','')
        bits.append('<details class="event-feed"><summary>'+_esc(label)+'｜'+_esc(scope)+
                    '　'+('來源暫不可用' if problem else str(len(items))+' 則近期公告')+'</summary>')
        bits.append('<p class="muted">'+_esc(publisher)+' 官方 RSS。'
                    + ('讀取遇到 '+_esc(problem)+'；請直接查看官方來源，不能解讀成沒有重要消息。'
                       if problem else '資料屬公告資訊，不代表股價反應。')
                    + ' <a target="_blank" rel="noopener noreferrer" href="'+_esc(feed)+'">官方來源</a></p>')
        if items:
            bits.append('<ul class="event-list">')
            for event in items:
                date_value=event['date'].astimezone(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d')
                bits.append('<li><small>'+_esc(date_value)+'</small> '
                            '<a href="'+_esc(event['url'])+'" target="_blank" rel="noopener noreferrer">'
                            +_esc(event['title'])+'</a></li>')
            bits.append('</ul>')
        elif not problem:
            bits.append('<p class="muted">本次可解析的資料中，近 14 日沒有符合日期與官方連結條件的公告；'
                        '這不代表該領域沒有事件。</p>')
        bits.append('</details>')
    bits.append('<p class="muted">懶人閱讀順序：先看貨幣政策與能源，再視持股產業查看就業數據和資安。'
                '這只是研究分類，不代表重要程度排名，更不構成買賣建議。</p></div>')
    bits.append('''<style>
    .international-events .event-feed {border:1px solid #dbe5f0;border-radius:11px;background:#fff;margin:9px 0;overflow:hidden}
    .international-events .event-feed>summary {padding:13px 11px;font-weight:700;color:#2d5e87;line-height:1.5}
    .international-events .event-feed>p {padding:0 12px}
    .international-events .event-list {padding:0 16px 8px 35px;line-height:1.7}
    .international-events .event-list li {margin-bottom:9px;overflow-wrap:anywhere}
    .international-events .event-list small {color:#5a748a;font-size:.78rem}
    .international-events a {color:#245f99;text-decoration:underline;text-underline-offset:2px}
    </style>''')
    return ''.join(bits)


if __name__ == '__main__':
    print(official_events_section()[:800])
