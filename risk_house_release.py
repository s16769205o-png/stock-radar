"""Publish private holdings page alongside the LAST successfully generated report.

This deploy-only path never fetches quotes, recomputes signals or commits user
holdings. It copies precisely the existing public report, its public CSV sources,
and the two static app files. A temporary kitchen shortcut is inserted into the
DEPLOY ARTIFACT when the existing report predates the new kitchen link.
"""
from __future__ import annotations

import shutil
from pathlib import Path

MARKER = "/* risk-house-quick-link-v1 */"
# Deployed HTML only. No person-specific records or remote scripts.
SHORTCUT = """<script>
/* risk-house-quick-link-v1 */
document.addEventListener('DOMContentLoaded',function(){
  const kitchen=document.getElementById('panel-kitchen');
  if(!kitchen||kitchen.querySelector('a[href="./holdings-risk.html"]'))return;
  const note=document.createElement('p');
  note.className='villa-note';
  const link=document.createElement('a');
  link.href='./holdings-risk.html';
  link.textContent='🛡️ 開啟獨立持股風控屋（私人資料只在本機）';
  note.appendChild(link);
  kitchen.insertBefore(note,kitchen.firstChild);
});
</script>
"""


def build_static_release(root: Path, out: Path) -> None:
    """Fail closed if last known report or private application files are missing."""
    root, out = Path(root), Path(out)
    original = (root / "index.html").read_text(encoding="utf-8")
    if ("STOCK RESEARCH LAB · 1.38" not in original
            or "/* stock-radar-villa-1.18 */" not in original
            or original.count("</body>") != 1):
        raise ValueError("既有已驗收的股票報告不存在，拒絕發布")
    app = (root / "holdings-risk.html").read_text(encoding="utf-8")
    js = (root / "risk_house_v1.js").read_text(encoding="utf-8")
    if ('src="./risk_house_v1.js"' not in app
            or 'soso-risk-house-v1' not in js
            or len(js) < 5000):
        raise ValueError("持股風控屋程式不完整，拒絕發布")
    if MARKER not in original and './holdings-risk.html' not in original:
        original = original.replace("</body>", SHORTCUT + "</body>", 1)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(original, encoding="utf-8")
    (out / "holdings-risk.html").write_text(app, encoding="utf-8")
    (out / "risk_house_v1.js").write_text(js, encoding="utf-8")
    for filename in ("history.csv", "monthly_revenue.csv", "quarterly_profit.csv"):
        source = root / "data" / filename
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError("原報告公開資料缺漏：" + filename)
        dest = out / "data" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    # Never upload a private holdings JSON. Artifact uses a closed file allowlist.
    assert sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()) == [
        "data/history.csv", "data/monthly_revenue.csv",
        "data/quarterly_profit.csv", "holdings-risk.html",
        "index.html", "risk_house_v1.js",
    ]


if __name__ == "__main__":
    build_static_release(Path(__file__).resolve().parent,
                         Path(__file__).resolve().parent / "_site")
    print("Published existing verified report + empty private holdings app only")
