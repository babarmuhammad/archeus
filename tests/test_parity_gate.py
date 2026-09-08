"""Parity as a gate, not a review.

`test_gui_parity.py` tests what the endpoints DO. Nothing tested that a
counterpart exists at all, which is why drift happened in both directions —
`health.py` was 229 lines and a README headline with no GUI trace, while
`gui-audit.md` listed seventeen routes that had never existed.
"""

import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import gui, gui_api, session_menu

TESTS = os.path.dirname(os.path.abspath(__file__))


def _routes():
    return (set(gui_api.GET_ROUTES) | set(gui_api.POST_ROUTES)
            | set(gui._LOCAL_GET) | set(gui._LOCAL_POST))


def test_every_tui_action_has_a_gui_counterpart():
    routes = _routes()
    missing = [(k, label, route)
               for k, label, _scope, route, _blurb, _bucket in
               session_menu.ACTIONS + session_menu.ARCHIVED_ACTIONS
               if route and route not in routes]
    assert not missing, 'TUI actions with no GUI route: %s' % (missing,)


def test_an_action_without_a_counterpart_must_say_why():
    """A blank route is allowed — some things only make sense in a terminal —
    but it has to be a decision, so the table carries a comment beside it."""
    src = io.open(session_menu.__file__, encoding='utf-8').read()
    table = src[src.index('ACTIONS = ['):src.index('#: actions reachable only')]
    for k, label, _scope, route, _blurb, _bucket in session_menu.ACTIONS:
        if route:
            continue
        line = next(ln for ln in table.splitlines() if "'%s'" % label in ln)
        assert '#' in line, 'terminal-only action %r gives no reason' % (label,)


def test_the_action_table_still_drives_the_hints():
    """Hoisting it out of the render loop is what makes the gate possible; if
    the hints stop coming from it, the table is decoration."""
    src = io.open(session_menu.__file__, encoding='utf-8').read()
    assert "_hints('session')" in src and "_hints('project')" in src
    labels = {label for _k, label, _s, _r, _b, _bk in session_menu.ACTIONS}
    assert {'view', 'fork', 'review', 'ctx audit'} <= labels


def test_every_key_the_sessions_screen_handles_is_in_the_table():
    """The gate for the drift the table exists to stop.

    Three lists described this screen — ACTIONS (21 keys), the `/` palette (26)
    and the help screen (22) — against 29 real handlers. `R`, code review, was
    in neither of the two DISCOVERABLE ones, so a shipped feature had no entry
    point anywhere in the product. Nothing could catch that by reading, because
    the evidence was a `ev[1] == 'R'` branch six hundred lines from the table.

    So the handlers are enumerated from the source: a key you can press and
    that the table does not know about is a key nobody can find.
    """
    src = io.open(session_menu.__file__, encoding='utf-8').read()
    tree = ast.parse(src)
    handled = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.comparators) != 1:
            continue
        left, right = node.left, node.comparators[0]
        # ev[1] == '<char>'
        if (isinstance(left, ast.Subscript) and isinstance(right, ast.Constant)
                and isinstance(right.value, str) and len(right.value) == 1):
            handled.add(right.value)
    assert len(handled) > 20, 'the handler walk found nothing — the dispatch shape changed'
    known = {k for k, _l, _s, _r, _b, _bk in
             session_menu.ACTIONS + session_menu.ARCHIVED_ACTIONS}
    assert not (handled - known), (
        'keys the sessions screen handles but the table does not list: %s'
        % sorted(handled - known))


