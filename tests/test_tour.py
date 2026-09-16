"""The guided tour: one narrative, three surfaces.

A tour is the one feature whose failure mode is silent by construction — a step
that points at a screen which no longer exists still renders perfectly, and the
only person who finds out is a new user on their first five minutes. So these
gates are almost all about whether the tour still describes THIS application:
every page and tab it names has to be one the app has, every terminal key one
the terminal answers, every manual page one that is published.
"""

import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import main as main_mod
from claude_sessions import tour
from claude_sessions.gui_html import PAGE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')

ALL_STEPS = [(name, s) for name in tour.names() for s in tour.steps(name)]


def _table(start, end):
    """The slice of the served page between two markers.

    `PAGE.index(end)` searches from ZERO, so the naive form returned the text
    between `const NAV=[` and the first `];` ANYWHERE in the page — which is
    thousands of lines earlier, making the slice empty and every id check pass
    on nothing. Search for the terminator after the start.
    """
    a = PAGE.index(start)
    return PAGE[a:PAGE.index(end, a)]


def _nav_ids():
    return set(re.findall(r"\n  \['([a-z]+)',", _table('const NAV=[', '];')))


def _tab_ids():
    return set(re.findall(r"\n  \['([a-z]+)',", _table('const TABS=[', '];')))


# ── the tour describes THIS application ──────────────────────

def test_every_step_names_a_page_the_app_has():
    """Read out of the served page rather than restated: `NAV` is authored in
    app.js, and a copy of it here would be the second thing to keep in step —
    which is the failure this whole file exists to catch."""
    pages = _nav_ids() | {'home'}
    bad = [(w, s['id'], s['page']) for w, s in ALL_STEPS if s['page'] and s['page'] not in pages]
    assert not bad, 'steps pointing at a page that does not exist: %s' % bad


def test_every_step_names_a_tab_the_project_has():
    tabs = _tab_ids()
    bad = [(w, s['id'], s['tab']) for w, s in ALL_STEPS if s['tab'] and s['tab'] not in tabs]
    assert not bad, 'steps pointing at a project tab that does not exist: %s' % bad


def test_every_step_names_a_manual_page_that_is_published():
    have = {n[:-3] for n in os.listdir(DOCS) if n.endswith('.md')}
    bad = [(w, s['id'], s['docs']) for w, s in ALL_STEPS if s['docs'] and s['docs'] not in have]
    assert not bad, 'steps linking a manual page that is not there: %s' % bad


def test_the_short_tour_ends_by_launching_something():
    """A getting-started tour that finishes on a settings screen has not started
    anything. The last step is the one nobody skips."""
    last = tour.SHORT[-1]
    assert 'launch' in (last['title'] + last['body']).lower()


def test_the_long_tour_covers_every_screen_the_app_has():
    """'Every function' is a claim, and this is what makes it one. A page in no
    step is a page the tour teaches nobody about — which is how a feature ends
    up being 'discovered' two years after it shipped.

    Two pages are deliberately exempt and both are doors rather than
    destinations: Search is a box on the dashboard, and Help is where the tour
    is started FROM.
    """
    named = {s['page'] for _w, s in ALL_STEPS if s['page']}
    missing = _nav_ids() - named - {'searchp'}
    assert not missing, 'screens no tour step mentions: %s' % sorted(missing)


def test_the_long_tour_covers_every_project_tab():
    named = {s['tab'] for _w, s in ALL_STEPS if s['tab']}
    missing = _tab_ids() - named
    assert not missing, 'project tabs no tour step mentions: %s' % sorted(missing)


def test_every_step_says_what_the_thing_is_FOR():
    """The whole reason this file is not generated from `NAV`'s blurbs. A blurb
    says what a screen shows; a step has to say when you would reach for it, and
    two sentences is the floor for that."""
    thin = [(w, s['id']) for w, s in ALL_STEPS
            if len(s['body'].split()) < 25 or s['body'].count('.') < 2]
    assert not thin, 'steps that only restate the screen name: %s' % thin


def test_a_step_id_is_unique_within_its_tour():
    """The GUI resumes by id and the website deep-links by index; a duplicate id
    is a step that can never be linked to."""
    for name in tour.names():
        ids = [s['id'] for s in tour.steps(name)]
        assert len(ids) == len(set(ids)), name


def test_an_unknown_tour_is_the_short_one_not_an_error():
    assert tour.steps('nonsense') == tour.SHORT
    assert tour.steps('') == tour.SHORT
    assert tour.steps(None) == tour.SHORT


# ── all three surfaces run the same one ──────────────────────

