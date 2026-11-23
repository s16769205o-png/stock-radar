"""Small, self-contained mobile status lamp for the last published report.

It describes the validated snapshot embedded in this report, NOT a live quote
feed or live check of GitHub Actions. The browser can warn when an old HTML
document is reopened; no network calls or write permissions are required.
"""
from __future__ import annotations

from datetime import datetime
from html import escape

from history_lab_v129 import _prices
from trading_sessions import last_completed_session, recent_sessions


BENCHMARKS = {'台股': '0050.TW', '美股': 'SPY'}


def snapshot_health(records, benchmark_frames, universe, generated_at):
    """Pure summary of the inputs actually used to create the website."""
    if not isinstance(generated_at, datetime) or generated_at.utcoffset() is None:
        raise ValueError('健康燈需要含時區的掃描時間')
    result = []
    for market in ('台股', '美股'):
        expected = last_completed_session(market, generated_at)
        codes = set(universe.get(market, ()))
        rows = [r for r in records if r.get('市場') == market]
        matching = [r for r in rows
                    if r.get('股票') in codes and r.get('交易日期') == expected]
        received = {r.get('股票') for r in matching}
        # Two identical rows must not inflate a valid 50/50 count.
        seen_once = {code for code in received
                     if sum(r.get('股票') == code for r in rows) == 1}
        prices, dates = _prices(benchmark_frames.get(market))
        required = recent_sessions(market, expected, 61)
        benchmark_ok = bool(dates and dates[-1] == expected and
                            all(d in prices for d in required))
        ready = (bool(codes) and seen_once == codes and
                 len(rows) == len(codes) and benchmark_ok)
        result.append({
            'market': market, 'expected': expected,
            'covered': len(seen_once), 'total': len(codes),
            'benchmark': BENCHMARKS[market], 'benchmark_ok': benchmark_ok,
            'ready': ready,
        })
    return result


