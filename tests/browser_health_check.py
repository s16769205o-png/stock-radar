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
    tiles = [x.bounding_box() for x in root.locator('.rhl-market').all()]
    assert all(x is not None for x in tiles)
    assert tiles[0]['x'] + tiles[0]['width'] <= tiles[1]['x'] + 2, (
        f'Market tiles overlap at width {width}: {tiles}'
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
                assert page.locator('#panel-us').is_hidden()
                page.locator('#tab-us').click()
                assert page.locator('#panel-us').is_visible()
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
    print('PASS: 320px/390px mobile layouts, five villa tabs and fresh/stale status; screenshots saved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--html', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    options = parser.parse_args()
    run(options.html, options.output)
