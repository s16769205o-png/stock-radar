"""Browser smoke test for the *synthetic* stock radar website.

Run only in the GitHub offline preview job. No repository data, deployment,
market API, or authenticated account is used by this script.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def assert_mobile_health(page, width: int):
    root = page.locator('#radar-health-light-v131')
    root.wait_for(state='visible', timeout=15000)
    assert root.count() == 1, 'One health light is required'
    assert root.locator('.rhl-market').count() == 2, 'Both market tiles are required'
    text = root.inner_text()
    for label in ('台股', '美股', '50 / 50', '0050.TW', 'SPY', '最近一次報告產生'):
        assert label in text, f'Missing mobile health text: {label}'
    rect = root.bounding_box()
    assert rect is not None
    assert -1 <= rect['x'] and rect['x'] + rect['width'] <= width + 2, (
        f'Health panel spills outside {width}px viewport: {rect}'
    )
    # Narrow mobile cards must not clip the date or benchmark status.
    for item in root.locator('.rhl-date, .rhl-benchmark-value').all():
        scroll, client = item.evaluate('(el) => [el.scrollWidth, el.clientWidth]')
        assert scroll <= client + 1, (
            f'Date or benchmark label overflows at {width}px: {scroll}/{client}'
        )
    tiles = [x.bounding_box() for x in root.locator('.rhl-market').all()]
    assert all(x is not None for x in tiles)
    assert tiles[0]['x'] + tiles[0]['width'] <= tiles[1]['x'] + 2, (
        f'Market tiles overlap at width {width}: {tiles}'
    )
    vix = page.locator('#vix-overview-v134')
    assert vix.count() == 1, 'One VIX overview card is required'
    assert '非即時行情' in vix.inner_text()
    assert 'VIX' in vix.inner_text()
    bounds = vix.bounding_box()
    assert bounds is not None
    assert bounds['x'] >= -1 and bounds['x'] + bounds['width'] <= width + 2, (
        f'VIX card overflows at {width}px: {bounds}'
    )
    page.locator('#radar-market-tabs').wait_for(state='visible', timeout=15000)
    # The villa hub extends the original three market tabs to five rooms.
    assert page.locator('#radar-market-tabs button').count() == 5, (
        'All five established villa tabs must remain present'
    )
    for key in ('overview', 'tw', 'us', 'famous', 'kitchen'):
        assert page.locator('#tab-' + key).count() == 1


def run(html: Path, output: Path):
    assert html.is_file(), f'No synthetic website found: {html}'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in (320, 390):
                context = browser.new_context(
                    viewport={'width': width, 'height': 844},
                    device_scale_factor=1, is_mobile=True, has_touch=True,
                    locale='zh-TW', timezone_id='Asia/Taipei',
                )
                context.add_init_script(
                    "Date.now = () => Date.parse('2026-11-24T10:00:00+08:00');"
                )
                page = context.new_page()
                page.route('http://**/*', lambda route: route.abort())
                page.route('https://**/*', lambda route: route.abort())
                page.goto(html.resolve().as_uri(), wait_until='domcontentloaded')
                assert_mobile_health(page, width)
                assert page.locator('#rhl-age-warning').is_hidden(), (
                    'Fresh simulated report must not show the age warning'
                )
                assert page.locator('#rhl-status').inner_text() == '本次報告行情完整'
                page.screenshot(path=str(output / f'health-fresh-{width}.png'))
                # Existing phone tabs must continue to work with the new lamp.
                page.locator('#tab-tw').click()
                assert page.locator('#panel-tw').is_visible()
                reading_tw=page.locator('#read138-tw')
                assert reading_tw.count()==1
                assert reading_tw.locator('button[data-mode="all"]').get_attribute('aria-pressed')=='true'
                assert page.locator('#panel-us').is_hidden()
                page.locator('#tab-overview').click()
                assert page.locator('#panel-overview').is_visible(), 'Overview tab must be visible before testing its controls'
                reading_overview=page.locator('#read138-overview')
                assert reading_overview.count()==1
                assert reading_overview.locator('button[data-mode="focus"]').get_attribute('aria-pressed')=='true'
                assert page.locator('#panel-overview > .radar-subgroup[hidden]').count() >= 1
                reading_overview.locator('button[data-mode="all"]').click()
                assert page.locator('#panel-overview > .radar-subgroup[hidden]').count()==0
                reading_overview.locator('button[data-mode="focus"]').click()
                official_index = page.locator('#sector-index-tw')
                official_index.wait_for(state='visible', timeout=10000)
                comparison = official_index.locator('details.sector-research-extra')
                assert comparison.count() == 1, 'Research-pool price strength must be inside TW index'
                assert not comparison.evaluate('(n) => n.open'), 'Extra price table must start folded'
                comparison.locator('summary').click()
                assert comparison.evaluate('(n) => n.open')
                assert '台股研究池｜族群強弱' in comparison.inner_text()
                assert comparison.locator('table').count() == 1
                assert page.locator('#panel-tw > .radar-subgroup').filter(has_text='台股研究池｜族群強弱').count() == 0
                comparison.locator('summary').click()
                pulse = page.locator('#sector-pulse-v132')
                pulse.scroll_into_view_if_needed()
                assert pulse.is_visible(), 'Taiwan sector evidence must be accessible'
                assert pulse.locator('.sp132-card').count() >= 1
                assert '不打分' in pulse.inner_text()
                bounds = pulse.bounding_box()
                assert bounds is not None
                assert bounds['x'] >= -1 and bounds['x'] + bounds['width'] <= width + 2, (
                    f'Sector pulse overflows {width}px mobile viewport: {bounds}'
                )
                pulse.screenshot(path=str(output / f'sector-pulse-{width}.png'))
                page.locator('#tab-us').click()
                assert page.locator('#panel-us').is_visible()
                reading_us=page.locator('#read138-us')
                assert reading_us.count()==1
                assert reading_us.locator('button[data-mode="all"]').get_attribute('aria-pressed')=='true'
                reading_us.locator('button[data-mode="focus"]').click()
                assert page.locator('#panel-us > .radar-subgroup[hidden]').count()>=1
                reading_us.locator('select').select_option('0')
                assert reading_us.locator('button[data-mode="all"]').get_attribute('aria-pressed')=='true'
                assert page.locator('#panel-us > .radar-subgroup[hidden]').count()==0
                assert page.locator('#panel-us').get_by_text('美股研究池｜族群強弱').count() == 1
                guide=page.locator('#panel-us #us-hours-v135')
                assert guide.count()==1 and guide.is_visible()
                assert '不是即時夜盤報價' in guide.inner_text()
                bounds=guide.bounding_box()
                assert bounds and bounds['x'] >= -1 and bounds['x']+bounds['width'] <= width+2
                guide.locator('summary').click()
                assert guide.locator('details').evaluate('(d)=>d.open')
                fundamentals=page.locator('#panel-us #us-fundamentals-v136')
                assert fundamentals.count()==1 and fundamentals.is_visible()
                assert not fundamentals.locator('details').evaluate('(d)=>d.open')
                fundamentals.locator('summary').click()
                assert fundamentals.locator('details').evaluate('(d)=>d.open')
                assert fundamentals.locator('.uf136-company').count()==8
                assert fundamentals.locator('.uf137-audit').count()==8
                assert 'SEC 官方核對尚未啟用' in fundamentals.inner_text()
                assert '未逐筆核對 SEC 原始申報' in fundamentals.inner_text()
                rect=fundamentals.bounding_box()
                assert rect and rect['x']>=-1 and rect['x']+rect['width']<=width+2
                page.locator('#tab-famous').click()
                assert page.locator('#panel-famous').is_visible()
                page.locator('#tab-kitchen').click()
                assert page.locator('#panel-kitchen').is_visible()
                page.locator('#tab-overview').click()
                assert page.locator('#panel-overview').is_visible()
                context.close()

            context = browser.new_context(
                viewport={'width': 390, 'height': 844},
                device_scale_factor=1, is_mobile=True, has_touch=True,
                locale='zh-TW', timezone_id='Asia/Taipei',
            )
            context.add_init_script(
                "Date.now = () => Date.parse('2026-11-27T12:00:00+08:00');"
            )
            page = context.new_page()
            page.route('http://**/*', lambda route: route.abort())
            page.route('https://**/*', lambda route: route.abort())
            page.goto(html.resolve().as_uri(), wait_until='domcontentloaded')
            assert_mobile_health(page, 390)
            assert page.locator('#rhl-age-warning').is_visible(), (
                'Report older than 72h must show stale warning in browser'
            )
            assert page.locator('#rhl-status').inner_text() == '資料較舊，請核對日期'
            page.screenshot(path=str(output / 'health-stale-390.png'))
            context.close()
        finally:
            browser.close()
    print('PASS: 320px/390px mobile layouts, five villa tabs, v1.32 sector pulse and fresh/stale status; screenshots saved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--html', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    options = parser.parse_args()
    run(options.html, options.output)
