"""Stock Radar 1.16: site architecture + private browser watchlist foundation.

Existing markets/analytics remain unchanged. Visitors' watchlists live only in
local browser storage; they are never transmitted to GitHub or embedded into the
public HTML. Any stock outside the fixed scanner is labeled unavailable.
"""
from __future__ import annotations

import json
from pathlib import Path

CSS = r"""
/* stock-radar-villa-1.16 */
#radar-market-tabs {
  display:flex;grid-template-columns:none;overflow-x:auto;overscroll-behavior-x:contain;
  scroll-snap-type:x proximity;scrollbar-width:thin;gap:7px;
  padding:10px 1px 12px;align-items:stretch;
}
#radar-market-tabs button {
  flex:1 0 auto;min-width:103px;padding:11px 8px;white-space:nowrap;
  scroll-snap-align:start;font-size:.91rem;
}
#radar-market-tabs button[aria-selected="true"] {padding:10px 7px;}
#radar-market-tabs button[data-target="famous"],
#radar-market-tabs button[data-target="kitchen"] {min-width:110px;}
.villa-h1 {font-size:1.42rem;margin:20px 0 8px;color:#243e62;}
.villa-muted {color:#6b7789;font-size:.9rem;line-height:1.7;}
.villa-cards {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:16px 0;}
.villa-card {background:#fff;border:1px solid #dce5ef;border-radius:14px;
  padding:14px;text-align:left;color:#243851;font:inherit;line-height:1.65;}
.villa-card strong {display:block;font-size:1rem;}
.villa-card small {display:block;margin-top:3px;color:#6b7789;font-size:.77rem;}
button.villa-card {cursor:pointer;}
button.villa-card:focus-visible {outline:3px solid #4b87d1;}
.villa-card-label {font-size:.78rem;color:#4776a1;}
.villa-note {background:#f0f5fc;border:1px solid #d8e4f2;border-radius:13px;padding:13px;margin:12px 0;line-height:1.7;font-size:.88rem;}
.villa-form {display:flex;gap:8px;flex-wrap:wrap;margin:14px 0;align-items:center;}
.villa-input {border:1px solid #b9c9db;border-radius:12px;background:white;padding:12px 10px;
  font:inherit;color:#243851;flex:1 1 170px;min-width:0;}
.villa-action {border:1px solid #4076ac;border-radius:12px;background:#2d6ca5;color:#fff;
  padding:12px 15px;cursor:pointer;font:700 .92rem system-ui,sans-serif;}
.villa-action:focus-visible,.villa-subtle:focus-visible {outline:3px solid #76a7df;outline-offset:2px;}
.villa-subtle {border:1px solid #ccd8e6;border-radius:10px;background:#fff;color:#365b85;
  padding:10px 11px;font:600 .84rem system-ui,sans-serif;cursor:pointer;}
.villa-subtle[disabled] {opacity:.5;cursor:not-allowed;}
.villa-list {display:grid;gap:10px;}
.villa-item {border:1px solid #dfe6f0;border-radius:14px;background:#fff;padding:13px;}
.villa-item-head {display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}
.villa-item h3 {font-size:1.04rem;margin:0 0 3px;}
.villa-item p {margin:6px 0;font-size:.86rem;line-height:1.65;}
.villa-item .villa-data {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;
  margin-top:10px;padding:10px;border-radius:9px;background:#f6f9fd;font-size:.85rem;}
.villa-data b {display:block;font-size:1rem;color:#233c5f;margin-top:3px;}
.villa-data small {display:block;color:#758196;}
.villa-private-actions {display:flex;gap:8px;flex-wrap:wrap;margin:12px 0;align-items:center;}
.villa-blank {border:1px dashed #bfcedd;border-radius:14px;background:#f8fafe;padding:20px 15px;line-height:1.7;color:#64758c;}
#villa-message {font-size:.88rem;min-height:1.2rem;color:#315f91;line-height:1.6;}
.villa-visually-hidden {position:absolute;clip:rect(0,0,0,0);height:1px;width:1px;overflow:hidden;white-space:nowrap;}
@media(max-width:600px) {.villa-cards {grid-template-columns:1fr;}
#radar-market-tabs button {flex:0 0 auto;min-width:100px;}
.villa-item .villa-data {grid-template-columns:repeat(2,minmax(0,1fr));}}
"""

