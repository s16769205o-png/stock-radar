"""Progressive-enhancement mobile navigation for the existing stock radar report.

Only reorganizes the already-rendered HTML in the browser; it never changes
stock calculations, archived observations, ranking, or the update schedule.
Without JavaScript the original long report is still accessible.
"""
from pathlib import Path

CSS = r"""
/* Stock Radar 1.12: market navigation */
#radar-market-tabs {
  position: sticky; top: 0; z-index: 20; display: grid;
  grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px;
  background: #f5f7fb; padding: 11px 0 12px; margin: 14px 0 14px;
  border-bottom: 1px solid #e0e6f0;
}
#radar-market-tabs button {
  border: 1px solid #dce3ee; border-radius: 13px; background: #fff;
  padding: 12px 6px; font: 700 .98rem/1.35 system-ui, sans-serif;
  color: #4b5a70; cursor: pointer; touch-action: manipulation;
}
#radar-market-tabs button[aria-selected="true"] {
  background: #deebfb; color: #184d8b; border: 2px solid #4978b5;
  padding: 11px 5px;
}
#radar-market-tabs button:focus-visible { outline: 3px solid #4b87d1; outline-offset: 2px; }
.radar-panel[hidden] { display: none !important; }
.radar-panel h2:first-child { margin-top: 15px; }
.radar-panel .radar-subgroup { margin-bottom: 25px; }
.radar-panel .radar-subgroup > h2 { margin-top: 26px; }
.radar-panel .tabs-helper { line-height: 1.6; color: #5e697c; margin: 16px 0; }
@media (max-width: 420px) {
  #radar-market-tabs { gap: 6px; padding: 9px 0 11px; }
  #radar-market-tabs button { font-size: .91rem; padding: 10px 4px; }
  #radar-market-tabs button[aria-selected="true"] { padding: 9px 3px; }
}
"""

