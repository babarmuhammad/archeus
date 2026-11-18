"""T-1398 · the ten highest-risk UNCOVERED branches of claude_sessions/render.py
screen state and row helpers, lines 197-276 (screen_init, screen_restore,
screen_active, frame_height, header, hline, sep_line, row, hint_bar), at tip
6a32dc14. Ranking is fail-closed first (no escape sequence without an active VT
screen, and a restore only undoes an init), then boundaries, then error paths.

Final selected branches (file:line, closest existing test, why it misses):

 1. render.py:211-212  restore when never initialised writes nothing and
                       invalidates nothing -> test_restore_without_init_writes_nothing
    (closest: tests/test_render.py:90, init no-op only)
 2. render.py:200-201  init without VT stays inactive and restore after it writes
                       nothing -> test_restore_after_failed_init_writes_nothing
    (closest: tests/test_render.py:90 runs without a tty, no VT seam)
 3. render.py:200-205  init twice enters the alternate screen once
                       -> test_init_twice_enters_alternate_once
 4. render.py:211-216  restore after init writes the leave sequence once
                       -> test_restore_twice_writes_leave_once
    (closest: tests/test_gaps7_claude_sessions_system_prompt.py, side effect only)
 5. render.py:225-228  frame_height reads the console and falls back to 24
                       -> test_frame_height_reads_console_and_falls_back_to_24
 6. render.py:256-258  a mixed dash label is text, not a rule
                       -> test_sep_line_mixed_dash_label_is_text_not_rule
    (closest: tests/test_render.py:187-196, plain text and pure dash only)
 7. render.py:265-267  a selected row strips inner colour, an unselected one keeps it
                       -> test_row_selected_strips_inner_colour_only_when_selected
 8. render.py:273-274  hint_bar strips ANSI and outer space before fit
                       -> test_hint_bar_strips_ansi_and_outer_space
 9. render.py:240-245  a header with no crumbs is a padded bar; crumbs use the arrow
                       -> test_header_no_crumbs_is_padded_bar
    (closest: tests/test_render.py:198, many crumbs only)
10. render.py:248-250  hline below width 4 gives an empty run
                       -> test_hline_small_width_has_no_dash_run
    Weak probe: max(0, ...) is not what keeps this empty, since '─' * -n is also
    ''. The test pins the output; removing max() would not fail it.

Escape sequences are captured through the _w seam; the VT probe, the flush, the
invalidate counter and the terminal size are all faked. No console, no alternate
screen, no subprocess.
"""
import os
from types import SimpleNamespace

from claude_sessions import config as _c
from claude_sessions import render

ENTER_SEQ = '\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H'
LEAVE_SEQ = '\x1b[0m\x1b[?25h\x1b[?1049l'


def _screen(monkeypatch, vt=True):
    writes = []
    invalidations = []
    monkeypatch.setattr(render, '_w', writes.append)
    monkeypatch.setattr(render, '_flush', lambda: None)
    monkeypatch.setattr(render, 'invalidate', lambda: invalidations.append(1))
    monkeypatch.setattr(render, '_vt_ok', lambda: vt)
    monkeypatch.setattr(render, '_screen_active', False)
    return writes, invalidations


def test_restore_without_init_writes_nothing(monkeypatch):
    """Branch: render.py:211-212 — restore with no init in effect is silent."""
    writes, invalidations = _screen(monkeypatch)
    render.screen_restore()
    assert writes == []
    assert invalidations == []
    assert render.screen_active() is False


def test_restore_after_failed_init_writes_nothing(monkeypatch):
    """Branch: render.py:200-201 — without VT, init does nothing, so a later
    restore must not write a leave sequence for a screen never entered."""
    writes, invalidations = _screen(monkeypatch, vt=False)
    render.screen_init()
    render.screen_restore()
    assert writes == []
    assert invalidations == []
    assert render.screen_active() is False


