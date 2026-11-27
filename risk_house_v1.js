/* 小G持股風控屋 v1.0 — local browser only; no market API, no trade action. */
(function(){
"use strict";
const KEY="soso-risk-house-v1", KITCHEN_LIST="soso-stock-radar-watchlist-v1";
const KITCHEN_META="soso-stock-radar-holdings-v1", LIMIT=100;
const ROLES={core:"長期核心",growth:"成長／進攻",cyclical:"景氣循環",income:"收息型",bond:"債券／到期持有",other:"其他"};
const THEMES={broad:"大盤股票",tech:"科技／AI",energy:"能源",property:"房地產／保險",industrials:"工業／航運／原物料",bonds:"利率／債券",other:"其他／待分類"};
const CURRENCIES=["TWD","USD","HKD","CNY","OTHER"];
const $=id=>document.getElementById(id);
const form=$("holding-form"), list=$("holdings"), editor=$("editor");
let holdings=[], editing=null, filter="all";

function notify(message){$("status").textContent=message;}
function normalize(raw){
  let s=String(raw||"").trim().toUpperCase().replace(/\s+/g,"");
  if(/^[0-9]{4,6}$/.test(s))s+=".TW";
  return (/^[0-9]{1,6}\.(TW|TWO|HK)$/.test(s)||/^[A-Z][A-Z0-9.\-]{0,14}$/.test(s))?s:null;
}
function currencyOf(symbol){return /\.(TW|TWO)$/.test(symbol)?"TWD":/\.HK$/.test(symbol)?"HKD":"USD";}
function num(raw,max=1e12){
  if(raw===null||raw===undefined||raw==="")return null;
  if(typeof raw==="boolean")return null;
  const v=Number(raw);
  return Number.isFinite(v)&&v>=0&&v<=max?v:null;
}
function validDay(str){
  if(typeof str!=="string"||!/^\d{4}-\d{2}-\d{2}$/.test(str))return "";
  const d=new Date(str+"T00:00:00Z");
  return !isNaN(d)&&d.toISOString().slice(0,10)===str?str:"";
}
function ageDays(str){
  const good=validDay(str);if(!good)return null;
  const base=Date.parse(new Date().toISOString().slice(0,10)+"T00:00:00Z");
  return Math.round((base-Date.parse(good+"T00:00:00Z"))/86400000);
}
function clean(raw){
  if(!raw||typeof raw!=="object"||Array.isArray(raw))return null;
  const symbol=normalize(raw.symbol);if(!symbol)return null;
  const role=Object.hasOwn(ROLES,raw.role)?raw.role:"other";
  const theme=Object.hasOwn(THEMES,raw.theme)?raw.theme:"other";
  const currency=CURRENCIES.includes(raw.currency)?raw.currency:currencyOf(symbol);
  const fx=num(raw.fx,1e6);
  return {
    symbol,name:typeof raw.name==="string"?raw.name.slice(0,40):"",
    role,theme,currency,quantity:num(raw.quantity,1e9),cost:num(raw.cost,1e12),
    price:num(raw.price,1e12),priceDate:validDay(raw.priceDate),
    fx:currency==="TWD"&&fx===null?1:fx,
    peak:num(raw.peak,1e12),maxWeight:num(raw.maxWeight,100),
    maxDrawdown:num(raw.maxDrawdown,100),
    thesis:["yes","question","no","unknown"].includes(raw.thesis)?raw.thesis:"unknown",
    reviewDate:validDay(raw.reviewDate),
    note:typeof raw.note==="string"?raw.note.slice(0,350):""
  };
}
function load(){
  try{
    const value=JSON.parse(localStorage.getItem(KEY)||"[]");
    if(!Array.isArray(value))return [];
    const found=new Set();
    return value.slice(0,LIMIT).map(clean).filter(x=>{
      if(!x||found.has(x.symbol))return false;
      found.add(x.symbol);return true;
    });
  }catch(err){notify("⚠️ 無法讀取本機持股，請檢查瀏覽器儲存權限。");return [];}
}
function save(){
  try{localStorage.setItem(KEY,JSON.stringify(holdings));return true;}
  catch(err){notify("⚠️ 儲存失敗：瀏覽器空間不足或禁止本機儲存。");return false;}
}
function node(tag,text,cls){
  const e=document.createElement(tag);
  if(cls)e.className=cls;
  if(text!==undefined)e.textContent=String(text);
  return e;
}
function btn(label,fn,cls){
  const b=node("button",label,cls);b.type="button";b.addEventListener("click",fn);return b;
}
function money(x,dec=0){return x===null||!Number.isFinite(x)?"—":x.toLocaleString("zh-TW",{maximumFractionDigits:dec});}
function calculate(){
  const rows=holdings.map(h=>{
    const age=ageDays(h.priceDate),haveValues=h.quantity>0&&h.price>0&&h.fx>0;
    const goodDate=age!==null&&age>=0&&age<=7;
    const value=haveValues?h.quantity*h.price*h.fx:null;
    const valid=Number.isFinite(value)&&value>0&&goodDate;
    const stale=age===null||age<0||age>7;
    let dd=null;
    if(h.role!=="bond"&&h.price>0&&h.peak>0&&h.peak>=h.price){
      dd=(1-h.price/h.peak)*100;
    }
    return {h,age,value,valid,stale,dd};
  });
  const fullyCovered=rows.length>0&&rows.every(r=>r.valid);
  const total=rows.filter(r=>r.valid).reduce((sum,r)=>sum+r.value,0);
  const evaluated=rows.map(r=>{
    const h=r.h, alerts=[], info=[];
    const ratio=fullyCovered&&total>0?r.value/total*100:null;
    if(h.thesis==="no")alerts.push({level:"high",label:"持有理由已改變：應優先重新檢視持有邏輯、配置與替代方案，並非自動賣出。"});
    if(h.thesis==="question")alerts.push({level:"alert",label:"持有理由存疑：請核對最近財報或重大事件。"});
    if(r.stale){
      info.push("價格日期缺漏、未來日期或超過 7 天；本次不做價格方向警報。");
    }
    if(!r.valid){
      info.push("未有新鮮且完整的股數／價格／匯率；無法可靠估值。");
    }
    if(!fullyCovered){
      info.push("持股尚未全部估值，暫停依整體持股比重發出減碼警報。");
    }else if(h.maxWeight!==null&&ratio>h.maxWeight+0.00001){
      alerts.push({level:"alert",label:"在已輸入持股中約占 "+ratio.toFixed(1)+"%，超過妳自訂的 "+money(h.maxWeight,1)+"% 上限；可研究是否再平衡，須另考慮未輸入的現金與資產。"});
    }
    if(h.maxDrawdown!==null&&r.valid&&h.role!=="bond"){
      if(r.dd!==null&&r.dd>=h.maxDrawdown-0.00001)
        alerts.push({level:"alert",label:"從填寫的持有後高點回撤約 "+r.dd.toFixed(1)+"%，達到妳自訂的 "+money(h.maxDrawdown,1)+"% 觀察門檻。這不是已驗證的賣出訊號。"});
      else if(h.peak===null||h.peak===0||h.peak<h.price)
        info.push("高點尚未填寫或低於現價，因此無法判定回撤。");
    }
    if(h.role==="bond"&&h.maxDrawdown!==null)
      info.push("債券的持有到期、信用與利率風險不能只靠價格回撤判斷。");
    if(h.thesis==="unknown")info.push("尚未確認原始持有理由是否成立。");
    if(!h.reviewDate)info.push("最近一次研究日期未填寫。");
    const priority=alerts.some(a=>a.level==="high")?3:alerts.length?2:r.valid?0:1;
    return {...r,ratio,alerts,info,priority};
  });
  return {rows:evaluated,fullyCovered,total,validCount:rows.filter(r=>r.valid).length};
}
function render(){
  const report=calculate(), rows=report.rows;
  $("stat-count").textContent=String(rows.length);
  $("stat-alert").textContent=String(rows.filter(r=>r.alerts.length).length);
  $("stat-missing").textContent=String(rows.filter(r=>!r.valid).length);
  $("coverage").textContent=rows.length===0?
    "這裡還沒有持股，先從炒股廚房讀入，或自行新增。":
    report.fullyCovered?
      "已估持股合計約 NT$"+money(report.total)+"；比重只以本工具輸入的持股為分母，不代表全部財產，也未涵蓋未輸入的現金等資產。":
      "目前 "+report.validCount+"/"+rows.length+" 檔有完整且近期價格；因部分資料缺漏，暫停完整配置比重警報。";
  list.replaceChildren();
  const subset=rows.filter(r=>filter==="all"||(filter==="alerts"&&r.alerts.length)||(filter==="missing"&&!r.valid));
  if(!subset.length){
    list.append(node("p",rows.length?"這個篩選條件下沒有持股。":"從炒股廚房匯入，或新增第一檔持股。","empty"));
    return;
  }
  subset.sort((a,b)=>b.priority-a.priority||a.h.symbol.localeCompare(b.h.symbol));
  for(const r of subset){
    const h=r.h, card=node("article",undefined,"holding");
    const head=node("div",undefined,"holding-head");
    const left=node("div");
    left.append(node("div",(h.name?h.name+" · ":"")+h.symbol,"holding-title"));
    left.append(node("div",ROLES[h.role]+"｜"+THEMES[h.theme]+"｜"+h.currency,"holding-meta"));
    const tags=node("div",undefined,"tags");
    tags.append(node("span",r.alerts.some(a=>a.level==="high")?"優先研究":r.alerts.length?"需要研究":r.valid?"正常追蹤":"資料不足",
      "tag "+(r.alerts.some(a=>a.level==="high")?"danger":r.alerts.length?"warn":r.valid?"ok":"")));
    head.append(left,tags);card.append(head);
    const metrics=node("dl");
    function metric(label,val){const d=node("div");d.append(node("dt",label),node("dd",val));metrics.append(d);}
    metric("數量",h.quantity===null?"待填":money(h.quantity,3));
    metric("最近參考價",h.price>0?money(h.price,4)+" "+h.currency:"待填");
    metric("價格日期",h.priceDate||"待填");
    metric("估計台幣市值",r.valid?"NT$"+money(r.value):"—");
    metric("已輸入持股比重",r.ratio!==null?r.ratio.toFixed(1)+"%":"—");
    metric("高點回撤",r.dd!==null&&r.valid?r.dd.toFixed(1)+"%":"—");
    card.append(metrics);
    const risks=node("ul",undefined,"risks");
    for(const alert of r.alerts)risks.append(node("li","⚠️ "+alert.label,alert.level));
    if(!r.alerts.length)risks.append(node("li","目前沒有觸發已設定的警報；不代表資產沒有風險。"));
    for(const item of r.info)risks.append(node("li","ℹ️ "+item));
    card.append(risks);
    if(h.note)card.append(node("p","🗒️ "+h.note,"muted"));
    const buttons=node("div",undefined,"holding-buttons");
    buttons.append(btn("✏️ 編輯",()=>edit(h.symbol)));
    buttons.append(btn("移除",()=>{
      if(!confirm("確定從風控屋移除 "+h.symbol+"？炒股廚房的原始資料不會受影響。"))return;
      const old=holdings;holdings=holdings.filter(x=>x.symbol!==h.symbol);
      if(!save())holdings=old;
      else {notify("已移除 "+h.symbol+"，炒股廚房清單保持不變。");render();}
    }));
    card.append(buttons);list.append(card);
  }
}
function resetEditor(){
  editing=null;form.reset();form.elements.symbol.readOnly=false;
  form.elements.currency.value="TWD";
  form.elements.fx.value="1";
  $("field-symbol").placeholder="例如 SHEL、0050.TW、0883.HK";
}
function edit(symbol){
  const h=holdings.find(x=>x.symbol===symbol);if(!h)return;
  resetEditor();editing=symbol;
  for(const [key,val] of Object.entries(h)){
    const el=form.elements.namedItem(key);
    if(el)el.value=val===null?"":String(val);
  }
  form.elements.symbol.readOnly=true;editor.open=true;
  editor.scrollIntoView({behavior:"auto",block:"start"});
  form.elements.name.focus({preventScroll:true});
}
function apply(){
  const raw={};
  for(const name of ["symbol","name","role","theme","currency","quantity","cost","price","priceDate","fx","peak","maxWeight","maxDrawdown","thesis","reviewDate","note"])
    raw[name]=form.elements.namedItem(name).value;
  // Keep absent numeric fields truly null rather than zero.
  for(const name of ["quantity","cost","price","fx","peak","maxWeight","maxDrawdown"])
    if(raw[name]==="")raw[name]=null;
  const h=clean(raw);
  if(!h){notify("請輸入有效股票代號。");return;}
  for(const key of ["quantity","cost","price","fx","peak","maxWeight","maxDrawdown"]){
    if(raw[key]!==null&&num(raw[key],["maxWeight","maxDrawdown"].includes(key)?100:1e12)===null){
      notify("「"+key+"」必須是有效、非負的數字。");return;
    }
  }
  if(raw.priceDate&&!h.priceDate){notify("價格日期無效。");return;}
  if(h.priceDate&&ageDays(h.priceDate)<0){notify("價格日期不可晚於今天。");return;}
  if(editing){
    const index=holdings.findIndex(x=>x.symbol===editing);
    if(index<0)return;
    const old=holdings[index];holdings[index]=h;
    if(!save())holdings[index]=old;
  }else{
    if(holdings.some(x=>x.symbol===h.symbol)){notify("這檔股票已存在，請點擊編輯。");return;}
    if(holdings.length>=LIMIT){notify("清單最多 "+LIMIT+" 檔。");return;}
    holdings.push(h);
    if(!save())holdings.pop();
  }
  notify("已在此裝置保存 "+h.symbol+"，請記得匯出私人備份。");
  resetEditor();editor.open=false;render();
}
function importKitchen(){
  let symbols,meta;
  try{
    symbols=JSON.parse(localStorage.getItem(KITCHEN_LIST)||"[]");
    meta=JSON.parse(localStorage.getItem(KITCHEN_META)||"{}");
  }catch(err){notify("廚房資料讀取失敗。請先開啟同一網站的炒股廚房。");return;}
  if(!Array.isArray(symbols)||!meta||typeof meta!=="object"){
    notify("廚房資料格式不符，沒有更動風控屋。");return;
  }
  let added=0,skipped=0;
  const existing=new Set(holdings.map(x=>x.symbol));
  const next=[...holdings];
  for(const item of symbols.slice(0,100)){
    const symbol=normalize(item),m=symbol&&meta[symbol];
    if(!symbol||!m||m.status!=="holding")continue;
    if(existing.has(symbol)){skipped++;continue;}
    if(next.length>=LIMIT)break;
    const raw={symbol,name:"",role:"other",theme:"other",
      currency:currencyOf(symbol),quantity:m.quantity,cost:m.cost,
      fx:currencyOf(symbol)==="TWD"?1:null,
      note:typeof m.note==="string"?m.note:"",
      thesis:"unknown"};
    const h=clean(raw);if(!h)continue;
    next.push(h);existing.add(symbol);added++;
  }
  const old=holdings;holdings=next;
  if(!save()){holdings=old;return;}
  render();notify("已從同網站炒股廚房加入 "+added+" 檔已持有股票；略過已有 "+skipped+" 檔。沒有匯入觀察清單，也沒有上傳任何資料。");
}
function exportBackup(){
  const data={type:"soso-private-risk-house",version:1,
    exportedAt:new Date().toISOString(),holdings};
  const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
  const url=URL.createObjectURL(blob);
  const a=node("a");a.href=url;a.download="小G持股風控屋_私人備份.json";
  document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1500);
  notify("已產生私人 JSON 備份，請確認手機有保存。檔案內含股數與成本，請小心保管。");
}
async function importBackup(file){
  if(!file||file.size>600000){notify("備份不存在或超過 600KB。");return;}
  try{
    const obj=JSON.parse(await file.text());
    if(obj?.type!=="soso-private-risk-house"||obj.version!==1||!Array.isArray(obj.holdings))
      throw new Error("不支援的備份格式");
    if(obj.holdings.length>LIMIT)throw new Error("備份持股太多");
    const next=[...holdings],known=new Set(holdings.map(h=>h.symbol));
    let count=0;
    for(const item of obj.holdings){
      const h=clean(item);if(!h)throw new Error("備份內有無效股票資料");
      if(known.has(h.symbol))continue;
      next.push(h);known.add(h.symbol);count++;
      if(next.length>LIMIT)throw new Error("合併超過持股上限");
    }
    const old=holdings;holdings=next;
    if(!save()){holdings=old;return;}
    render();notify("已合併 "+count+" 檔；原本已有的持股不會被備份覆蓋。");
  }catch(err){notify("匯入失敗："+err.message);}
}
$("sync-kitchen").addEventListener("click",importKitchen);
$("add-holding").addEventListener("click",()=>{resetEditor();editor.open=true;editor.scrollIntoView({block:"start"});form.elements.symbol.focus({preventScroll:true});});
$("cancel-edit").addEventListener("click",()=>{resetEditor();editor.open=false;});
form.addEventListener("submit",e=>{e.preventDefault();apply();});
$("export-data").addEventListener("click",exportBackup);
$("import-data").addEventListener("click",()=>$("import-file").click());
$("import-file").addEventListener("change",async e=>{
  const file=e.target.files?.[0];if(file)await importBackup(file);
  e.target.value="";
});
document.querySelectorAll("[data-filter]").forEach(b=>b.addEventListener("click",()=>{
  filter=b.dataset.filter;
  document.querySelectorAll("[data-filter]").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  render();
}));
form.elements.symbol.addEventListener("change",()=>{
  if(editing)return;
  const s=normalize(form.elements.symbol.value);
  if(s){
    const c=currencyOf(s);form.elements.currency.value=c;
    form.elements.fx.value=c==="TWD"?"1":"";
  }
});
holdings=load();resetEditor();render();
})();