SCRIPT = r"""
(function () {
  'use strict';
  const main = document.querySelector('main');
  if (!main || document.getElementById('radar-market-tabs')) return;
  const original = Array.from(main.children);
  const start = original.findIndex(n => n.tagName === 'H2');
  if (start === -1) return;
  const source = original.slice(start);
  const groups = [];
  let group = null;
  for (const node of source) {
    if (node.tagName === 'H2') {
      group = {heading: node, nodes: []};
      groups.push(group);
    } else if (group) {
      group.nodes.push(node);
    }
  }
  if (!groups.length) return;
  const tabItems = [
    {key:'overview',label:'🏠 總覽'},
    {key:'tw',label:'🇹🇼 台股'},
    {key:'us',label:'🇺🇸 美股'}
  ];
  const nav = document.createElement('nav');
  nav.id = 'radar-market-tabs';
  nav.setAttribute('aria-label','股票市場分頁');
  nav.setAttribute('role','tablist');
  const panels = {};
  const views = document.createElement('div');
  views.id = 'radar-market-views';
  for (const item of tabItems) {
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'tab-'+item.key;
    button.textContent = item.label;
    button.dataset.target = item.key;
    button.setAttribute('role','tab');
    button.setAttribute('aria-controls','panel-'+item.key);
    button.setAttribute('aria-selected','false');
    button.tabIndex = -1;
    nav.appendChild(button);
    const panel = document.createElement('section');
    panel.className = 'radar-panel';
    panel.id = 'panel-'+item.key;
    panel.setAttribute('role','tabpanel');
    panel.setAttribute('aria-labelledby',button.id);
    panel.hidden = true;
    panels[item.key] = panel;
    views.appendChild(panel);
  }
  const hint = document.createElement('p');
  hint.className = 'tabs-helper';
  hint.textContent = '選擇市場後，只顯示該市場的排行榜、績效與產業資料；切換分頁不會重新抓取行情。';
  panels.overview.appendChild(hint);
  const stats = original.find(n => n.classList && n.classList.contains('stats'));
  if (stats) panels.overview.appendChild(stats.cloneNode(true));

  function marketFrom(text) {
    if (text.includes('🇹🇼') || text.includes('台股')) return 'tw';
    if (text.includes('🇺🇸') || text.includes('美股')) return 'us';
    return null;
  }
  function addGroup(dest, heading, nodes) {
    const container = document.createElement('section');
    container.className = 'radar-subgroup';
    container.appendChild(heading.cloneNode(true));
    nodes.forEach(n => container.appendChild(n.cloneNode(true)));
    panels[dest].appendChild(container);
  }
  function splitMarketGroup(heading, nodes) {
    const first = nodes.findIndex(n => n.tagName === 'H3');
    if (first < 0) return false;
    const common = nodes.slice(0, first);
    const parts = [];
    let part = null;
    for (const node of nodes.slice(first)) {
      if (node.tagName === 'H3') {
        part = {heading:node, items:[]};
        parts.push(part);
      } else if (part) {
        part.items.push(node);
      }
    }
    const targets = parts.map(p => marketFrom(p.heading.textContent));
    if (!targets.includes('tw') || !targets.includes('us')) return false;
    for (let i=0; i<parts.length; i++) {
      const market = targets[i];
      if (!market) continue;
      addGroup(market, heading, common.concat([parts[i].heading],parts[i].items));
    }
    return true;
  }
  for (const block of groups) {
    const title = block.heading.textContent.trim();
    const nodes = block.nodes;
    // Split shared sections by the already-rendered Taiwan/US h3 subtitles.
    if (splitMarketGroup(block.heading,nodes)) continue;
    const market = marketFrom(title);
    if (market) { addGroup(market,block.heading,nodes); continue; }
    if (title.includes('月營收') || title.includes('獲利品質') ||
        title.includes('基本面交叉驗證')) {
      addGroup('tw',block.heading,nodes); continue;
    }
    // Shared site status, risk notices and methodology remain in the overview.
    addGroup('overview',block.heading,nodes);
  }
  const firstContent = stats || source[0];
  main.insertBefore(nav, firstContent);
  main.insertBefore(views, firstContent);
  if (stats) stats.remove();
  source.forEach(n => n.remove());

  function select(key, saveHash, moveTop) {
    if (!panels[key]) key='overview';
    for (const item of tabItems) {
      const chosen = item.key === key;
      const button = document.getElementById('tab-'+item.key);
      button.setAttribute('aria-selected',String(chosen));
      button.tabIndex = chosen ? 0 : -1;
      panels[item.key].hidden = !chosen;
    }
    if (saveHash && history.replaceState) {
      try { history.replaceState(null,'',location.pathname+location.search+'#'+key); }
      catch (e) { /* No navigation history on local previews; tabs still work. */ }
    }
    if (moveTop) {
      nav.scrollIntoView({block:'start',behavior:'auto'});
    }
  }
  nav.addEventListener('click',function(ev) {
    const button = ev.target.closest('button[data-target]');
    if (button) select(button.dataset.target,true,true);
  });
  nav.addEventListener('keydown',function(ev) {
    const keys = ['ArrowLeft','ArrowRight','Home','End'];
    if (!keys.includes(ev.key)) return;
    ev.preventDefault();
    const now = tabItems.findIndex(t => document.getElementById('tab-'+t.key).getAttribute('aria-selected')==='true');
    let next = ev.key === 'Home' ? 0 : ev.key === 'End' ? 2 :
      (now+(ev.key==='ArrowRight'?1:2))%3;
    select(tabItems[next].key,true,false);
    document.getElementById('tab-'+tabItems[next].key).focus();
  });
  const initial = location.hash.replace('#','');
  select(panels[initial] ? initial : 'overview',false,false);
})();
"""


def install_mobile_tabs(path: Path) -> None:
    """Append a harmless client-side tab enhancer after the full HTML is generated."""
    text = path.read_text(encoding='utf-8')
    if '/* Stock Radar 1.12: market navigation */' in text:
        return
    marker = '</head>'
    if text.count(marker) != 1 or text.count('</body>') != 1:
        raise ValueError('HTML 結構異常，拒絕加入分頁')
    text = text.replace(marker, '<style>'+CSS+'</style>'+marker, 1)
    text = text.replace('</body>', '<script>'+SCRIPT+'</script></body>', 1)
    path.write_text(text, encoding='utf-8')
