"""Fixture Replay browser acceptance. Claude runs under testlock; serve prototype on 8819.
BASE=http://127.0.0.1:8819 OUT=<artifact directory> py tools/v2_replay_probe.py
No production backend required. Real touch/44 pt and screen-reader QA remain manual.
"""
import os
import sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE', 'http://127.0.0.1:8819').rstrip('/')
OUT = os.environ.get('OUT', '.')
fails, errors, external = [], [], []


def check(ok, message):
    print(('ok   ' if ok else 'FAIL ') + message, flush=True)
    if not ok:
        fails.append(message)


def pointer_scrub(pg, index):
    slider = pg.locator('#rp-scrub')
    slider.scroll_into_view_if_needed()
    box = slider.bounding_box()
    # Native range thumb travel excludes half a thumb at each end.
    pg.mouse.click(box['x'] + 8 + (box['width'] - 16) * index / 12,
                   box['y'] + box['height'] / 2)


os.makedirs(OUT, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')
with sync_playwright() as p:
    br = p.chromium.launch()
    for width in (1440, 402):
        facts = []
        for mode in ('full', 'reduced', 'quiet'):
            reduced = mode == 'reduced'
            ctx = br.new_context(viewport={'width': width, 'height': 900},
                                 reduced_motion='reduce' if reduced else 'no-preference',
                                 service_workers='block')
            pg = ctx.new_page()
            if mode == 'quiet':
                ctx.add_init_script("localStorage.setItem('archeus.v2.motion', 'quiet')")
            pg.on('pageerror', lambda e: errors.append(str(e)))
            pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            ctx.route('**/*', lambda route: route.continue_() if urlparse(route.request.url).netloc == urlparse(BASE).netloc else (external.append(route.request.url), route.abort())[-1])
            tag = '%s/%s' % (width, mode)
            pg.goto(BASE + '/index.html#/mission/m-date', wait_until='load')
            pg.evaluate('document.fonts.ready')
            pg.locator('#m-replay').click()
            pg.locator('#rp-scrub').wait_for(state='visible')
            check(pg.locator('#rp-rows li').count() >= 12, tag + ' timeline count')
            facts.append(pg.locator('#rp-rows').text_content())
            check('Verification FAILED' in facts[-1] and 'Execution LOST' in facts[-1], tag + ' required evidence')
            check('NOT RECORDED' in pg.locator('#rp-gaps').text_content(), tag + ' evidence gaps')
            check('CONCEPT FIXTURE' in pg.locator('#rp-context').text_content(), tag + ' fixture label')
            slider = pg.locator('#rp-scrub')
            slider.focus()
            slider.press('Home')
            check(pg.locator('#rp-prev').is_disabled(), tag + ' first endpoint')
            slider.press('ArrowRight')
            check(slider.input_value() == '1', tag + ' keyboard scrub')
            pg.locator('#rp-prev').click()
            check(slider.input_value() == '0', tag + ' step back')
            pg.locator('#rp-next').click()
            check(slider.input_value() == '1', tag + ' step forward')
            slider.focus()
            slider.press('End')
            check(pg.locator('#rp-next').is_disabled(), tag + ' last endpoint')
            pointer_scrub(pg, 8)
            check(slider.input_value() == '8', tag + ' pointer selects failed verification')
            pg.locator('[data-recovery="retry"]').click()
            pg.locator('#rp-approve').click()
            check(pg.locator('#rp-proposal').is_visible(), tag + ' retry requires changes')
            pg.locator('#rp-draft').fill('Change boundary handling; verify again.')
            pg.locator('#rp-approve').click()
            check('SIMULATED' in pg.locator('#rp-receipt').text_content(), tag + ' explicit approval receipt')
            check(pg.locator('#rp-rows').text_content() == facts[-1], tag + ' approval leaves evidence unchanged')
            pg.locator('[data-recovery="resume"]').click()
            pg.locator('#rp-cancel').click()
            check(pg.locator('#rp-proposal').is_hidden(), tag + ' cancel')
            pg.locator('[data-recovery="ask"]').click()
            slider.focus()
            slider.press('ArrowRight')
            check(pg.locator('#rp-proposal').is_hidden(), tag + ' cursor invalidates proposal')
            check(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), tag + ' no horizontal overflow')
            check(pg.locator('#replay-stage').is_visible(), tag + ' constellation retained')
            sizes = pg.locator('#rp-controls button, #rp-scrub, #rp-controls a').evaluate_all('es => es.map(e => {const b=e.getBoundingClientRect(); return [b.width,b.height]})')
            check(all(w >= 47.5 and h >= 47.5 for w, h in sizes if w and h), tag + ' control boxes >=48 CSS px')
            pg.screenshot(path=os.path.join(OUT, 'replay-%s-%s.png' % (width, mode)))
            if width == 1440:
                pg.goto(BASE + '/index.html#/terminal', wait_until='load')
                term = pg.locator('#term')
                term.focus()
                term.press('j')
                term.press('Enter')
                term.press('p')
                term.press('End')
                check('13/13' in term.text_content(), tag + ' terminal shares timeline')
                term.press('1')
                check('SIMULATED proposal: resume' in term.text_content(), tag + ' terminal proposal')
                term.press('Escape')
                check('SIMULATED proposal:' not in term.text_content(), tag + ' terminal cancel')
                term.press('3')
                term.press('y')
                check('SIMULATED' in pg.locator('#rp-receipt').text_content(), tag + ' terminal explicit approval')
                colors = term.locator('svg text').evaluate_all('es => [...new Set(es.map(e => getComputedStyle(e).fill))]')
                check(len(colors) <= 1, tag + ' terminal monochrome')
            ctx.close()
        check(facts[0] == facts[1] == facts[2], str(width) + ' reduced motion and Quiet preserve facts')
    br.close()
check(not errors, 'zero browser errors: ' + repr(errors))
check(not external, 'zero external requests: ' + repr(external))
sys.exit(1 if fails else 0)
