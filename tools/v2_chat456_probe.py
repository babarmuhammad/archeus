"""Steps 4–6. Serve clients/v2-prototype; BASE defaults to localhost:8817.
Run through D:\\Archeus\\.collab\\testlock.py. No Core or account access.
Companion probes cover scene beats and effective hit testing.
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get('BASE', 'http://127.0.0.1:8817')
failures = []
general_facts = []


def check(ok, text):
    print(('ok   ' if ok else 'FAIL ') + text, flush=True)
    if not ok:
        failures.append(text)


def state(pg):
    return pg.evaluate("ArchReview.state('m-search')")


def send(pg, text):
    pg.locator('#chat-input').fill(text)
    pg.locator('#chat-input').press('Enter')
    pg.wait_for_timeout(800)


def confirm(pg):
    pg.locator('#confirm button[value="ok"]').click()
    pg.wait_for_timeout(100)


def approve(pg):
    pg.locator('[data-kind="approve"]').click()
    pg.locator('[data-kind="approve-confirm"]').click()
    confirm(pg)


def mission_list(pg, tag):
    panel = pg.locator('#s-now .list-d')
    check(not panel.locator('#now-list').is_visible(), tag + ': closed mission list hides link boxes')
    panel.locator('summary').click()
    hrefs = panel.locator('#now-list a').evaluate_all('(links) => links.map(a => a.getAttribute("href"))')
    for href in hrefs:
        link = panel.locator('a[href="' + href + '"]').first
        link.scroll_into_view_if_needed()
        hit = link.evaluate('''a => {
            const b = a.getBoundingClientRect();
            return [[2, 2], [b.width - 2, 2], [2, b.height - 2],
                    [b.width - 2, b.height - 2], [b.width / 2, b.height / 2]]
                .every(([x, y]) => a.contains(document.elementFromPoint(b.left + x, b.top + y)));
        }''')
        check(hit, tag + ': open list control unobstructed ' + href)
        link.click()
        pg.wait_for_url('**/index.html' + href)
        check(pg.evaluate('location.hash') == href, tag + ': mission list navigates ' + href)
        pg.goto(BASE + '/index.html#/now')
        if panel.get_attribute('open') is None:
            panel.locator('summary').click()
    panel.locator('summary').click()


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for width, height, motion in [(1440, 900, 'no-preference'), (402, 780, 'no-preference'),
                                   (320, 780, 'reduce')]:
        ctx = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion=motion)
        pg = ctx.new_page()
        errors, external = [], []
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.on('request', lambda r: external.append(r.url) if not r.url.startswith(BASE + '/') else None)
        pg.goto(BASE + '/index.html#/now')
        pg.wait_for_timeout(500)
        tag = str(width) + '/' + motion
        mission_list(pg, tag)
        nodes = pg.evaluate('ArchFixture.nodes()')
        before = pg.locator('#msgs > li').count()
        pg.locator('#chat-input').fill('/unknown-chat456')
        pg.locator('#chat-input').press('Enter')
        check(pg.locator('#msgs > li').count() == before, tag + ': unknown sends zero messages')
        pg.locator('#chat-input').press('Escape')
        pg.locator('#chat-input').fill('What is a rainbow?')
        check('General' in pg.text_content('#chat-destination'), tag + ': General shown before send')
        pg.locator('#chat-input').press('Enter')
        pg.wait_for_timeout(800)
        check(pg.evaluate('ArchFixture.nodes()') == nodes and state(pg)['memories'] == 0,
              tag + ': General adds zero nodes and memories')
        general_facts.append(pg.locator('#msgs .msg-gen').last.text_content())
        send(pg, '/idea isolated slash fixture')
        check(pg.evaluate('ArchFixture.nodes()') == nodes, tag + ': slash creation stays in its card')
        send(pg, '/remember I prefer tabs')
        card = pg.locator('#msgs > li').last
        card.locator('[data-memory-confirm]').click()
        check(not pg.locator('#confirm').is_visible(), tag + ': missing scope blocks memory')
        card.locator('select').select_option('*')
        card.locator('[data-memory-confirm]').click()
        check(state(pg)['memories'] == 0, tag + ': scope alone saves nothing')
        confirm(pg)
        check(state(pg)['memories'] == 1, tag + ': explicit confirmation saves one demo item')
        send(pg, 'Start a project called Chat456')
        send(pg, 'Add a mission "Review gate" to Chat456')
        check(not pg.evaluate("ArchReview.state('m-review-gate').version"),
              tag + ': mission request makes no plan or run')
        pg.locator('[data-card="start"]').last.click()
        check(pg.evaluate("ArchReview.state('m-review-gate').version") == 1 and
              not pg.evaluate("ArchReview.state('m-review-gate').approved"),
              tag + ': Start plans only and leaves approval pending')
        check('Plan approval required' in pg.locator('#msgs > li').last.text_content(),
              tag + ': Start produces its own plan approval card')
        pg.locator('#msgs > li').last.get_by_role('link', name='Review plan', exact=True).click()
        pg.wait_for_url('**/index.html#/plan/m-review-gate')
        check(pg.locator('[data-kind="approve"]').is_visible() and
              not pg.evaluate("ArchReview.state('m-review-gate').approved"),
              tag + ': own plan card opens live review without approval')
        pg.locator('#plan-review').get_by_role('link', name='Back to conversation', exact=True).click()
        before_state = state(pg)
        send(pg, '/approve Search provenance')
        check(state(pg) == before_state, tag + ': slash approve has zero effects')
        pg.goto(BASE + '/index.html#/plan/m-search')
        pg.wait_for_timeout(200)
        pg.locator('#plan-note').fill('Check provenance first')
        pg.locator('#plan-tasks summary').first.click()
        pg.locator('#c-t1').fill('Keep original source')
        check(len(state(pg)['feedback']) == 0, tag + ': comments remain drafts')
        pg.locator('[data-kind="approve"]').click()
        check(not pg.locator('#plan-confirm').is_visible(), tag + ': drafts block approval')
        pg.locator('[data-kind="request"]').click()
        confirm(pg)
        feedback = state(pg)['feedback']
        check(len(feedback) == 1 and feedback[0]['version'] == 1 and len(feedback[0]['tasks']) == 1,
              tag + ': Request changes batches versioned general and task feedback')
        pg.locator('[data-act="revise-plan"]').click()
        check(not state(pg).get('approved'), tag + ': changed plan invalidates approval')
        pg.locator('#review-fixture').select_option('error')
        approve(pg)
        check(not state(pg).get('approved'), tag + ': error applies nothing')
        check(pg.locator('[data-kind="approve"]').is_visible(), tag + ': error returns to review for retry')
        approve(pg)
        check(bool(state(pg).get('approved')), tag + ': retry records one approval')
        pg.locator('[data-act="revise-plan"]').click()
        pg.locator('#review-fixture').select_option('delay')
        approve(pg)
        check(not state(pg).get('approved'), tag + ': delay has no early effect')
        check(pg.locator('[data-act="revise-plan"]').is_visible(), tag + ': pending decision keeps revision reachable')
        pg.locator('[data-act="revise-plan"]').click()
        pg.wait_for_timeout(1900)
        check(not state(pg).get('approved'), tag + ': stale delayed decision rejected')
        pg.locator('#review-fixture').select_option('duplicate')
        approve(pg)
        check(state(pg).get('approved') == state(pg)['hash'], tag + ': duplicate resolves same identity')
        # Native dialog keyboard path: default Cancel; Escape never approves.
        pg.locator('[data-act="revise-plan"]').click()
        pg.locator('[data-kind="approve"]').focus()
        pg.keyboard.press('Enter')
        pg.locator('[data-kind="approve-confirm"]').focus()
        pg.keyboard.press('Enter')
        pg.keyboard.press('Escape')
        pg.locator('#confirm').wait_for(state='hidden')
        check(not state(pg).get('approved') and not pg.locator('#confirm').is_visible(),
              tag + ': keyboard Escape cancels')
        check(pg.locator('[data-kind="approve"]').is_visible(), tag + ': Cancel returns to live review')
        check(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), tag + ': review reflows')
        pg.goto(BASE + '/index.html#/terminal')
        pg.locator('#term').focus()
        pg.keyboard.press('r')
        pg.wait_for_timeout(150)
        check('/plan/' in pg.url, tag + ': terminal keyboard opens shared review')
        check(not external and not errors, tag + ': no external requests or browser errors')
        ctx.close()
    browser.close()

check(len(set(general_facts)) == 1, 'motion on/reduced show identical General facts')
sys.exit(1 if failures else 0)
