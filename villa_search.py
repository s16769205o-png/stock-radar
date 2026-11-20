"""Stock radar 1.20 - accessible, client-side search of already rendered stock cards.

Only operates on public report nodes within the 100-stock research universe.
It does not fetch quotes, access private browser holdings or alter calculations.
"""
from pathlib import Path

CSS = r'''
/* stock-radar-villa-search-1.20 */
#villa-quickfind {background:#fff;border:1px solid #dbe5f1;border-radius:16px;
 padding:15px;margin:20px 0;box-shadow:0 3px 10px rgba(36,76,116,.04);}
#villa-quickfind h2 {font-size:1.12rem;margin:1px 0 7px;color:#28466a}
#villa-quickfind .quick-hint {color:#63758a;font-size:.83rem;line-height:1.6;margin:4px 0 12px}
#villa-quick-input {display:block;width:100%;font:inherit;color:#24384f;box-sizing:border-box;
 border:1px solid #a8c1dc;border-radius:10px;padding:12px 13px;background:#fbfdff;}
#villa-quick-input:focus-visible {outline:2px solid #3778b7;outline-offset:1px;}
#villa-quick-results {list-style:none;margin:10px 0 0;padding:0;display:grid;gap:7px;max-height:355px;overflow:auto;}
#villa-quick-results li {list-style:none;margin:0;padding:0;}
#villa-quick-results button {display:flex;align-items:center;justify-content:space-between;gap:7px;
 background:#f4f8fe;border:1px solid #d9e6f5;color:#263f5a;border-radius:11px;
 width:100%;text-align:left;padding:11px;cursor:pointer;font:inherit;}
#villa-quick-results button:focus-visible {outline:2px solid #3778b7;}
#villa-quick-results small {font-size:.75rem;color:#64758b;display:block;line-height:1.45;}
#villa-quick-results .quick-symbol {font-size:.8rem;white-space:nowrap;color:#3d6c97;}
#villa-quick-status {font-size:.8rem;color:#65768c;line-height:1.6;margin:9px 0 0;}
@media(max-width:600px){#villa-quickfind{padding:12px;margin-top:12px}}
'''

JS = r'''
(function(){
  'use strict';
  const overview=document.getElementById('panel-overview');
  const nav=document.getElementById('radar-market-tabs');
  if(!overview || !nav || document.getElementById('villa-quickfind'))return;
  const entries=[];
  for(const market of ['tw','us']){
    const panel=document.getElementById('panel-'+market);
    if(!panel)continue;
    // Only ranking cards, not every document whose heading happens to be similar.
    for(const card of panel.querySelectorAll('article.card')){
      const name=card.querySelector('.heading strong')?.textContent?.trim() || '';
      const meta=card.querySelector('.heading small')?.textContent?.trim() || '';
      const symbol=meta.split('·')[0]?.trim() || '';
      if(!symbol || !name)continue;
      entries.push({market,card,name,symbol,key:(name+' '+symbol).toUpperCase()});
    }
  }
  const unique=new Map();
  for(const row of entries)unique.set(row.market+'-'+row.symbol,row);
  const stocks=Array.from(unique.values());
  const root=document.createElement('section');
  root.id='villa-quickfind';root.setAttribute('aria-label','股票研究快速搜尋');
  root.innerHTML='<h2>🔎 股票快速搜尋</h2>'+
    '<p class="quick-hint">直接搜尋固定 100 檔裡的股票名稱或代號；點結果即可跳到它的研究卡片。</p>'+
    '<label for="villa-quick-input" class="villa-visually-hidden">股票名稱或代號</label>'+
    '<input id="villa-quick-input" type="search" placeholder="例：南亞、2330、NVDA" autocomplete="off" maxlength="35">'+
    '<p id="villa-quick-status" role="status" aria-live="polite"></p>'+
    '<ul id="villa-quick-results"></ul>';
  const plan=overview.querySelector('.radar-subgroup') || overview.firstChild;
  overview.insertBefore(root,plan);
  const input=root.querySelector('input');
  const status=root.querySelector('#villa-quick-status');
  const results=root.querySelector('#villa-quick-results');
  function render(){
    const query=input.value.trim().toUpperCase();
    results.replaceChildren();
    if(!query){status.textContent='可查詢已掃描的 '+stocks.length+' 檔股票。';return;}
    const matched=stocks.filter(row=>row.key.includes(query)).slice(0,15);
    status.textContent=matched.length?('符合條件：顯示 '+matched.length+' 檔'+
      (stocks.filter(row=>row.key.includes(query)).length>15?'（僅顯示前 15 檔）':'')):
      '固定掃描池找不到這檔股票。可至「🍳 廚房」加入私人觀察清單，但尚無額外行情。';
    for(const row of matched){
      const li=document.createElement('li');
      const button=document.createElement('button');button.type='button';
      const group=document.createElement('span');
      const strong=document.createElement('strong');strong.textContent=row.name;
      const small=document.createElement('small');small.textContent=row.market==='tw'?'🇹🇼 台股':'🇺🇸 美股';
      group.append(strong,small);
      const ticker=document.createElement('span');ticker.className='quick-symbol';ticker.textContent=row.symbol+' ›';
      button.append(group,ticker);
      button.addEventListener('click',()=>{
        const tab=document.getElementById('tab-'+row.market);
        if(!tab)return;
        tab.click();
        // Ranking positions 11-50 are behind an expandable disclosure.
        let ancestor=row.card.parentElement;
        while(ancestor){if(ancestor.tagName==='DETAILS')ancestor.open=true;ancestor=ancestor.parentElement;}
        input.blur();
        requestAnimationFrame(()=>{
          row.card.scrollIntoView({block:'start',behavior:'auto'});
          row.card.setAttribute('tabindex','-1');row.card.focus({preventScroll:true});
        });
      });
      li.appendChild(button);results.appendChild(li);
    }
  }
  input.addEventListener('input',render);
  render();
})();
'''


def install_stock_search(path: Path) -> None:
    """Insert progressive enhancement after existing villa/famous tabs are in place."""
    path=Path(path)
    page=path.read_text(encoding='utf-8')
    if '/* stock-radar-villa-search-1.20 */' in page:return
    if page.count('</head>')!=1 or page.count('</body>')!=1:
        raise ValueError('Unexpected HTML document structure')
    if '/* stock-radar-villa-1.18 */' not in page:
        raise ValueError('Private kitchen tabs must be installed first')
    page=page.replace('</head>','<style>'+CSS+'</style></head>',1)
    page=page.replace('</body>','<script>'+JS+'</script></body>',1)
    path.write_text(page,encoding='utf-8')
