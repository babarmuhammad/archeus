"""T-1396 · the ten highest-risk UNCOVERED branches of claude_sessions/ui.py
text and path input, lines 428-551 (text_input, path_completions, _join_path,
path_input), at tip 6a32dc14. Ranking is fail-closed first (a cancelled or
non-directory input never returns a path), then boundaries, then error paths.

Final selected branches (file:line, closest existing test, why it misses):

 1. ui.py:514-527  ENTER on a non-directory with several suggestions keeps the
    input and flashes      -> test_enter_on_nondirectory_with_many_suggestions_keeps_input
    (test_tui_widgets.py:42 only covers ENTER on a real directory)
 2. ui.py:512-513  ESC returns None with a suggestion selected
                           -> test_esc_cancels_with_selection_active_returns_none
 3. ui.py:519-522  ENTER returns the absolute expanded path, not the raw text
                           -> test_enter_returns_absolute_expanded_dir
 4. ui.py:523-524  ENTER with one suggestion completes it and waits
                           -> test_enter_single_suggestion_completes_then_waits
 5. ui.py:533-537  TAB completes the common prefix without a separator
                           -> test_tab_completes_common_prefix_without_separator
    ui.py:535-536  TAB with one suggestion appends the separator
                           -> test_tab_single_match_appends_separator
    (test_tui_widgets.py:48 covers only the single-match tab through ENTER)
 6. ui.py:461-464  bare relative name uses '.' as base; separator suffix lists children
                           -> test_completions_relative_bare_name_uses_dot_base
 7. ui.py:457-460  empty text lists only drive roots that exist
                           -> test_empty_text_lists_only_existing_drive_roots
 8. ui.py:465-469  os.listdir failure returns no names and never raises
                           -> test_listdir_failure_returns_empty_names
 9. ui.py:474-475  _join_path with an empty base returns the bare name
                           -> test_join_path_empty_base_returns_name
10. ui.py:429-446  text_input: ESC is None, BACKSPACE on empty is a no-op,
                           ENTER strips the result
                           -> test_text_input_esc_none_and_empty_backspace_noop
                           -> test_text_input_enter_strips_the_result

Every event comes from a scripted list; a script that runs out fails the test
instead of hanging. flash, render_frame and the header are captured or stubbed.
Real directories live under tmp_path; no drive, home, subprocess or network.
"""
import os

from claude_sessions import render, ui

def _type(text):
    return [('char', ch) for ch in text]


def _drive(monkeypatch, script, fn, *args):
    events = list(script)
    frames = []
    flashes = []

    def next_event():
        if not events:
            raise AssertionError('script ran out before the screen returned')
        return events.pop(0)

    monkeypatch.setattr(ui, 'wait_event', next_event)
    monkeypatch.setattr(ui, 'flush_input', lambda: None)
    monkeypatch.setattr(ui, 'flash', lambda msg, ok=True, secs=0.8: flashes.append((msg, ok)))
    monkeypatch.setattr(render, 'render_frame',
                        lambda lines: frames.append([render.strip_ansi(x) for x in lines]))
    monkeypatch.setattr(render, 'header', lambda *a: 'HEADER')
    monkeypatch.setattr(render, 'hint_keys', lambda pairs, *a, **k: 'HINT')
    monkeypatch.setattr(render, 'content_width', lambda: 200)
    result = fn(*args)
    assert not events, 'screen returned before consuming the whole script'
    return result, frames, flashes


def _ends_with_line(frame, text):
    return any(line.endswith(text) for line in frame)


def test_enter_on_nondirectory_with_many_suggestions_keeps_input(monkeypatch, tmp_path):
    """Branch: ui.py:514-527 — non-directory and several suggestions: no return,
    the buffer is kept, one failure flash is shown."""
    (tmp_path / 'pa').mkdir()
    (tmp_path / 'pb').mkdir()
    typed = os.path.join(str(tmp_path), 'p')
    script = _type(typed) + [('enter',), ('esc',)]
    result, frames, flashes = _drive(monkeypatch, script, ui.path_input, 'Folder?', '')
    assert result is None
    assert flashes == [("Not a folder — pick a suggestion or type a valid path", False)]
    assert _ends_with_line(frames[-1], typed + '▌')


def test_esc_cancels_with_selection_active_returns_none(monkeypatch, tmp_path):
    """Branch: ui.py:512-513 — ESC wins over an active suggestion selection."""
    (tmp_path / 'pa').mkdir()
    (tmp_path / 'pb').mkdir()
    script = _type(os.path.join(str(tmp_path), 'p')) + [('down',), ('esc',)]
    result, frames, _ = _drive(monkeypatch, script, ui.path_input, 'Folder?', '')
    assert result is None
    assert _ends_with_line(frames[-1], '▸ pa' + '\\')