def health_light_section(records, benchmark_frames, universe, generated_at):
    """Return a mobile-first HTML fragment positioned above market tabs."""
    state = snapshot_health(records, benchmark_frames, universe, generated_at)
    success = all(item['ready'] for item in state)
    status_class = 'rhl-ok' if success else 'rhl-alert'
    status_text = '本次報告行情完整' if success else '本次報告有行情異常'
    stamp = escape(generated_at.strftime('%Y-%m-%d %H:%M'), quote=True)
    iso = escape(generated_at.isoformat(timespec='seconds'), quote=True)
    tiles = []
    for item in state:
        market = escape(item['market'])
        prefix = '🇹🇼' if item['market'] == '台股' else '🇺🇸'
        check = '資料一致' if item['ready'] else '請檢查'
        bench = '完整' if item['benchmark_ok'] else '有缺口'
        tile_class = 'rhl-tile-ok' if item['ready'] else 'rhl-tile-alert'
        tiles.append(
            '<div class="rhl-market ' + tile_class + '"><div class="rhl-market-top">'
            + '<strong>' + prefix + ' ' + market + '</strong>'
            + '<span>' + check + '</span></div>'
            + '<div class="rhl-count">' + str(item['covered']) + ' / '
            + str(item['total']) + '<small> 檔</small></div>'
            + '<p>行情日<span class="rhl-date">' + escape(item['expected'])
            + '</span><span class="rhl-benchmark">基準 '
            + '<span class="rhl-benchmark-value">'
            + escape(item['benchmark']) + '：' + bench + '</span></span></p></div>'
        )
    return ('''<section id="radar-health-light-v131" class="rhl-card '''
    + status_class + '''" data-generated-at="''' + iso + '''"
      aria-label="股票雷達資料健康燈">
      <style>
      /* stock-radar-v131-mobile-health */
      #radar-health-light-v131{margin:16px 0 18px;padding:15px;border-radius:16px;
       border:1px solid #cbdbea;background:#fff;box-shadow:0 5px 19px #23364e0d;
       font-family:system-ui,-apple-system,sans-serif}
      #radar-health-light-v131 .rhl-head{display:flex;align-items:flex-start;
       justify-content:space-between;gap:10px;flex-wrap:wrap}
      #radar-health-light-v131 .rhl-kicker{font-size:.72rem;letter-spacing:.09em;
       color:#496786;font-weight:750;margin:0 0 5px}
      #radar-health-light-v131 .rhl-title{display:flex;align-items:center;
       gap:9px;font-size:1.01rem;font-weight:800;color:#214a36}
      #radar-health-light-v131.rhl-alert .rhl-title{color:#884927}
      #radar-health-light-v131 .rhl-dot{width:11px;height:11px;flex:none;border-radius:50%;
       background:#168257;box-shadow:0 0 0 4px #e0f5ea}
      #radar-health-light-v131.rhl-alert .rhl-dot,
      #radar-health-light-v131.rhl-stale .rhl-dot{background:#ad6426;box-shadow:0 0 0 4px #fff0d8}
      #radar-health-light-v131 .rhl-scan{font-size:.78rem;color:#596779;
       margin-top:4px;line-height:1.5}
      #radar-health-light-v131 .rhl-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
       gap:10px;margin:14px 0 10px}
      #radar-health-light-v131 .rhl-market{padding:11px;min-width:0;border-radius:11px;
       background:#f4f8fd;border:1px solid #e0e8f1}
      #radar-health-light-v131 .rhl-market-top{display:flex;justify-content:space-between;
       gap:5px;flex-wrap:wrap;align-items:center}
      #radar-health-light-v131 .rhl-market-top strong{font-size:.89rem;color:#2f4865}
      #radar-health-light-v131 .rhl-market-top span{font-size:.71rem;font-weight:700;color:#27634a}
      #radar-health-light-v131 .rhl-tile-alert .rhl-market-top span{color:#aa4f29}
      #radar-health-light-v131 .rhl-count{font-weight:800;font-size:1.48rem;
       letter-spacing:-.04em;color:#294969;margin:5px 0}
      #radar-health-light-v131 .rhl-count small{font-size:.72rem;letter-spacing:0;font-weight:500}
      #radar-health-light-v131 .rhl-market p{font-size:.74rem;line-height:1.65;
       color:#5b6b7b;margin:0;overflow-wrap:anywhere}
      #radar-health-light-v131 .rhl-benchmark{display:block}
      #radar-health-light-v131 .rhl-date,
      #radar-health-light-v131 .rhl-benchmark-value{display:block;
       white-space:nowrap;font-variant-numeric:tabular-nums}
      #radar-health-light-v131 .rhl-note{font-size:.78rem;line-height:1.6;
       color:#687686;margin:0}
      #radar-health-light-v131 .rhl-age-alert{font-size:.82rem;color:#8c4b1d;
       margin:8px 0 0;font-weight:700}
      @media(max-width:420px){
       #radar-health-light-v131{padding:12px}
       #radar-health-light-v131 .rhl-grid{gap:8px}
       #radar-health-light-v131 .rhl-market{padding:9px}
       #radar-health-light-v131 .rhl-count{font-size:1.32rem}
      }
      </style>
      <div class="rhl-head"><div>
        <p class="rhl-kicker">🕸️ 股票別墅 · 1.31</p>
        <div class="rhl-title"><span class="rhl-dot" aria-hidden="true"></span>
          <span id="rhl-status">''' + status_text + '''</span></div>
        <div class="rhl-scan">最近一次報告產生：''' + stamp + '''（台灣時間）</div>
      </div></div>
      <div class="rhl-grid">''' + ''.join(tiles) + '''</div>
      <p class="rhl-note">這是上次成功產生報告時的資料狀況，不是即時行情；
       休市日或更新失敗時，網站可能仍顯示舊報告。請以資料日期為準。</p>
      <p id="rhl-age-warning" class="rhl-age-alert" role="status" hidden></p>
      <script>
      (function(){
        const root=document.getElementById('radar-health-light-v131');
        if(!root)return;
        const issued=Date.parse(root.dataset.generatedAt||'');
        const warning=document.getElementById('rhl-age-warning');
        const label=document.getElementById('rhl-status');
        if(!Number.isFinite(issued)||!warning||!label)return;
        const originalLabel=label.textContent;
        function refresh(){
          const elapsed=Date.now()-issued;
          if(elapsed>72*60*60*1000){
            root.classList.add('rhl-stale');
            label.textContent='資料較舊，請核對日期';
            warning.hidden=false;
            warning.textContent='距上次報告已超過 72 小時；可能是休市或更新中斷，不代表即時行情完整。';
          }else{
            root.classList.remove('rhl-stale');
            warning.hidden=true;
            label.textContent=originalLabel;
          }
        }
        refresh();
        document.addEventListener('visibilitychange',function(){if(!document.hidden)refresh()});
      })();
      </script>
    </section>''')


