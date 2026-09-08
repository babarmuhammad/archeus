"""The GUI uses the whole screen, and it does it without inventing breakpoints.

Every page except the dashboard capped its cards at `max-width:940px`, so on a
2560px display the app used about 37% of the width. The dashboard was the proof
of cause rather than an exception: `.dash>.card{max-width:none}` is the only
reason that one page filled the screen.

The fix is a fluid grid — `#content` is the grid, cards are the cells, and the
reading measure is protected by the track MINIMUM instead of by a cap on the
card, so the browser decides how many columns fit. What these tests pin is the
three things that make that hold:

  · the cap is gone, and nothing re-adds a fixed measure to a card
  · the track minimum is `min(100%, …)`, or a 560px track overflows a 400px
    viewport sideways
  · furniture spans the row and only a card tiles, so a page's header, the
    sessions list and a bare spinner need no marking

Fit itself is measured, not asserted: tools/shot_gui.py walks every page at
1280 / 1920 / 2560 under every skin. A string match cannot tell you whether a
table fits its column.
"""
import re

from claude_sessions.gui_html import PAGE

_CSS = re.sub(r'/\*.*?\*/', '',
              PAGE[PAGE.index('<style>'):PAGE.index('</style>')], flags=re.S)
_JS = re.sub(r'/\*.*?\*/', '', PAGE[PAGE.index('</style>'):], flags=re.S)


def test_no_card_carries_a_fixed_reading_measure_any_more():
    """The 940px cap, and the two rules that had quietly copied it.

    `.slist` and `.rowtune` had the same literal, which is why the sessions page
    stayed narrow even though it renders no card at all — a cap copied into
    three rules is three places the next person has to find."""
    assert '940px' not in _CSS, 'the 940px measure is back'
    for sel in ('.card{', '.slist{', '.rowtune{'):
        block = _CSS[_CSS.index(sel):]
        block = block[:block.index('}')]
        assert 'max-width' not in block, f'{sel} caps its own width again'


def test_the_content_column_is_an_auto_fill_grid():
    """auto-fill is the whole design: the column count is a consequence of the
    window, so there is no breakpoint to keep in sync with a card's contents."""
    block = _CSS[_CSS.index('.content{'):]
    block = block[:block.index('}')]
    assert 'display:grid' in block
    assert 'repeat(auto-fill,' in block, 'the column count is hardcoded again'
    assert 'var(--card-min' in block, 'the reading measure is not a token'
    # align-items:start, or a short card is stretched as tall as the tallest in
    # its row and the page reads as a wall of equal boxes
    assert 'align-items:start' in block


def test_the_track_minimum_cannot_overflow_a_narrow_window():
    """`minmax(560px,1fr)` makes the track 560px wide even in a 400px viewport,
    which pushes the grid sideways out of the scroll area. `min(100%,…)` is what
    collapses the minimum to the available width instead, and it is the reason
    this needs no narrow-window media query of its own."""
    block = _CSS[_CSS.index('.content{'):]
    block = block[:block.index('}')]
    assert 'minmax(min(100%,var(--card-min' in block.replace(' ', ''), \
        'the track minimum is not clamped to the available width'


def test_the_measure_is_a_real_token_a_look_can_lower():
    root = _CSS[_CSS.index(':root{'):]
    root = root[:root.index('}')]
    assert re.search(r'--card-min:\s*\d+px', root), \
        '--card-min is not declared on :root'


def test_only_cards_tile_and_furniture_spans_the_row():
    """A page header, `.dash`, the sessions `.slist` and the bare spinner
    `paintNow(LOADING)` writes are all direct children of #content and none of
    them is a card. Defaulting them to a full row is what keeps the marking
    burden at ~15 cards instead of at every wrapper div any renderer emits —
    and it is what stops the dashboard's own 4-column grid being crammed into
    one 560px cell."""
    assert '.content>*{grid-column:1/-1}' in _CSS.replace(' ', '')
    cell = _CSS[_CSS.index('.content>.card{'):]
    cell = cell[:cell.index('}')]
    assert 'grid-column:auto' in cell
    assert 'margin-bottom:0' in cell, 'card margin doubles up with the grid gap'
    # a grid item's default min-width:auto lets a wide table push its own cell
    # past the track, which widens the column for every card on the page
    assert 'min-width:0' in cell
    assert '.content>.card.wide{grid-column:1/-1}' in _CSS.replace(' ', '')


