"""T-1397 · the ten highest-risk UNCOVERED branches of claude_sessions/ui.py menu
search and key handling, lines 597-727 (menu, its _filtered, _nav_idx and the key
loop), at tip 6a32dc14. Ranking is fail-closed first, then boundaries, then
error paths. Each test's docstring names the branch it catches.

Final selected branches (file:line, closest existing test, why it misses):

 1. ui.py:611-619  a query that matches nothing returns the FULL list, so ENTER
    returns the first row. PREMISE REJECTED: the screen shows the full list with
    the cursor on row 0 and no "no matches" text, so the behaviour is visible and
    is pinned as a passing test -> test_no_match_query_falls_back_to_full_list
    (closest: tests/test_tui_main.py:190 ESC clears a no-match filter, no ENTER)
 2. ui.py:617-618  '__global_claude_md__' stays findable under any match
                   -> test_global_claude_md_stays_findable_under_any_match
    (closest: none for menu())
 3. ui.py:612-613  an empty query keeps separators in place
                   -> test_empty_query_keeps_separators_in_place
 4. ui.py:615-616  a separator is never matched by a query, nor returned
                   -> test_separator_never_selected_by_query
 5. ui.py:717-722  ESC with a query clears it and resets the cursor; ESC on an
    empty query returns None -> test_esc_clears_query_before_leaving
    (closest: tests/test_tui_main.py:190, main menu only, cursor not asserted)
 6. ui.py:723-726  BACKSPACE shortens the query and resets the cursor; on an
    empty query it does nothing -> test_backspace_shortens_query_and_resets_cursor
 7. ui.py:727-729  typing resets the cursor to the first match
                   -> test_typing_resets_cursor_to_first_match
 8. ui.py:645-663  window keeps the cursor visible and counts hidden rows
                   -> test_window_keeps_cursor_visible_and_counts_hidden_rows
    (closest: tests/test_tui_main.py:150 and test_tui_sessions.py windowing,
    which assert only that a row is visible, not the marker counts)
 9. ui.py:621-627  all-separator list: no cursor, no crash
                   -> test_all_separator_list_has_no_cursor_and_no_crash
10. ui.py:709-712  UP and DOWN wrap over navigable rows only
                   -> test_up_down_wrap_over_navigable_rows_only

Every key comes from a scripted list; a script that runs out fails the test
instead of hanging. Drawing is stubbed and captured; no real terminal, sleep,
subprocess or home directory is touched.
"""
from claude_sessions import render, ui


def _type(text):
    return [('char', ch) for ch in text]


def _menu(monkeypatch, items, script, height=60):
    events = list(script)
    frames = []

    def next_event():
        if not events:
            raise AssertionError('script ran out before the menu returned')
        return events.pop(0)

    monkeypatch.setattr(ui, 'poll_event', next_event)
    monkeypatch.setattr(ui, '_size_changed', lambda: False)
    monkeypatch.setattr(ui.time, 'sleep', lambda s: None)
    monkeypatch.setattr(render, 'render_frame',
                        lambda lines: frames.append([render.strip_ansi(x) for x in lines]))
    monkeypatch.setattr(render, 'header', lambda *a: 'HEADER')
    monkeypatch.setattr(render, 'hint_keys', lambda pairs, *a, **k: 'HINT')
    monkeypatch.setattr(render, 'row',
                        lambda label, selected=False: ('> ' if selected else '  ') + label)
    monkeypatch.setattr(render, 'sep_line', lambda label: 'SEP ' + label)
    monkeypatch.setattr(render, 'frame_height', lambda: height)
    result = ui.menu(items, 'TITLE')
    assert not events, 'menu returned before consuming the whole script'
    return result, frames


def _find(frame, text):
    return [i for i, line in enumerate(frame) if text in line]


def test_no_match_query_falls_back_to_full_list(monkeypatch):
    """Branch: ui.py:619 — a query that matches nothing shows the full list with
    the cursor on row 0, and ENTER returns that row. Pinned as current behaviour:
    the screen never says "no matches", so this is not a defect the screen
    contradicts."""
    items = [('Open project', 'open'), ('Settings', 'settings')]
    result, frames = _menu(monkeypatch, items, _type('zzz') + [('enter',)])
    assert result == 'open'
    assert _find(frames[-1], '[ zzz▌ ]')
    assert _find(frames[-1], '> Open project')
    assert _find(frames[-1], '  Settings')
    assert not _find(frames[-1], 'no match')