def test_init_twice_enters_alternate_once(monkeypatch):
    """Branch: render.py:200 — a second init while active is a no-op."""
    writes, invalidations = _screen(monkeypatch)
    render.screen_init()
    render.screen_init()
    assert writes == [ENTER_SEQ]
    assert invalidations == [1]
    assert render.screen_active() is True


def test_restore_twice_writes_leave_once(monkeypatch):
    """Branch: render.py:211-216 — the first restore undoes exactly one init and
    the second writes nothing."""
    writes, invalidations = _screen(monkeypatch)
    render.screen_init()
    render.screen_restore()
    render.screen_restore()
    assert writes == [ENTER_SEQ, LEAVE_SEQ]
    assert invalidations == [1, 1]
    assert render.screen_active() is False


def test_frame_height_reads_console_and_falls_back_to_24(monkeypatch):
    """Branch: render.py:225-228 — the console's line count is used, and a
    failing size probe answers 24."""
    # render.shutil is the global module, and pytest's own progress line calls
    # get_terminal_size before teardown: undo each patch before returning.
    with monkeypatch.context() as m:
        m.setattr(render.shutil, 'get_terminal_size',
                  lambda *a, **k: os.terminal_size((80, 41)))
        assert render.frame_height() == 41

    def broken(*a, **k):
        raise OSError('synthetic: no console')

    with monkeypatch.context() as m:
        m.setattr(render.shutil, 'get_terminal_size', broken)
        assert render.frame_height() == 24


def test_sep_line_mixed_dash_label_is_text_not_rule(monkeypatch):
    """Branch: render.py:256-258 — only a label made of nothing but box dashes
    becomes a rule; a label with any letter is text, truncated to the width."""
    monkeypatch.setattr(render, 'content_width', lambda: 20)
    text = render.sep_line('── x ──')
    assert text == f'  {_c.C_DIM}── x ──{_c.C_RESET}'
    assert '─' * 16 not in text
    rule = render.sep_line('  ──  ')
    assert rule == render.hline()
    cut = render.sep_line('x' * 30)
    assert render.strip_ansi(cut) == '  ' + 'x' * 17 + '…'


def test_row_selected_strips_inner_colour_only_when_selected(monkeypatch):
    """Branch: render.py:265-267 — the selected highlight drops inner colour so
    the bar is uniform; an unselected row keeps it."""
    monkeypatch.setattr(render, 'content_width', lambda: 40)
    label = '\x1b[38;5;208mX\x1b[0m'
    selected = render.row(label, selected=True)
    plain = render.row(label, selected=False)
    assert '38;5;208' not in selected
    assert _c.C_SEL_BG in selected
    assert '38;5;208' in plain


def test_hint_bar_strips_ansi_and_outer_space(monkeypatch):
    """Branch: render.py:273-274 — escape codes and outer space are removed before
    the fit, so the bar is exactly the content width."""
    monkeypatch.setattr(render, 'content_width', lambda: 40)
    out = render.hint_bar('   \x1b[38;5;208mhi\x1b[0m  ')
    assert '38;5;208' not in out
    assert render.strip_ansi(out).strip() == 'hi'
    assert len(render.strip_ansi(out)) == 40


def test_header_no_crumbs_is_padded_bar(monkeypatch):
    """Branch: render.py:240-245 — no crumbs gives a blank bar at full width;
    crumbs are joined by the arrow glyph."""
    monkeypatch.setattr(render, 'content_width', lambda: 30)
    empty = render.strip_ansi(render.header())
    assert empty.strip() == ''
    assert len(empty) == 30
    assert 'ARCHEUS ▸ proj' in render.strip_ansi(render.header('ARCHEUS', 'proj'))


def test_hline_small_width_has_no_dash_run(monkeypatch):
    """Branch: render.py:248-250 — a width below 4 gives an empty dash run; the
    rule is only the two-space indent."""
    assert render.strip_ansi(render.hline(2)) == '  '
    assert render.strip_ansi(render.hline(4)) == '  '
    assert render.strip_ansi(render.hline(5)) == '  ─'
