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
import io
import re

from claude_sessions.gui_html import PAGE

_CSS = re.sub(r'/\*.*?\*/', '',
              PAGE[PAGE.index('<style>'):PAGE.index('</style>')], flags=re.S)
_JS = re.sub(r'/\*.*?\*/', '', PAGE[PAGE.index('</style>'):], flags=re.S)


def _fn_body(name):
    """The whole body of a top-level function in app.js.

    The first cut of this took everything up to the first `paint`, which in
    `drawSessions` is the `paintNow(LOADING)` on its second line — so the call
    that paints the page, 28 lines below, was outside what the check read, and
    mutating it to `paintPile` failed nothing at all."""
    # the DECLARATION, not the first mention: a bare name finds the call site
    # inside `render()` first, and the slice from there is somebody else's body
    i = _JS.index('function ' + name + '(')
    rest = _JS[i + len(name):]
    ends = [rest.index(m) for m in (NL + 'function ', NL + 'async function ')
            if m in rest]
    return rest[:min(ends)] if ends else rest


#: A newline, to anchor a BASE rule: `.card{` on its own finds
#: `.content>.card{` first, which is a different rule about a different thing.
NL = chr(10)

#: Every page's declared archetype, read out of the served page rather than
#: restated here. This is what turns the two lists that used to be typed into
#: this file — four "designed" function names, fourteen `.wide` heading strings
#: — into facts about all 28 pages instead of assertions about the handful
#: somebody remembered. A page missing from either table simply has no
#: archetype, which `test_every_page_declares_a_shape` is what catches.
def _arch_table():
    out = {}
    for tbl, idx in (('NAV', 5), ('TABS', 3)):
        block = _JS[_JS.index('const %s=[' % tbl) + len('const %s=[' % tbl):]
        block = block[:block.index('];')]
        # Rows are found by their BRACKETS, not by matching a whole line: the
        # last row of TABS ends `]];` and a line-anchored pattern could not
        # match it, so `tools` was missing and everything still passed. Neither
        # table nests a bracket inside a row, so this is exact.
        for row in re.finditer(r'\[([^\[\]]+)\]', block):
            # split on top-level commas only — a blurb contains commas
            parts = _top_level_commas(row.group(1))
            if len(parts) > idx and parts[0].strip()[:1] in '\'"':
                out[parts[0].strip().strip("'\"")] = \
                    parts[idx].strip().strip("'\"")
    return out


def _top_level_commas(s):
    """Split a tuple body on commas that are not inside a quote.

    The escape branch is load-bearing: two blurbs carry an apostrophe as `\\'`
    ("This project's token spend", "Claude Code's own record"), and without it
    the scan thought the string had closed and lost those two rows — 26 of 28,
    silently, which is the shape of bug this whole file exists to distrust."""
    parts, buf, q, esc = [], '', None, False
    for ch in s:
        if esc:
            buf += ch
            esc = False
        elif ch == '\\':
            buf += ch
            esc = True
        elif q:
            buf += ch
            if ch == q:
                q = None
        elif ch in '\'"':
            q = ch
            buf += ch
        elif ch == ',':
            parts.append(buf)
            buf = ''
        else:
            buf += ch
    parts.append(buf)
    return parts


_ARCH = _arch_table()

#: The shapes `shell()` knows how to write. `grid` is the un-designed default a
#: page carries until this rehaul reaches it.
SHAPES = ('grid', 'dash', 'split', 'feed', 'form', 'pile')


def _arch(page):
    return _ARCH.get(page)


def _read_tool(name):
    """The audit tools are part of the contract this file pins: a probe that
    stops running still prints a pass, so the checks that keep it honest are
    asserted here rather than left to whoever remembers to read the output."""
    import os
    return io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'tools', name), encoding='utf-8').read()


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


def test_the_content_column_is_an_auto_fit_grid():
    """auto-fit is the whole design: the column count is a consequence of the
    space, so there is no breakpoint to keep in sync with a card's contents.

    auto-FIT and not auto-fill, which is a one-word difference with a visible
    one: auto-fill keeps an empty track alive, so a page holding two short cards
    left a third of the row dark on a 2560px display. auto-fit collapses the
    empty track and the cards that exist stretch into it. With enough cards to
    occupy every track the two are identical, which is why this is safe."""
    block = _CSS[_CSS.index('.content{'):]
    block = block[:block.index('}')]
    assert 'display:grid' in block
    assert 'repeat(auto-fit,' in block, \
        'auto-fill is back, or the column count is hardcoded again'
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