def test_the_website_copy_is_current():
    """Generated, and the gate is the generator's own --check: comparing a
    hand-read subset would pass on a file that is stale in every other field."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import gen_tour
    assert gen_tour.main(['--check']) == 0, \
        'www/lib/tour.ts is stale — run: py tools/gen_tour.py'


def test_the_endpoint_serves_the_steps_with_their_manual_links():
    from claude_sessions import gui_api
    out = gui_api.api_tour({'which': 'long'}, None)
    assert out['which'] == 'long'
    assert len(out['steps']) == len(tour.LONG)
    with_docs = [s for s in out['steps'] if s['docs']]
    assert with_docs and all(s['docsUrl' if 'docsUrl' in s else 'docs_url']
                             for s in with_docs)
    # an unknown name is the short tour, never an error or an empty page
    assert gui_api.api_tour({'which': 'nope'}, None)['which'] == 'short'


def test_the_gui_can_run_it_and_targets_by_attribute():
    """A tour that found its target by matching the printed label would break on
    the first rename, silently, and point at nothing."""
    assert 'window.TOUR' in PAGE and "TOUR.start('short')" in PAGE
    assert "api('/api/tour" in PAGE
    assert 'data-nav="${esc(label)}"' in PAGE
    assert 'data-tab="${esc(id)}"' in PAGE
    assert "[data-nav=\"' + SEC_OF[s.page] + '\"]" in PAGE


def test_the_tour_overlay_animates_only_transform_and_opacity():
    """The compositor contract in CLAUDE.md is not a style rule — it is what
    stops the Qt surface tearing, and a feature whose whole job is to draw the
    eye is the last place to break it."""
    css = io.open(os.path.join(ROOT, 'claude_sessions', 'web', 'app.css'),
                  encoding='utf-8').read()
    block = css[css.index('@keyframes tourIn'):]
    block = block[:block.index('}}') + 2]
    props = set(re.findall(r'([a-z-]+)\s*:', block))
    assert props <= {'opacity', 'transform'}, props
    assert 'backdrop-filter' not in css[css.index('/* ── guided tour ──'):]


def test_the_terminal_offers_it_and_prints_the_website():
    keys = {k for _l, k, _r in main_mod.MAIN_ACTIONS}
    assert '__tour__' in keys
    assert '__tour__' in main_mod.MAIN_TOP
    src = io.open(os.path.join(ROOT, 'claude_sessions', 'ui.py'),
                  encoding='utf-8').read()
    body = src[src.index('def tour_screen('):src.index('def help_screen(')]
    # the one thing the terminal cannot do is show the screen, so it points at
    # the surface that can
    assert 'SITE_TOUR' in body
    assert 'wait_event()[0]' in body, \
        "a resize is ('resize',) — unpacking two names kills the screen"


def test_the_terminal_screen_opens_where_it_is_asked_to():
    """`start` is what lets the recorder capture one clean frame per step, and
    what lets the screen resume. Driven through the real fake keyboard."""
    sys.path.insert(0, os.path.join(ROOT, 'tests'))
    import harness as H
    from _pytest.monkeypatch import MonkeyPatch
    import tempfile
    from pathlib import Path
    from claude_sessions import ui
    mp = MonkeyPatch()
    tmp = Path(tempfile.mkdtemp(prefix='archeus-tourtest-'))
    try:
        H.Sandbox(mp, tmp)
        cap = H.run_flow(mp, list(H.ESC), lambda: ui.tour_screen('short', 3))[1]
        assert 'step 4 of %d' % len(tour.SHORT) in cap.text
        assert tour.SHORT[3]['title'] in cap.text
    finally:
        mp.undo()


def test_the_website_page_is_in_the_nav_and_built_from_the_generated_copy():
    site = io.open(os.path.join(ROOT, 'www', 'lib', 'site.ts'), encoding='utf-8').read()
    assert "href: '/getting-started'" in site
    page = io.open(os.path.join(ROOT, 'www', 'app', 'getting-started', 'page.tsx'),
                   encoding='utf-8').read()
    assert "from '@/lib/tour'" in page
    player = io.open(os.path.join(ROOT, 'www', 'components', 'TourPlayer.tsx'),
                     encoding='utf-8').read()
    assert "from '@/lib/tour'" in player
    # the HowTo is DERIVED from the short tour, not written beside it
    assert 'TOUR_SHORT.map' in page


@pytest.mark.parametrize('rel', ['tour-gui-short.webp', 'tour-tui-short.webp'])
def test_the_recorded_guide_is_published_to_both_hosts_and_moves(rel):
    """A recording announced as an animation that is one frame is the failure
    the recorder itself hit: the screen never advanced and nothing said so."""
    from PIL import Image, ImageSequence
    for host in (os.path.join(ROOT, 'docs', 'img'),
                 os.path.join(ROOT, 'www', 'public', 'img')):
        p = os.path.join(host, rel)
        assert os.path.isfile(p), p
    im = Image.open(os.path.join(ROOT, 'docs', 'img', rel))
    frames = sum(1 for _ in ImageSequence.Iterator(im))
    assert frames >= len(tour.SHORT), '%s has %d frames for %d steps' % (
        rel, frames, len(tour.SHORT))


def test_the_generated_copy_is_json_the_website_can_type_check():
    ts = io.open(os.path.join(ROOT, 'www', 'lib', 'tour.ts'), encoding='utf-8').read()
    for name in tour.names():
        marker = 'export const TOUR_%s: TourStep[] = ' % name.upper()
        assert marker in ts
        body = ts[ts.index(marker) + len(marker):]
        body = body[:body.index('\n];') + 2]
        rows = json.loads(body)
        assert len(rows) == len(tour.steps(name))
        assert {k for k in rows[0]} == {'id', 'title', 'body', 'page', 'tab',
                                        'key', 'docs', 'docsUrl'}
