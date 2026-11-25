"""1.38 optional reading-mode controls. Never edits report numbers or archives.

A small progressive enhancement for the existing five-tab stock villa:
- Overview defaults to compact (all extra research stays discoverable).
- Taiwan, US, famous and kitchen tabs keep prior full default visibility.
- Every section is reachable via an accessible jump menu.
- Compact/full state is browser-local only and can always be overridden.
"""
from pathlib import Path

CSS = r"""
/* stock-radar-reading-mode-v138 */
.read138{margin:12px 0 16px;border:1px solid #d7e3ef;border-radius:13px;
 background:#fff;padding:11px 12px;color:#364e69;}
.read138 .read138-row{display:flex;align-items:center;justify-content:space-between;
 gap:8px;flex-wrap:wrap;}
.read138 strong{font-size:.91rem}
.read138 .read138-actions{display:flex;gap:6px;flex-wrap:wrap}
.read138 button{border:1px solid #bccedd;border-radius:9px;background:#fff;
 padding:8px 10px;color:#385676;font:650 .79rem system-ui;cursor:pointer}
.read138 button[aria-pressed="true"]{background:#e4f0fc;border-color:#4e83b9;color:#1d568c}
.read138 button:focus-visible,.read138 select:focus-visible{outline:3px solid #4b87d1}
.read138 .read138-jump{display:flex;align-items:center;gap:8px;margin-top:10px;
 flex-wrap:wrap}
.read138 label{font-size:.77rem;color:#566c82}
.read138 select{max-width:100%;min-width:0;flex:1 1 175px;
 border:1px solid #b9c9dc;border-radius:9px;padding:9px 8px;
 font:inherit;font-size:.82rem;background:#fff;color:#344e6c}
.read138 .read138-message{font-size:.75rem;color:#61758b;line-height:1.5;margin:8px 0 0}
.read138 [hidden]{display:none!important}
"""

SCRIPT = r"""
/* stock-radar-reading-mode-v138-mount */
(function(){
  'use strict';
  if(document.getElementById('read138-overview'))return;
  const panels=['overview','tw','us'];
  // Intentionally do not modify the two private/custom rooms.
  for(const key of panels){
    const panel=document.getElementById('panel-'+key);
    if(!panel)continue;
    const sections=Array.from(panel.children).filter(el=>
      el.classList&&el.classList.contains('radar-subgroup'));
    if(!sections.length)continue;
    const control=document.createElement('div');
    control.className='read138';
    control.id='read138-'+key;
    control.setAttribute('role','group');
    control.setAttribute('aria-label','研究頁面閱讀模式');
    const bar=document.createElement('div');bar.className='read138-row';
    const title=document.createElement('strong');title.textContent='📖 閱讀模式';
    const buttons=document.createElement('div');buttons.className='read138-actions';
    function makeButton(mode,label){
      const btn=document.createElement('button');btn.type='button';
      btn.textContent=label;btn.dataset.mode=mode;btn.setAttribute('aria-pressed','false');
      buttons.appendChild(btn);return btn;
    }
    const focusButton=makeButton('focus','重點速覽');
    const allButton=makeButton('all','完整研究');
    bar.append(title,buttons);
    const jump=document.createElement('div');jump.className='read138-jump';
    const label=document.createElement('label');
    const select=document.createElement('select');
    select.id='read138-select-'+key;
    label.htmlFor=select.id;label.textContent='直接前往';
    const placeholder=document.createElement('option');
    placeholder.value='';placeholder.textContent='選擇研究項目…';
    select.appendChild(placeholder);
    for(let i=0;i<sections.length;i++){
      const section=sections[i];
      const heading=section.querySelector('h2,h3');
      const option=document.createElement('option');option.value=String(i);
      // Never use innerHTML from source headings.
      option.textContent=(heading?.textContent||'研究項目 '+(i+1)).trim().slice(0,85);
      select.appendChild(option);
    }
    jump.append(label,select);
    const message=document.createElement('p');
    message.className='read138-message';message.setAttribute('role','status');
    control.append(bar,jump,message);
    panel.insertBefore(control,panel.firstChild);
    function essential(section,index){
      if(key==='overview')return index===0; // Existing villa floor directory
      const heading=(section.querySelector('h2,h3')?.textContent||'').trim();
      return heading.includes('技術排名前10')||heading.includes('研究池｜族群強弱');
    }
    function setMode(mode){
      const compact=mode==='focus';
      let hidden=0;
      sections.forEach((section,index)=>{
        const hide=compact&&!essential(section,index);
        section.hidden=hide;if(hide)hidden++;
      });
      focusButton.setAttribute('aria-pressed',String(compact));
      allButton.setAttribute('aria-pressed',String(!compact));
      message.textContent=compact?
        ('已收起 '+hidden+' 個次要研究區；資料仍完整保留，可用下拉選單直達。'):
        ('全部 '+sections.length+' 個研究區已展開；資料及計算方式未更動。');
    }
    buttons.addEventListener('click',event=>{
      const btn=event.target.closest('button[data-mode]');
      if(btn&&buttons.contains(btn))setMode(btn.dataset.mode);
    });
    select.addEventListener('change',()=>{
      if(select.value==='')return;
      const index=Number(select.value);
      if(!Number.isInteger(index)||index<0||index>=sections.length)return;
      setMode('all');
      sections[index].scrollIntoView({block:'start',behavior:'auto'});
      const heading=sections[index].querySelector('h2,h3');
      if(heading){
        heading.setAttribute('tabindex','-1');
        heading.focus({preventScroll:true});
      }
    });
    // Preserve the existing full TW/US research experience. The Overview is
    // intentionally shorter by default without deleting any contents.
    setMode(key==='overview'?'focus':'all');
  }
})();
"""


def install_reading_mode(path: Path):
    """Install once at end of render; JS progressively enhances existing tabs."""
    path=Path(path)
    page=path.read_text(encoding="utf-8")
    if "/* stock-radar-reading-mode-v138-mount */" in page:
        return
    if page.count("</head>")!=1 or page.count("</body>")!=1:
        raise ValueError("閱讀模式：HTML 結構異常")
    if "/* stock-radar-villa-1.18 */" not in page:
        raise ValueError("閱讀模式：缺少股票別墅五分頁")
    page=page.replace("</head>","<style>"+CSS+"</style></head>",1)
    page=page.replace("</body>","<script>"+SCRIPT+"</script></body>",1)
    path.write_text(page,encoding="utf-8")