# ── the Library's list + detail split ────────────────────────────────

def test_the_library_split_is_a_grid_child_like_the_dashboard():
    """`.tpane` is to #content exactly what `.dash` is: not a card, so it takes
    the whole row, with its own children needing the cell rules the grid would
    otherwise have handed them. Two equal auto-fill columns is the wrong shape
    for a list beside what you picked out of it."""
    block = _CSS[_CSS.index('.tpane{'):]
    block = block[:block.index('}')]
    assert 'display:grid' in block
    assert 'minmax(320px,440px)' in block and '1fr' in block,         'the split is no longer a narrow list beside a wide detail'
    assert 'align-items:start' in block
    cell = _CSS[_CSS.index('.tpane>.card{'):]
    cell = cell[:cell.index('}')]
    for want in ('max-width:none', 'min-width:0', 'margin-bottom:0'):
        assert want in cell, f'.tpane>.card is missing {want}'


def test_the_split_collapses_before_its_columns_get_unreadable():
    """A 320px list next to a detail pane needs about 860px of CONTENT to be two
    columns at all — below that they stack, and the detail stops being sticky
    because there is nothing beside it to stay level with.

    Of content, not of window: it asked for 1099px of viewport, which is a
    different number every time the sidebar is dragged, and 240px different at
    the two ends of its own range."""
    flat = _CSS.replace(' ', '').replace('\n', '')
    assert '@containerpage(max-width:860px){.tpane{grid-template-columns:1fr}' \
        in flat
    assert '.tpane.tdet{position:static}' in flat


def test_the_skills_list_and_its_detail_are_one_pane_each():
    """The page this replaced put an explainer, 62 unbounded rows and an "add"
    form side by side, so the list got one narrow column of three."""
    # the split is DECLARED now, not hand-written into the template: the page
    # says `split` in NAV and `shell()` writes the wrapper
    assert _arch('skills') == 'split', 'the skills page is no longer a split pane'
    assert 'class="card tdet" id="skDet"' in _JS
    row = _JS[_JS.index('const row=(r,i)=>'):]
    row = row[:row.index('const det=')]
    assert 'skdesc' not in row, 'a description on every row is the wall this replaced'
    assert '${act(r)}' not in row, 'the buttons belong to the skill you picked'
    # …but everything the row is SCANNED for stays on it, which is also what
    # tools/smoke_gui.py reads out of #content's innerText
    for want in ('data-scope', 'skcmd', '${usage(r)}${warn(r)}'):
        assert want in row, f'the skill row lost {want}'
    # nothing picked yet is the Add form, so the pane is never an empty state
    assert 'id="skDet">${SKADD}' in _JS


def test_a_picked_row_survives_the_filter():
    """Why the selection needs no filter hook of its own: bindFilter already
    refuses to hide a row carrying `.on`, because filtering is a way to find
    more and not a way to lose track of what you picked. Take that clause out
    and picking a skill then typing in the box empties the detail pane's row."""
    run = _JS[_JS.index('const run=window['):]
    run = run[:run.index('inp.oninput=run')]
    assert "classList.contains('on')" in run

# ── a layout rule reads its container, never the window ──────────────

def _at_blocks(css, at):
    """(prelude, body) for every `@<at> …{ … }` block, brace-matched.

    Same reason `test_gui_flicker._keyframes` is hand-written rather than a
    regex: these bodies nest, and a non-greedy `{.*?}` stops at the first inner
    close brace while a greedy one runs to the end of the stylesheet."""
    out = []
    for m in re.finditer(r'@' + at + r'([^{]*)\{', css):
        i = m.end() - 1
        depth = 0
        for j in range(i, len(css)):
            if css[j] == '{':
                depth += 1
            elif css[j] == '}':
                depth -= 1
                if depth == 0:
                    out.append((m.group(1).strip(), css[i + 1:j]))
                    break
    return out


#: Selectors whose width is decided by the box they are in, never by the
#: window. A card lives in a 560-760px track of #content's grid at every window
#: above 1280px, so a `@media` query about the viewport was asking about a
#: number two to four times too big — and the sidebar is draggable, which moves
#: the content edge by up to 240px with no media query noticing. This is the
#: whole pass in one assertion.
CONTAINED = ('.tbl', '.cctable', '.dash', '.tpane', '.cols3', '.pghd', '.memhd')