SCRIPT = r"""
(function(){
  'use strict';
  const nav=document.getElementById('radar-market-tabs');
  const views=document.getElementById('radar-market-views');
  const overview=document.getElementById('panel-overview');
  if(!nav||!views||!overview||document.getElementById('tab-kitchen')) return;
  const tabs=[
    ['overview','🏠 總覽'],['tw','🇹🇼 台股'],['us','🇺🇸 美股'],
    ['famous','🏦 名人'],['kitchen','🍳 廚房']
  ];
  function addTab(key,label){
    const btn=document.createElement('button');
    btn.type='button';btn.id='tab-'+key;btn.textContent=label;
    btn.dataset.target=key;btn.setAttribute('role','tab');
    btn.setAttribute('aria-controls','panel-'+key);
    btn.setAttribute('aria-selected','false');btn.tabIndex=-1;
    nav.appendChild(btn);
    const panel=document.createElement('section');
    panel.id='panel-'+key;panel.className='radar-panel';
    panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',btn.id);
    panel.hidden=true;views.appendChild(panel);return panel;
  }
  const famous=addTab('famous','🏦 名人');
  const kitchen=addTab('kitchen','🍳 廚房');
  function select(key,changeHash,scroll){
    if(!tabs.some(x=>x[0]===key))key='overview';
    for(const [id] of tabs){
      const btn=document.getElementById('tab-'+id);
      const panel=document.getElementById('panel-'+id);
      const active=id===key;
      if(!btn||!panel)continue;
      btn.setAttribute('aria-selected',String(active));
      btn.tabIndex=active?0:-1;panel.hidden=!active;
    }
    if(changeHash){
      try {history.replaceState(null,'',location.pathname+location.search+'#'+key);}
      catch(err){/* local file preview can still switch tabs */}
    }
    if(scroll){
      const button=document.getElementById('tab-'+key);
      if(button)button.scrollIntoView({block:'nearest',inline:'nearest',behavior:'auto'});
      nav.scrollIntoView({block:'start',behavior:'auto'});
    }
  }
  // Capture first so the legacy three-tab handlers cannot deselect the new rooms.
  nav.addEventListener('click',e=>{
    const button=e.target.closest('button[data-target]');
    if(!button||!nav.contains(button))return;
    e.stopImmediatePropagation();e.preventDefault();
    select(button.dataset.target,true,true);
  },true);
  nav.addEventListener('keydown',e=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
    e.preventDefault();e.stopImmediatePropagation();
    const index=tabs.findIndex(t=>t[0]===document.activeElement.dataset.target);
    const i=Math.max(0,index);
    const dest=e.key==='Home'?0:e.key==='End'?tabs.length-1:
      (i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
    select(tabs[dest][0],true,false);
    document.getElementById('tab-'+tabs[dest][0]).focus();
  },true);
  const direct=location.hash.replace(/^#/,'');
  if(direct==='famous'||direct==='kitchen')select(direct,false,false);

  const plan=document.createElement('section');
  plan.className='radar-subgroup';
  plan.innerHTML=`<h2 class="villa-h1">🏡 小G股票研究別墅｜樓層導覽</h2>
    <p class="villa-muted">先把架構蓋好，再慢慢裝潢。研究報告與私人自選股分開保存。</p>
    <div class="villa-cards">
      <button class="villa-card" data-room="tw" type="button"><span class="villa-card-label">已運作</span><strong>🇹🇼 台股研究室</strong><small>排名、營收、季報、產業透視鏡與懶人提醒</small></button>
      <button class="villa-card" data-room="us" type="button"><span class="villa-card-label">已運作</span><strong>🇺🇸 美股研究室</strong><small>技術排名、產業動能與紙上績效觀察</small></button>
      <button class="villa-card" data-room="famous" type="button"><span class="villa-card-label">預留房間</span><strong>🏦 名人持股室</strong><small>申報資料與季度變化功能待接入</small></button>
      <button class="villa-card" data-room="kitchen" type="button"><span class="villa-card-label">基本功能可使用</span><strong>🍳 soso 炒股廚房</strong><small>私人自選股新增、刪除及 JSON 備份</small></button>
    </div>`;
  overview.insertBefore(plan,overview.firstChild);
  plan.addEventListener('click',e=>{
    const btn=e.target.closest('button[data-room]');if(btn)select(btn.dataset.room,true,true);
  });

  famous.innerHTML=`<h2 class="villa-h1">🏦 名人持股觀察室</h2>
    <p class="villa-muted">這間先蓋好入口與資料架構，持股比較尚未接入；不會顯示假的持股變化。</p>
    <div class="villa-note"><b>第一位研究對象：波克夏·海瑟威（Berkshire Hathaway）</b><p>
    未來會比較不同季度的 13F 申報：新增、增持、減持與不再列示的部位。
    13F 是機構的延遲季度申報，不代表巴菲特本人全部持倉，也不等於申報當天的買賣。
    </p><a href="https://www.sec.gov/edgar/search/" target="_blank" rel="noopener noreferrer">前往美國 SEC EDGAR 查詢官方申報</a></div>
    <div class="villa-card"><strong>預計施工順序</strong>
    <small>申報來源查證 → 兩季持股對照 → 變動摘要 → 更多機構</small></div>`;

  kitchen.innerHTML=`<h2 class="villa-h1">🍳 soso 炒股廚房</h2>
    <p class="villa-muted">自由輸入想追蹤的股票，不受固定 100 檔限制；不必修改 GitHub 程式。
    目前先完成清單管理，行情與技術分析只顯示雷達已掃描的股票。</p>
    <div class="villa-note"><b>🔐 私人資料提醒</b>：這個清單只保存在目前瀏覽器的本機儲存空間，不會寫進公開 GitHub。
    換手機、無痕模式或清除網站資料可能使清單消失，請定期匯出備份。
    此版本沒有帳戶同步，也不儲存成本、股數或實際損益。</div>
    <form class="villa-form" id="villa-add-form">
      <label class="villa-visually-hidden" for="villa-ticker">股票代號</label>
      <input id="villa-ticker" class="villa-input" placeholder="例：1303、NVDA、0883.HK" autocomplete="off" maxlength="20" required>
      <button class="villa-action" type="submit">＋ 加入清單</button>
    </form>
    <p id="villa-message" role="status" aria-live="polite"></p>
    <div class="villa-private-actions">
      <button class="villa-subtle" type="button" id="villa-export">匯出 JSON 備份</button>
      <button class="villa-subtle" type="button" id="villa-import">匯入備份</button>
      <input type="file" id="villa-file" accept=".json,application/json" class="villa-visually-hidden">
    </div>
    <p class="villa-muted" id="villa-count"></p>
    <div id="villa-list" class="villa-list"></div>`;

  const SNAPSHOT=__SNAPSHOT_JSON__;
  const bySymbol=new Map(SNAPSHOT.map(r=>[r.symbol,r]));
  const KEY='soso-stock-radar-watchlist-v1';
  const MAX_ITEMS=80;
  const msg=document.getElementById('villa-message');
  const tickerInput=document.getElementById('villa-ticker');
  const list=document.getElementById('villa-list');
  const count=document.getElementById('villa-count');
  function say(text){msg.textContent=text;}
  function normalize(ticker){
    let x=String(ticker||'').trim().toUpperCase().replace(/\s+/g,'');
    if(/^\d{4,6}$/.test(x))x+='.TW';
    // TW/TWO/HK ticker or ordinary US symbol; avoid user-controlled HTML.
    if(/^\d{4,6}\.(TW|TWO|HK)$/.test(x)||/^[A-Z][A-Z0-9.\-]{0,14}$/.test(x))return x;
    return null;
  }
  function marketOf(symbol){
    return symbol.endsWith('.TW')||symbol.endsWith('.TWO')?'台股':
      symbol.endsWith('.HK')?'港股':'美股／其他';
  }
  function readList(){
    try{
      const data=JSON.parse(localStorage.getItem(KEY)||'[]');
      if(!Array.isArray(data))return [];
      return Array.from(new Set(data.filter(x=>typeof x==='string').map(normalize).filter(Boolean))).slice(0,MAX_ITEMS);
    }catch(err){return [];}
  }
  let saved=readList();
  function saveList(){
    try{localStorage.setItem(KEY,JSON.stringify(saved));return true;}
    catch(err){say('瀏覽器未允許儲存：這次修改無法持久保存，請檢查網站儲存設定。');return false;}
  }
  function el(tag,className,text){
    const node=document.createElement(tag);
    if(className)node.className=className;
    if(text!==undefined)node.textContent=text;
    return node;
  }
  function metric(parent,label,value){
    const box=el('div');box.append(el('small','',label),el('b','',value));parent.append(box);
  }
  function renderList(){
    list.replaceChildren();
    count.textContent='目前清單：'+saved.length+' 檔（最多 '+MAX_ITEMS+' 檔）';
    if(!saved.length){list.appendChild(el('div','villa-blank','這裡還沒有股票。輸入代號就能建立第一筆私人觀察清單。'));return;}
    for(const symbol of saved){
      const stock=bySymbol.get(symbol);
      const item=el('article','villa-item');
      const head=el('div','villa-item-head');
      const titleWrap=el('div');
      titleWrap.append(el('h3','',stock&&stock.name?stock.name+' · '+symbol:symbol),
        el('p','villa-muted',marketOf(symbol)));
      const remove=el('button','villa-subtle','移除');remove.type='button';
      remove.setAttribute('aria-label','移除'+symbol);
      remove.addEventListener('click',()=>{
        saved=saved.filter(x=>x!==symbol);
        if(saveList()){say('已從此裝置的清單移除 '+symbol);renderList();}
      });
      head.append(titleWrap,remove);item.appendChild(head);
      if(stock){
        const data=el('div','villa-data');
        const price=Number(stock.price),score=Number(stock.score),change=Number(stock.change);
        metric(data,'調整收盤價',Number.isFinite(price)?price.toLocaleString('en-US',{maximumFractionDigits:2})+' '+(stock.market==='台股'?'TWD':'USD'):'—');
        metric(data,'實驗性技術分數',Number.isFinite(score)?score+'/30':'—');
        metric(data,'均線趨勢',stock.trend==='是'?'符合':stock.trend==='否'?'未符合':'—');
        metric(data,'當日漲跌',Number.isFinite(change)?(change>0?'+':'')+change.toFixed(2)+'%':'—');
        item.appendChild(data);
        item.appendChild(el('p','villa-muted','資料日期：'+(stock.date||'—')+'；非即時報價。'+(stock.alert?'研究提醒：'+stock.alert:'目前無預設技術警示。')));
      }else{
        item.appendChild(el('p','villa-muted','此股票不在雷達現有的固定 100 檔掃描池；目前只保存代號，不會假裝有自動更新或即時行情。'));
      }
      list.appendChild(item);
    }
  }
  document.getElementById('villa-add-form').addEventListener('submit',e=>{
    e.preventDefault();const symbol=normalize(tickerInput.value);
    if(!symbol){say('代號格式不符合。範例：1303、1303.TW、NVDA、0883.HK');return;}
    if(saved.includes(symbol)){say('清單裡已經有 '+symbol);return;}
    if(saved.length>=MAX_ITEMS){say('清單最多 '+MAX_ITEMS+' 檔，請先移除部分股票。');return;}
    saved.push(symbol);
    if(saveList()){tickerInput.value='';say('已加入 '+symbol+'（此裝置專用）');renderList();}
  });
  document.getElementById('villa-export').addEventListener('click',()=>{
    const file={type:'soso-radar-watchlist',version:1,exportedAt:new Date().toISOString(),symbols:saved};
    const blob=new Blob([JSON.stringify(file,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download='soso_炒股廚房_備份.json';
    document.body.appendChild(a);a.click();a.remove();
    // Revoke at a later event turn so browsers have time to start the download.
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    say('已產生 JSON 備份。請確認檔案已儲存在手機裡。');
  });
  const fileInput=document.getElementById('villa-file');
  document.getElementById('villa-import').addEventListener('click',()=>fileInput.click());
  fileInput.addEventListener('change',async()=>{
    const file=fileInput.files&&fileInput.files[0];if(!file)return;
    try{
      if(file.size>150000)throw Error('檔案過大');
      const payload=JSON.parse(await file.text());
      if(!payload||payload.type!=='soso-radar-watchlist'||payload.version!==1||!Array.isArray(payload.symbols))
        throw Error('不是炒股廚房支援的 JSON 備份');
      if(payload.symbols.length>MAX_ITEMS)throw Error('備份超過 '+MAX_ITEMS+' 檔限制');
      const next=[];
      for(const item of payload.symbols){
        if(typeof item!=='string'||!normalize(item))throw Error('備份有無效股票代號');
        const value=normalize(item);if(!next.includes(value))next.push(value);
      }
      // Merge, do not silently overwrite current holdings.
      const merged=Array.from(new Set([...saved,...next]));
      if(merged.length>MAX_ITEMS)throw Error('合併後超過 '+MAX_ITEMS+' 檔');
      saved=merged;if(saveList()){say('已合併備份，現在共有 '+saved.length+' 檔');renderList();}
    }catch(err){say('匯入失敗：'+err.message);}
    finally{fileInput.value='';}
  });
  renderList();
})();
"""