def test_enter_returns_absolute_expanded_dir(monkeypatch, tmp_path):
    """Branch: ui.py:519-522 — ENTER on an existing directory returns the
    absolute path of the typed text, never the raw relative text."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'sub').mkdir()
    script = _type('sub') + [('enter',)]
    result, _, flashes = _drive(monkeypatch, script, ui.path_input, 'Folder?', '')
    assert result == os.path.abspath('sub')
    assert os.path.isabs(result)
    assert flashes == []


def test_enter_single_suggestion_completes_then_waits(monkeypatch, tmp_path):
    """Branch: ui.py:523-524 — one suggestion and a non-directory: ENTER completes
    it with a trailing separator and does not return; the next ENTER returns it."""
    (tmp_path / 'projects').mkdir()
    typed = os.path.join(str(tmp_path), 'pro')
    script = _type(typed) + [('enter',), ('enter',)]
    result, _, flashes = _drive(monkeypatch, script, ui.path_input, 'Folder?', '')
    assert result == os.path.abspath(str(tmp_path / 'projects'))
    assert flashes == []


def test_tab_completes_common_prefix_without_separator(monkeypatch, tmp_path):
    """Branch: ui.py:533-537 — several suggestions: TAB completes only the
    common prefix, with no separator appended."""
    (tmp_path / 'alpha_one').mkdir()
    (tmp_path / 'alpha_two').mkdir()
    script = _type(os.path.join(str(tmp_path), 'al')) + [('tab',), ('esc',)]
    result, frames, _ = _drive(monkeypatch, script, ui.path_input, 'Folder?', '')
    assert result is None
    assert _ends_with_line(frames[-1], os.path.join(str(tmp_path), 'alpha_') + '▌')
    assert not _ends_with_line(frames[-1], os.path.join(str(tmp_path), 'alpha_') + os.sep + '▌')


def test_tab_single_match_appends_separator(monkeypatch, tmp_path):
    """Branch: ui.py:535-536 — one suggestion: TAB completes it and appends the
    separator."""
    (tmp_path / 'solo').mkdir()
    script = _type(os.path.join(str(tmp_path), 'so')) + [('tab',), ('esc',)]
    result, frames, _ = _drive(monkeypatch, script, ui.path_input, 'Folder?', '')
    assert result is None
    assert _ends_with_line(frames[-1], os.path.join(str(tmp_path), 'solo') + os.sep + '▌')


def test_completions_relative_bare_name_uses_dot_base(monkeypatch, tmp_path):
    """Branch: ui.py:461-464 — a bare relative name lists the current directory
    (base '.'); a trailing separator lists that directory's children."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'alpha').mkdir()
    (tmp_path / 'alps').mkdir()
    (tmp_path / 'beta').mkdir()
    (tmp_path / 'alpha' / 'child').mkdir()
    assert ui.path_completions('al') == ('.', 'al', ['alpha', 'alps'])
    assert ui.path_completions('alpha' + os.sep) == ('alpha' + os.sep, '', ['child'])


def test_empty_text_lists_only_existing_drive_roots(monkeypatch):
    """Branch: ui.py:457-460 — empty text lists the drive roots that exist and
    nothing when none does."""
    present = {'C:\\', 'E:\\'}
    monkeypatch.setattr(os.path, 'isdir', lambda p: p in present)
    assert ui.path_completions('') == ('', '', ['C:\\', 'E:\\'])
    present.clear()
    assert ui.path_completions('') == ('', '', [])


def test_listdir_failure_returns_empty_names(monkeypatch, tmp_path):
    """Branch: ui.py:465-469 — an unreadable folder answers with no names and
    never raises into the input loop."""
    (tmp_path / 'alpha').mkdir()

    def denied(path):
        raise PermissionError(13, 'synthetic denial')

    monkeypatch.setattr(os, 'listdir', denied)
    base, partial, names = ui.path_completions(os.path.join(str(tmp_path), 'al'))
    assert base == str(tmp_path)
    assert partial == 'al'
    assert names == []


def test_join_path_empty_base_returns_name(tmp_path):
    """Branch: ui.py:474-475 — an empty base returns the bare name; a real base
    joins with the platform separator."""
    assert ui._join_path('', 'name') == 'name'
    assert ui._join_path(str(tmp_path), 'name') == os.path.join(str(tmp_path), 'name')


def test_text_input_esc_none_and_empty_backspace_noop(monkeypatch):
    """Branch: ui.py:444-449 — ESC is None (not ''), and BACKSPACE on an empty
    buffer changes nothing."""
    result, _, _ = _drive(monkeypatch, [('back',), ('char', 'a'), ('esc',)],
                          ui.text_input, 'Name?')
    assert result is None
    result, _, _ = _drive(monkeypatch, [('back',), ('char', 'x'), ('enter',)],
                          ui.text_input, 'Name?')
    assert result == 'x'


def test_text_input_enter_strips_the_result(monkeypatch):
    """Branch: ui.py:443-444 — the default is the starting buffer, and ENTER
    returns it stripped."""
    result, _, _ = _drive(monkeypatch, [('enter',)], ui.text_input, 'Name?', '  hi  ')
    assert result == 'hi'