def test_every_action_is_discoverable_without_reading_the_source():
    """Both discovery surfaces come from ACTIONS, so neither can fall behind.

    A key with no blurb is deliberately undiscoverable and must say why on its
    line — today that is `/` alone, which opens the palette it would appear in.
    """
    src = io.open(session_menu.__file__, encoding='utf-8').read()
    table = src[src.index('ACTIONS = ['):src.index('#: actions reachable only')]
    silent = [(k, label) for k, label, _s, _r, blurb, _bk in session_menu.ACTIONS if not blurb]
    for k, label in silent:
        line = next(ln for ln in table.splitlines() if "'%s'" % label in ln)
        assert '#' in line, 'undiscoverable action %r gives no reason' % (label,)
    # the palette and the help screen are the same inventory, generated
    palette = {k for _blurb, k in session_menu.palette_rows()}
    assert palette == {k for k, _l, _s, _r, b, _bk in session_menu.ACTIONS if b}
    assert 'R' in palette and 'X' in palette and 'K' in palette
    from claude_sessions import ui
    helptext = '\n'.join(ui._session_key_lines())
    for key in ('R', 'X', 'K'):
        assert ('\n    %s  ' % key) in helptext or ('  %s  ' % key) in helptext, key


def test_the_palette_does_not_offer_an_action_that_is_guarded_off():
    """Generating the palette from the table is what created this hazard: the
    hand-written list simply omitted `!`, whose handler only runs while the
    project has no CLAUDE.md and no memory graph. Picking a row that falls
    through to the type-to-filter handler is worse than not seeing the row."""
    assert '!' in {k for _b, k in session_menu.palette_rows()}
    assert '!' not in {k for _b, k in session_menu.palette_rows(skip='!')}
    # and the call site passes it — an unused parameter is not a guard
    src = io.open(session_menu.__file__, encoding='utf-8').read()
    assert "palette_rows(skip=" in src


def _at_the_narrowest_supported_terminal(monkeypatch):
    """Pin the terminal to the width the help screen is written for.

    The budget follows the terminal, so "does this blurb fit" is meaningless
    without one — on a wide CI console every blurb passes. The number comes
    from `ui.HELP_MIN_COLS` rather than from here: a fixture that owns the
    contract is a contract that can be relaxed by editing the test.
    """
    import shutil
    from claude_sessions import render, ui
    # `**kw` is load-bearing, not defensive. This patches the GLOBAL shutil, so
    # pytest's own terminal writer calls it too — as
    # `shutil.get_terminal_size(fallback=(80, 24))`, a KEYWORD argument. A
    # `lambda *a` rejected it, and the TypeError surfaced as a pytest
    # INTERNALERROR during reporting: "679 passed" followed by exit 1, only on
    # CI, because a local TTY run takes a different path through the writer.
    monkeypatch.setattr(shutil, 'get_terminal_size',
                        lambda *a, **kw: os.terminal_size((ui.HELP_MIN_COLS, 35)))
    render.invalidate()


def test_a_blurb_fits_the_help_grid(monkeypatch):
    """The blurb is the palette row AND the help cell, and only the help screen
    has a hard budget — so it is written to that one. Truncating there loses the
    only description a key has; the palette merely has room to spare.

    The budget is ASKED of the renderer. The first cut restated it as 33 while
    the renderer computed 32, so this gate passed with four cells truncated —
    the duplicated-constant bug, inside the test written to prevent a different
    duplication.
    """
    from claude_sessions import ui
    _at_the_narrowest_supported_terminal(monkeypatch)
    budget = ui.help_blurb_budget()
    too_long = [(k, len(b), b) for k, _l, _s, _r, b, _bk in session_menu.ACTIONS
                if len(b) > budget]
    assert not too_long, (
        'these truncate in the help screen (budget %d chars): %s'
        % (budget, too_long))


def test_the_help_grid_shows_every_blurb_whole(monkeypatch):
    """The end of that argument, asserted on the rendered lines rather than on
    the inputs: no cell may end in the truncation marker."""
    from claude_sessions import ui
    _at_the_narrowest_supported_terminal(monkeypatch)
    from claude_sessions import render
    lines = ui._session_key_lines()
    assert lines, 'the help grid rendered nothing'
    joined = '\n'.join(lines)
    assert '…' not in joined, 'a help cell is truncated:\n' + joined
    # The other half of the same invariant, and the one a lying budget would
    # otherwise slip past: a cell wide enough never to truncate is a cell that
    # runs off the frame. These lines carry no ANSI, so len() is the width.
    over = [ln for ln in lines if len(ln) > render.content_width()]
    assert not over, 'a help line overruns the frame:\n' + '\n'.join(over)


