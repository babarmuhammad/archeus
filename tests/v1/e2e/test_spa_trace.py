"""P21 slice C in a real browser against a real Core (p21-design-gate D3, D14):
a mission's Trace tab reads the trace, and Replay plays its events on their
own clock, back to where it started."""

import re

from .conftest import wait
from .test_spa_p16 import _go, _mission, _open


def test_the_trace_tab_replays_the_missions_events(browser, core):
    mid = _mission(core, 'Trace me')
    core.http('POST', '/v1/missions/%s/pause' % mid, body={'idempotency_key': 'k-trace-p'})
    n = len(core.http('GET', '/v1/missions/%s/trace' % mid).json()['events'])
    assert n >= 1
    context, page, errors = _open(browser, core)
    _go(page, '#/o/mission/%s/trace' % mid)
    page.get_by_role('heading', name=re.compile(r'^Events · \d+$')).wait_for()
    items = page.locator('#panel-trace ol.timeline li')
    wait(page, lambda: items.count() >= n, what='every event before a replay')
    n = items.count()
    page.evaluate('''() => {
      const ol = document.querySelector('#panel-trace ol.timeline');
      window.__min = ol.children.length;
      new MutationObserver(() => { window.__min = Math.min(window.__min, ol.children.length); })
        .observe(ol, {childList: true});
    }''')
    page.get_by_role('button', name='Replay').click()
    wait(page, lambda: items.count() >= n and page.get_by_role('button', name='Replay').count() == 1,
         what='the replay plays to the end and stops')
    assert page.locator('#panel-trace ol.timeline li[aria-current="step"]').count() == 1
    assert page.evaluate('window.__min') == 1                     # it started over, one by one
    assert not errors, errors
    context.close()
