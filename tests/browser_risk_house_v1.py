"""Real Chromium check for the *separate*, browser-private risk house.

Run in the existing offline CI browser job. Serves ONLY local repository code
over 127.0.0.1; tests never query market providers or publish holdings.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass


def verify(browser,base,width,output):
    context=browser.new_context(
        viewport={"width":width,"height":844},
        device_scale_factor=1,is_mobile=True,has_touch=True,
        locale="zh-TW",timezone_id="Asia/Taipei",
        accept_downloads=True,
    )
    page=context.new_page()
    requested=[]
    page.on("request",lambda req: requested.append(req.url))
    page.goto(base+"/holdings-risk.html",wait_until="load")
    assert page.title().startswith("🛡️ 小G持股風控屋")
    assert page.locator("#stat-count").inner_text()=="0"
    assert page.locator("#holdings").get_by_text("新增第一檔持股").count()==1
    # Exactly same origin as existing kitchen; never use GitHub API to fetch secrets.
    page.evaluate("""() => {
      localStorage.setItem('soso-stock-radar-watchlist-v1',
        JSON.stringify(['DEMO','0001.HK','MSFT']));
      localStorage.setItem('soso-stock-radar-holdings-v1',
        JSON.stringify({
          'DEMO':{status:'holding',quantity:10,cost:3.21,note:'示例科技股'},
          '0001.HK':{status:'holding',quantity:2,cost:14.7,note:'示例港股'},
          'MSFT':{status:'watch',quantity:100,cost:10,note:'未持有'}
        }));
    }""")
    kitchen_before=page.evaluate("localStorage.getItem('soso-stock-radar-holdings-v1')")
    page.locator("#sync-kitchen").click()
    assert page.locator("#stat-count").inner_text()=="2"
    assert page.locator("#stat-missing").inner_text()=="2"
    assert page.locator(".holding").count()==2
    assert page.locator(".holding").filter(has_text="MSFT").count()==0
    assert page.locator("#stat-alert").inner_text()=="0"
    # No price -> no pretend sell advice; all partial input remains private.
    assert "暫停完整配置比重警報" in page.locator("#coverage").inner_text()
    today=date.today().isoformat()
    shell=page.locator(".holding").filter(has_text="DEMO")
    shell.get_by_role("button",name="✏️ 編輯").click()
    assert page.locator("#editor").evaluate("(n)=>n.open")
    page.locator('input[name="price"]').fill("100")
    page.locator('input[name="fx"]').fill("30")
    page.locator('input[name="priceDate"]').fill(today)
    page.locator('input[name="peak"]').fill("150")
    page.locator('input[name="maxWeight"]').fill("20")
    page.locator('input[name="maxDrawdown"]').fill("20")
    page.locator('select[name="thesis"]').select_option("no")
    page.locator('input[name="reviewDate"]').fill(today)
    page.locator('textarea[name="note"]').fill('<img src=x onerror="alert(1)">')
    page.get_by_role("button",name="保存這檔").click()
    assert page.locator("#stat-alert").inner_text()=="1"
    assert page.locator("#stat-missing").inner_text()=="1"
    assert "持有理由已改變" in page.locator("#holdings").inner_text()
    assert "暫停完整配置比重警報" in page.locator("#coverage").inner_text()
    assert page.locator("#holdings img").count()==0, "Private notes must use textContent"
    # Fill second holding to permit known-position allocation comparisons.
    other=page.locator(".holding").filter(has_text="0001.HK")
    other.get_by_role("button",name="✏️ 編輯").click()
    page.locator('input[name="price"]').fill("100")
    page.locator('input[name="fx"]').fill("4")
    page.locator('input[name="priceDate"]').fill(today)
    page.locator('select[name="role"]').select_option("cyclical")
    page.locator('select[name="thesis"]').select_option("yes")
    page.locator('input[name="reviewDate"]').fill(today)
    page.get_by_role("button",name="保存這檔").click()
    assert page.locator("#stat-count").inner_text()=="2"
    assert page.locator("#stat-missing").inner_text()=="0"
    assert "已估持股合計" in page.locator("#coverage").inner_text()
    assert "超過妳自訂的 20%" in page.locator("#holdings").inner_text()
    assert "達到妳自訂的 20%" in page.locator("#holdings").inner_text()
    assert page.evaluate("localStorage.getItem('soso-stock-radar-holdings-v1')")==kitchen_before
    # App state survives page reload; it is NOT in the public source.
    page.reload(wait_until="load")
    assert page.locator("#stat-count").inner_text()=="2"
    assert page.locator("#stat-alert").inner_text()=="1"
    page.locator('[data-filter="alerts"]').click()
    assert page.locator(".holding").count()==1
    assert page.locator(".holding").filter(has_text="DEMO").count()==1
    page.locator('[data-filter="all"]').click()
    # Export is local, not a network call; inspect the actual downloaded file.
    with page.expect_download() as download_info:
        page.locator("#export-data").click()
    download=download_info.value
    target=output/f"risk-private-export-{width}.json"
    download.save_as(target)
    exported=json.loads(target.read_text(encoding="utf-8"))
    assert exported["type"]=="soso-private-risk-house"
    assert len(exported["holdings"])==2
    assert any(x["symbol"]=="DEMO" for x in exported["holdings"])
    assert all(u.startswith(base+"/") for u in requested),requested
    scroll_width=page.evaluate("document.documentElement.scrollWidth")
    assert scroll_width <= width+2, f"risk-house overflows: width={width} document={scroll_width}"
    page.screenshot(path=str(output/f"risk-house-{width}.png"),full_page=True)
    context.close()


def main(out):
    output=Path(out)
    output.mkdir(parents=True,exist_ok=True)
    handler=partial(QuietHandler,directory=str(ROOT))
    server=ThreadingHTTPServer(("127.0.0.1",0),handler)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            try:
                for width in (320,390):
                    verify(browser,base,width,output)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print("PASS: private holdings risk-house CRUD, kitchen import, offline privacy, evidence alerts, 320/390 mobile screens")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    main(args.output)