def test_a_container_shaped_rule_is_never_a_media_query():
    """Every one of these used to break on a viewport width, so none of them
    ever fired in the state people actually run the app in: `.tbl` stacked at
    719px of WINDOW while the card holding a five-column table was 740px wide
    inside a 2048px one. The photographed symptom was that table's status
    column rendering 23px wide and wrapping to three lines."""
    for prelude, body in _at_blocks(_CSS, 'media'):
        for sel in CONTAINED:
            assert sel + '{' not in body and sel + ',' not in body, (
                f'@media{prelude} styles {sel} — that is a container query')


def test_the_two_containers_are_declared():
    """`#content` and `.card` are the two boxes every internal layout decision
    is actually about, so they are the two named containers. Nothing else needs
    a name: a query resolves outward to the nearest ancestor that has one."""
    # the newline anchors the BASE rule: `.card{` on its own matches
    # `.content>.card{` first, which is a different rule about a different thing
    for sel, name in ((NL + '.content{', 'page'), (NL + '.card{', 'card')):
        block = _CSS[_CSS.index(sel):]
        block = block[:block.index('}')]
        assert f'container:{name}/inline-size' in block.replace(' ', ''), \
            f'{sel} is not a container any more'
    # a modal and the drawer too, or a query inside one resolves to #content —
    # or, when the modal is opened from a page that has no #content, to nothing
    for sel in (NL + '.modal{', NL + '.drawer{'):
        block = _CSS[_CSS.index(sel):]
        block = block[:block.index('}')]
        assert 'container:card/inline-size' in block.replace(' ', ''), \
            f'{sel} is not a container'


def test_every_container_query_names_a_container():
    """An unnamed `@container (max-width:…)` resolves to whichever ancestor
    happens to be nearest, which is `.card` on one page and `#content` on
    another — the same class of bug as the media queries this replaced."""
    blocks = _at_blocks(_CSS, 'container')
    assert len(blocks) >= 6, f'only {len(blocks)} container queries'
    for prelude, _ in blocks:
        assert prelude.split()[0] in ('page', 'card'), \
            f'@container {prelude} does not name a container'


def test_a_card_whose_content_needs_the_row_takes_the_row():
    """Instead of a hand-maintained list of `.wide` literals, which is exactly
    the kind of copy this file exists to distrust: a five-column table and the
    settings matrix are wide by construction, so they say so themselves."""
    for host in ('.content>', '.pile>'):
        assert f'{host}.card:has(.tbl th:nth-child(4))' in _CSS
        assert f'{host}.card:has(.cctable)' in _CSS


def test_no_layout_keeps_a_column_count_it_cannot_justify():
    """`1fr 1fr` and `repeat(3,…)` are counts with no argument behind them: the
    two-up form was still two-up inside a 380px card, where each field was too
    narrow to show its own value, and `.cols3` asked the WINDOW whether three
    210px columns fit in a card the window knows nothing about."""
    for sel in ('.grid2{', '.cols3{', '.acct-rail{'):
        block = _CSS[_CSS.index(sel):]
        block = block[:block.index('}')]
        assert 'auto-fit' in block or 'auto-fill' in block, \
            f'{sel} carries a fixed column count again'
    # and the rail is a grid, not a flex row that hides accounts off-screen
    assert '.acct-card{flex:0 0' not in _CSS.replace(' ', ''), \
        'the plan-usage rail clips accounts again'


# ── the pile ─────────────────────────────────────────────────────────

def test_a_pile_balances_instead_of_leaving_rows_ragged():
    """A grid ROW is what makes a hole: it is as tall as its tallest card and
    `align-items:start` leaves the rest dark, so a page holding a 147px card
    beside a 794px one had 650px of nothing in the middle. Multicol balances
    the columns instead — with no breakpoint and, crucially, nothing to mark by
    hand, because a card's height is DATA (Help's project card is 656px next to
    thirteen projects and 200px next to two)."""
    block = _CSS[_CSS.index('.pile{'):]
    block = block[:block.index('}')]
    assert 'columns:var(--card-min' in block.replace(' ', ''), \
        'a pile no longer breaks at the same width as the grid'
    kids = _CSS[_CSS.index('.pile>*{'):]
    kids = kids[:kids.index('}')]
    assert 'break-inside:avoid' in kids, 'a card can be sliced across columns'
    assert '.pile>*:not(.card)' in _CSS, 'furniture no longer spans a pile'