def test_the_dashboard_keeps_its_own_grid():
    """`.dash` is a child of #content, so it takes the full row as furniture —
    but its cards are children of `.dash`, not of #content, and still need the
    rule that made this page the only one filling the screen."""
    block = _CSS[_CSS.index('.dash>.card{'):]
    block = block[:block.index('}')]
    assert 'max-width:none' in block and 'min-width:0' in block


def test_wide_is_only_ever_put_on_a_card():
    """`.wide` only means anything on `.content>.card`. On anything else it is a
    no-op that reads like an instruction, and on a nested card (a review
    finding, a drawer card) it is meaningless — those are not grid items."""
    for m in re.finditer(r'class="([^"]*\bwide\b[^"]*)"', _JS):
        cls = m.group(1).split()
        assert 'card' in cls or 'modal' in cls, f'stray .wide on {cls}'


def test_the_wide_cards_are_the_ones_that_cannot_share_a_row():
    """Two reasons a card takes the whole row, and both are about content:

    it is ALONE on its page (a column of one card on a 2560px screen is the
    original bug with a smaller number), or it holds something that does not
    survive a 560px column — `.cctable`, whose own grid has a 664px minimum
    with three accounts; `.cols3`, three tables side by side; a six- or
    eight-column table; the theme gallery.

    Pinned by name because the failure is silent: an unmarked wide card does
    not throw, it just squeezes, and only a screenshot shows it."""
    for anchor in (
            'class="card wide"><h3>Code review',           # sole card
            'class="card wide"><h3>Per-session usage',      # 6-col table
            'class="card wide"><h3>${ic(\'search\')} Search every session',
            'class="card wide"><h3>MCP servers',
            'class="card wide"><h3>${ic(\'history\')} Logs',
            'class="card wide"><h3>Repos',                  # both repo paths
            'class="card wide"><h3>${ic(\'fork\')} Repos',
            'class="card wide"><h3>${ic(\'settings\')} How Claude Code behaves',
            'class="card wide"><h3>${ic(\'ai\')} What is actually being used',
            'class="card wide"><h3>${ic(\'check\')} Auto mode',
            'class="card wide"><h3>Per-project',
            'class="card wide"><h3>Claude accounts',
            'class="card wide"><h3>${ic(\'refresh\')} Sync accounts',
            'class="card wide"><h3>${ic(\'palette\')} Appearance',
    ):
        assert anchor in _JS, f'no longer a full-row card: {anchor}'
    # the sessions setup banner sits above a full-width list; a 560px banner
    # over a 2242px list is the one place .wide is about alignment, not content
    assert 'class="card wide"\n      style="border-left:3px solid var(--warn)"' in _JS


def test_the_fit_gate_measures_more_than_one_width():
    """The narrowest column happens at the WIDEST viewport — auto-fill has just
    fitted one more in — so a single-width audit is blind to exactly the failure
    this change can cause."""
    src = open('tools/shot_gui.py', encoding='utf-8').read()
    assert 'WIDTHS = (1280, 1920, 2560)' in src
    assert 'def audit_widths(' in src
    assert 'GRID_JS' in src
    # …and the per-skin pass has to walk them too: a 3px border and a hard
    # shadow break fit at a width the default skin survives
    skin = src[src.index("print('\\n— per-skin audit —')"):]
    assert 'for w in WIDTHS:' in skin, 'the per-skin audit is still single-width'


def test_the_fit_probe_does_not_skip_everything_it_measures():
    """The bug this file's gate would otherwise have inherited.

    Both roots the overflow probes are pointed at scroll — `.modal` is
    max-height:88vh and `#content` is the app's scroll area — and the ancestor
    walk that exists to skip descendants of a scroller ran up to and INCLUDING
    the root. So the first ancestor examined always said "scrolling", every
    element was skipped, and the page audit printed `clean` for measuring
    nothing. Same family as the smoke tool's stranded `return`."""
    src = open('tools/shot_gui.py', encoding='utf-8').read()
    assert 'p&&p!==m.parentElement' not in src, \
        'the ancestor walk includes the scrolling root again'
    assert 'p&&p!==m;p=p.parentElement' in src
    assert 'if(p===c)continue;' in src, 'GRID_JS consults its own root'