def test_shift_keys_render_as_shift_in_the_hints():
    hints = dict(session_menu._hints('session'))
    assert '⇧F' in hints and hints['⇧F'] == 'files'
    assert 'v' in hints, 'a lowercase key must not grow a shift marker'


# ── endpoint test floor ──────────────────────────────────────

def _tested_routes():
    """Every '/api/...' string literal anywhere in the test suite."""
    found = set()
    for name in os.listdir(TESTS):
        if not name.endswith('.py'):
            continue
        src = io.open(os.path.join(TESTS, name), encoding='utf-8').read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                if v.startswith('/api/'):
                    found.add(v.split('?')[0])
    return found


def test_every_endpoint_is_exercised_by_something():
    """Forty-nine routes had no HTTP-level test of any kind — the exact class of
    bug already recorded here: gate['diff'] shipped broken because the only
    gate test covered one of the two shapes its producers passed.

    Coverage comes from two places. Most routes have a test that names them and
    asserts what they return; the rest are covered by the parametrized floor in
    `test_endpoint_floor.py`, which is shallow (it only proves the route does
    not fault) but TOTAL — and total is what stops a new route shipping with
    nothing at all behind it.
    """
    named = _tested_routes()
    covered = named | _floor_routes()
    missing = sorted(_routes() - covered)
    assert not missing, 'endpoints with no test at all: %s' % (missing,)


def _floor_routes():
    """What the parametrized floor covers — read off the same live tables it
    parametrizes over, so the two cannot drift apart."""
    src = io.open(os.path.join(TESTS, 'test_endpoint_floor.py'),
                  encoding='utf-8').read()
    if "_all('GET')" not in src or "_all('POST')" not in src:
        return set()                       # it stopped covering; report nothing
    return _routes()


def test_the_floor_is_driven_by_the_live_route_tables():
    """If the floor is ever given a hardcoded list it stops being a floor — the
    same rot that had smoke_gui checking eleven of twelve pages."""
    src = io.open(os.path.join(TESTS, 'test_endpoint_floor.py'),
                  encoding='utf-8').read()
    assert "@pytest.mark.parametrize('route', _all('GET'))" in src
    assert "@pytest.mark.parametrize('route', _all('POST'))" in src
    assert "getattr(ga, table_name + '_ROUTES')" in src, \
        'the floor stopped reading the live tables'


def test_most_endpoints_have_a_test_that_names_them():
    """The floor proves a route answers; it cannot prove a route is CORRECT.
    This keeps the shallow-but-total check from becoming the only coverage —
    the ratio may not slide below where it stands now."""
    named = _tested_routes() & _routes()
    assert len(named) >= 40, (
        'only %d of %d routes have a test naming them' % (len(named), len(_routes())))


def test_the_api_reference_is_generated_and_current():
    """docs/gui-audit.md was a hand-written route catalogue that had drifted to
    listing seventeen routes which do not exist. A hand-maintained copy of
    something the code already states is a copy that will be wrong."""
    sys.path.insert(0, os.path.join(os.path.dirname(TESTS), 'tools'))
    import gen_api_docs
    current = io.open(gen_api_docs.OUT, encoding='utf-8').read().replace('\r\n', '\n')
    assert current == gen_api_docs.render(), \
        'docs/api.md is stale — run tools/gen_api_docs.py'


def test_the_route_tables_have_no_duplicates_between_them():
    """A path in both a local table and gui_api's is ambiguous — the local one
    silently wins."""
    both = (set(gui._LOCAL_GET) & set(gui_api.GET_ROUTES)) | \
           (set(gui._LOCAL_POST) & set(gui_api.POST_ROUTES))
    assert not both, both