def install_villa_hub(path: Path, records) -> None:
    """Augment rendered HTML; never modify scanner, archives, or workflows."""
    text = path.read_text(encoding='utf-8')
    if '/* stock-radar-villa-1.16 */' in text:
        return
    if text.count('</head>') != 1 or text.count('</body>') != 1:
        raise ValueError('網頁結構異常，拒絕安裝別墅入口')
    if 'id="radar-market-tabs"' not in text and '/* Stock Radar 1.12: market navigation */' not in text:
        raise ValueError('三分頁導覽尚未安裝；停止以免破壞舊網頁')
    snapshot = []
    for r in records:
        if r.get('市場') not in ('台股', '美股') or not r.get('股票'):
            continue
        snapshot.append({
            'symbol': str(r['股票']), 'name': str(r.get('中文名稱') or ''),
            'market': str(r['市場']), 'date': str(r.get('交易日期') or ''),
            'price': r.get('調整收盤價'), 'score': r.get('技術分數'),
            'change': r.get('單日漲跌幅'), 'trend': str(r.get('符合趨勢') or ''),
            'alert': str(r.get('研究警示') or ''),
        })
    json_text = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    # No page input is allowed to terminate or mutate the embedded script.
    json_text = json_text.replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
    script = SCRIPT.replace('__SNAPSHOT_JSON__', json_text)
    text = text.replace('</head>', '<style>'+CSS+'</style></head>', 1)
    text = text.replace('</body>', '<script>'+script+'</script></body>', 1)
    path.write_text(text, encoding='utf-8')