def test_every_page_declares_a_shape():
    """A page's composition used to be whatever its renderer happened to emit,
    so `paint` vs `paintPile` was a choice made 28 separate times and nothing
    could tell a considered layout from an accident. The archetype is that
    decision, declared in the same table the page is declared in — which is
    what makes it impossible to add a page without one."""
    ids = re.findall(r"^\s*\['([a-z]+)'", _JS[_JS.index('const NAV=['):
                                              _JS.index('const SECTIONS=[')],
                     re.M)
    assert len(ids) == 19, f'expected 19 NAV pages, parsed {len(ids)}'
    for page in ids:
        assert _arch(page) in SHAPES, \
            f'{page} declares no archetype (or an unknown one: {_arch(page)!r})'
    tab_ids = re.findall(r"^\s*\['([a-z]+)'", _JS[_JS.index('const TABS=['):
                                                 _JS.index('const TAB_GROUPS=[')],
                         re.M)
    assert len(tab_ids) == 9, f'expected 9 project tabs, parsed {len(tab_ids)}'
    for tab in tab_ids:
        assert _arch(tab) in SHAPES, f'tab {tab} declares no archetype'


def test_the_shell_is_the_only_thing_that_writes_a_layout_wrapper():
    """One writer for `.pile`, `.dash`, `.tpane` and every shape after them,
    for the same reason `paint`/`paintNow` are the only writers of `#content`:
    a renderer that hand-writes the wrapper is a renderer that will be missing
    `break-inside` the day the rule changes, and four hand-written wrappers is
    four chances to disagree about what a shape means.

    Asserted as an ABSENCE across the whole of app.js, so a new page cannot
    reintroduce one — the previous form of this check counted `class="pile"`
    and had nothing to say about the two hand-written `.tpane`s or the
    dashboard's own `.dash`, all three of which existed while it passed."""
    assert 'function shellNow(html){return paintNow(shellWrap(html));}' in _JS
    assert 'function shell(nav,html){return paint(nav,shellWrap(html));}' in _JS
    # the wrapper class appears exactly once each: inside ARCH_WRAP
    for shape in ('pile', 'dash', 'tpane'):
        assert f'class="{shape}"' not in _JS, \
            f'a renderer is hand-writing the {shape} wrapper — use shell()'
    assert _JS.count('ARCH_WRAP=') == 1 and _JS.count('function shellWrap(') == 1
    # and the shape is read from the table, never passed in by the caller
    assert re.search(r'function shell\(nav,html\)\{return paint\(nav,'
                     r'shellWrap\(html\)\);\}', _JS), \
        'shell() takes an archetype argument — a renderer must not claim a shape'


def test_a_designed_layout_is_never_a_pile():
    """This used to be four function names typed into this file. It is every
    page now, derived from what each one declares: multicol pours content down
    column 1 and then starts column 2, so a pile is right for INDEPENDENT
    sections and wrong for anything whose order or composition is designed."""
    for page, arch in _ARCH.items():
        if arch == 'pile':
            continue
        assert arch in SHAPES
    # the shapes that are compositions rather than a stack
    for page in ('agents', 'skills'):
        assert _arch(page) == 'split', f'{page} stopped being a list + detail'
    assert _ARCH.get('sessions') != 'pile', 'the sessions list is not a pile'


def test_the_migration_marker_only_ever_shrinks():
    """`grid` is what a page is before anyone decided what it should be — a bag
    of cards dropped into the auto-fit grid. It is scaffolding for this rehaul,
    so the count is pinned DOWNWARD: a page may leave it, nothing may join it,
    and when the last one goes the shape itself should be deleted rather than
    left as a place for the next page to land by default."""
    grid = sorted(p for p, a in _ARCH.items() if a == 'grid')
    assert len(grid) <= 12, \
        f'{len(grid)} pages still undesigned, was 12: {grid}'


# ── and the tool that measures all of it ─────────────────────────────