def test_global_claude_md_stays_findable_under_any_match(monkeypatch):
    """Branch: ui.py:617-618 — the global CLAUDE.md row is appended to a matched
    result even though its own label does not match the query."""
    items = [('Alpha project', 'a'), ('Global CLAUDE.md', '__global_claude_md__'),
             ('Beta project', 'b')]
    result, frames = _menu(monkeypatch, items,
                           _type('alpha') + [('down',), ('enter',)])
    assert result == '__global_claude_md__'
    assert _find(frames[-1], '> Global CLAUDE.md')


def test_empty_query_keeps_separators_in_place(monkeypatch):
    """Branch: ui.py:612-613 — an empty query returns the items unchanged, with
    separators drawn between their rows."""
    items = [('Top', 't'), ('────', None), ('Bottom', 'b')]
    result, frames = _menu(monkeypatch, items, [('enter',)])
    assert result == 't'
    top, sep, bottom = (_find(frames[-1], s)[0] for s in ('Top', 'SEP ────', 'Bottom'))
    assert top < sep < bottom


def test_separator_never_selected_by_query(monkeypatch):
    """Branch: ui.py:615-616 — a separator whose label matches the query is not
    shown, and the query's ENTER returns the matching real row."""
    items = [('x separator', None), ('xray', 'x1'), ('Yak', 'y')]
    result, frames = _menu(monkeypatch, items, _type('x') + [('enter',)])
    assert result == 'x1'
    assert not _find(frames[-1], 'SEP x separator')
    assert _find(frames[-1], '> xray')


def test_esc_clears_query_before_leaving(monkeypatch):
    """Branch: ui.py:717-722 — ESC with a query clears it without returning; the
    next ESC on the empty query returns None."""
    items = [('Alpha', 'a'), ('Beta', 'b')]
    result, frames = _menu(monkeypatch, items, _type('zz') + [('esc',), ('esc',)])
    assert result is None
    assert any(_find(f, '[ zz▌ ]') for f in frames)
    assert _find(frames[-1], '[ search... ]')


def test_backspace_shortens_query_and_resets_cursor(monkeypatch):
    """Branch: ui.py:723-726 — BACKSPACE on an empty query does nothing; on a
    query it drops one character and resets the cursor to the first match."""
    items = [('ab one', '1'), ('ab two', '2'), ('a x', '3')]
    script = [('back',)] + _type('ab') + [('down',), ('back',), ('enter',)]
    result, frames = _menu(monkeypatch, items, script)
    assert result == '1'
    assert _find(frames[-1], '[ a▌ ]')


def test_typing_resets_cursor_to_first_match(monkeypatch):
    """Branch: ui.py:727-729 — a typed character resets the cursor, so ENTER
    returns the first match, not the row the cursor was on before typing."""
    items = [('apple', '1'), ('avocado', '2'), ('banana', '3')]
    result, _ = _menu(monkeypatch, items, [('down',), ('char', 'a'), ('enter',)])
    assert result == '1'


def test_window_keeps_cursor_visible_and_counts_hidden_rows(monkeypatch):
    """Branch: ui.py:645-663 — with 10 rows in a frame that fits 3, the cursor
    stays in the window and the hidden counts on both sides are exact."""
    items = [(f'item{i}', f'v{i}') for i in range(10)]
    result, frames = _menu(monkeypatch, items, [('down',)] * 6 + [('enter',)], height=12)
    assert result == 'v6'
    frame = frames[-1]
    assert _find(frame, '> item6')
    assert _find(frame, '  item5') and _find(frame, '  item7')
    assert not _find(frame, 'item4') and not _find(frame, 'item8')
    assert _find(frame, '… 5 more ↑')
    assert _find(frame, '… 2 more ↓')


def test_all_separator_list_has_no_cursor_and_no_crash(monkeypatch):
    """Branch: ui.py:621-627 — a list of separators only has no cursor: UP, DOWN
    and ENTER do nothing and ENTER returns None."""
    items = [('────', None), ('══', None)]
    result, frames = _menu(monkeypatch, items,
                           [('up',), ('down',), ('enter',)])
    assert result is None
    assert _find(frames[-1], 'SEP ────')
    assert not any(line.startswith('> ') for line in frames[-1])


def test_up_down_wrap_over_navigable_rows_only(monkeypatch):
    """Branch: ui.py:709-712 — UP from the first row wraps to the last navigable
    row, and DOWN from the last wraps to the first; separators are skipped."""
    items = [('A', 'a'), ('────', None), ('B', 'b')]
    result, _ = _menu(monkeypatch, items, [('up',), ('enter',)])
    assert result == 'b'
    result, _ = _menu(monkeypatch, items, [('down',), ('down',), ('enter',)])
    assert result == 'a'