def test_the_space_audit_measures_dead_space_and_says_how_much_it_measured():
    """Every other probe in shot_gui asks whether something sticks OUT. None of
    them could see the opposite failure, which is the one people photograph, so
    all three reported defects passed every audit in that file for its whole
    life. And a probe that stops finding containers reports `clean` — the same
    trap smoke_gui's check floor exists for."""
    src = _read_tool('shot_gui.py')
    assert 'SPACE_JS' in src and 'def audit_space(' in src
    assert re.search(r'SPACE_FLOOR = \d+', src), 'the probe has no floor'
    assert 'SPACE_PROBED[0] < SPACE_FLOOR' in src, 'the floor is not enforced'
    assert 'return 1' in src.split('— space audit —')[1], \
        'the space audit prints its findings without failing the run'
    # it runs on every page and tab at every width, and on every skin
    widths = src[src.index('def audit_widths('):]
    assert 'audit_space(pg, f\'{w}px {page}\')' in widths
    assert 'audit_space(pg, f\'{w}px tab {tab}\')' in widths
    assert "audit_space(pg, f'{sk} {w}px home')" in src


def test_the_space_probe_measures_the_thing_and_not_an_artefact_of_it():
    """Three of these were wrong in the first cut and each reported a page that
    was laid out correctly — which is why they are pinned rather than trusted:

      * a table cell's BOX is as tall as its row, so measuring that says only
        that some other column is tall (twenty false reports);
      * a full-row card compared against `#content`'s PADDED width looks like a
        row one item short (every `.wide` card);
      * a pile bucketed by x across a `column-span:all` boundary puts the first
        run's left column and the last run's left column in one bucket (a
        1433px imbalance in a pile with none)."""
    src = _read_tool('shot_gui.py')
    assert 'rng.selectNodeContents(td)' in src, \
        'the cramped check is back to measuring the row height'
    assert 'g.clientWidth-parseFloat(st.paddingLeft' in src.replace(' ', ''), \
        'the band test is back to the padded width'
    assert 'runs[runs.length - 1].push(b)' in src.replace('  ', ' '), \
        'the pile balance is no longer measured per run'
    assert 'gap > tallest + 16' in src, \
        'an imbalance smaller than one card is arithmetic, not a fault'
    # the four dashboard tiles are one ROW only while they are on one line
    assert 'IHEIGHTS_JS' in src and 'rows.get(r).push' in src


# The pile's single-writer check lived here and is now
# test_the_shell_is_the_only_thing_that_writes_a_layout_wrapper, which asserts
# the same invariant for every shape instead of only for `.pile`. It counted
# `class="pile"` and therefore had nothing to say about the two hand-written
# `.tpane` wrappers or the dashboard's own `.dash` — all three of which were in
# the file, and passing, the whole time it existed.


def test_a_card_that_cannot_share_a_row_cannot_share_a_column_either():
    """The grid and the pile are two layouts for the same cards, so the cards
    that take the whole row in one have to take the whole width in the other.
    Miss one and a six-column table quietly becomes 560px wide on the pages
    that are piles — the exact bug the grid rule was written to stop, moved one
    layout over and invisible because nothing throws.

    Compared as SETS rather than asserted by name: the point is that adding a
    case to one layout and forgetting the other fails, which a list of literals
    could not tell you."""
    def spanners(prop, prefix):
        out = set()
        for m in re.finditer(r'([^{}]+)\{[^{}]*' + re.escape(prop) + r'[;}]', _CSS):
            for sel in m.group(1).split(','):
                sel = sel.strip()
                if sel.startswith(prefix + '.card'):
                    out.add(sel[len(prefix):])
        return out

    grid = spanners('grid-column:1/-1', '.content>')
    pile = spanners('column-span:all', '.pile>')
    assert grid, 'no full-row cards found — the selector shape moved'
    assert grid == pile, f'grid spans {grid - pile} but the pile does not'


def test_the_space_audit_can_fail_and_knows_when_it_measured_nothing():
    """The audit that finds the OPPOSITE of overflow — a page not using the
    room it has — and the two things that make its silence mean something.

    It has to be able to fail: every other probe in that file only PRINTS, which
    is why `instrument row RAGGED` went unfixed for as long as it did. And it
    needs a floor on how much it looked at, because a selector that stops
    matching reports exactly what a clean page reports — the lesson smoke_gui's
    own floor already carries, one tool over."""
    src = _read_tool('shot_gui.py')
    assert 'SPACE_JS' in src and 'def audit_space(' in src
    assert re.search(r'SPACE_FLOOR = \d+', src), 'the space audit has no floor'
    assert 'SPACE_PROBED[0] < SPACE_FLOOR' in src, 'the floor is not checked'
    assert "sys.exit(main())" in src, 'main() returns a code nothing reads'
