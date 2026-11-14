"""T-1330 — deny-rule scan and merge in claude_sessions/denygen.py, lines 23-131.

Selected branches (highest risk first):
  1. :77-83 + :96  malformed .claude/settings.json is overwritten (xfail, premise)
  2. :86-87        non-list permissions.deny is replaced silently (xfail, premise)
  3. :95-96        every pattern present: no write, bytes unchanged (control)
  4. :89-94        existing deny order kept, only new patterns appended
  5. :123-129      esc or a declined confirm writes nothing and calls no merge_deny
  6. :109-115      nothing heavy: the screen returns on esc or enter, no merge
  7. :34-36        missing project or file path returns [] (scan of None is xfail)
  8. :48-57        .git skipped; heavy dir reported once, not descended into
  9. :56-57, :42-46 heavy dir at max_depth reported, one below not; OSError skipped
 10. :58-65        lock file at depth reported as Read(**/name), size floored to KB, unreadable size 0

Seams: tmp_path trees only; ui.wait_event, ui.confirm, ui.flash and render.render_frame
are monkeypatched for the screen probes; os.scandir and os.path.getsize are wrapped
for the unreadable-entry probes and restored by monkeypatch.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import denygen, render, ui


def _proj(tmp_path, name='proj'):
    proj = tmp_path / name
    proj.mkdir()
    return proj


def _settings(proj):
    return proj / '.claude' / 'settings.json'


def _write_settings(proj, raw):
    sp = _settings(proj)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_bytes(raw.encode('utf-8'))
    return sp


def _screen(monkeypatch, events, confirm_answer=True):
    calls = {'merge': [], 'confirm': 0, 'flash': 0, 'frames': []}
    queue = iter(events)

    def fake_merge(project_path, patterns):
        calls['merge'].append(list(patterns))
        return len(patterns), 0

    def fake_confirm(question, *a, **k):
        calls['confirm'] += 1
        return confirm_answer

    def fake_flash(*a, **k):
        calls['flash'] += 1

    monkeypatch.setattr(denygen, 'merge_deny', fake_merge)
    monkeypatch.setattr(render, 'render_frame', lambda frame: calls['frames'].append(frame))
    monkeypatch.setattr(ui, 'wait_event', lambda: next(queue))
    monkeypatch.setattr(ui, 'confirm', fake_confirm)
    monkeypatch.setattr(ui, 'flash', fake_flash)
    return calls


def test_scan_heavy_file_path_and_missing_project_return_empty(tmp_path):
    proj = _proj(tmp_path)
    (proj / 'node_modules').mkdir()
    (proj / 'package.json').write_text('{}', encoding='utf-8')

    assert denygen.scan_heavy(str(proj / 'package.json')) == []
    assert denygen.scan_heavy(str(tmp_path / 'missing')) == []
    assert denygen.scan_heavy(str(proj)) == [
        ('Read(node_modules/**)', 'node_modules/ present, 0 entries')]


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/denygen.py:34 abspath('') returns the process cwd, so the "
    "`not root` guard at :35 never fires and scan_heavy(None) scans the cwd"))
def test_scan_heavy_without_project_does_not_scan_cwd(monkeypatch, tmp_path):
    proj = _proj(tmp_path)
    (proj / 'node_modules').mkdir()
    monkeypatch.chdir(proj)

    assert denygen.scan_heavy(None) == []


def test_scan_heavy_skips_git_and_does_not_descend_heavy_dirs(tmp_path):
    proj = _proj(tmp_path)
    (proj / '.git' / 'node_modules').mkdir(parents=True)
    (proj / '.git' / 'node_modules' / 'g.js').write_text('g', encoding='utf-8')
    (proj / 'node_modules' / 'build').mkdir(parents=True)
    (proj / 'node_modules' / 'build' / 'keep.txt').write_text('k', encoding='utf-8')
    (proj / 'node_modules' / 'lib').mkdir()
    (proj / 'node_modules' / 'lib' / 'x.js').write_text('x', encoding='utf-8')
    (proj / 'src' / 'node_modules').mkdir(parents=True)
    (proj / 'src' / 'node_modules' / 'a.js').write_text('a', encoding='utf-8')

    assert denygen.scan_heavy(str(proj)) == [
        ('Read(node_modules/**)', 'node_modules/ present, 2 entries'),
        ('Read(src/node_modules/**)', 'src/node_modules/ present, 1 entries'),
    ]


def test_heavy_dir_reported_at_max_depth_and_not_one_below(tmp_path):
    proj = _proj(tmp_path)
    (proj / 'l1' / 'l2' / 'node_modules').mkdir(parents=True)
    (proj / 'l1' / 'l2' / 'node_modules' / 'x.js').write_text('x', encoding='utf-8')
    (proj / 'l1' / 'l2' / 'l3' / 'node_modules').mkdir(parents=True)
    (proj / 'l1' / 'l2' / 'l3' / 'node_modules' / 'y.js').write_text('y', encoding='utf-8')

    pats = [p for p, _ in denygen.scan_heavy(str(proj))]
    assert pats == ['Read(l1/l2/node_modules/**)']


def test_unreadable_subdir_is_skipped_and_siblings_still_scanned(monkeypatch, tmp_path):
    proj = _proj(tmp_path)
    (proj / 'locked' / 'node_modules').mkdir(parents=True)
    (proj / 'ok' / 'node_modules').mkdir(parents=True)

    real_scandir = os.scandir

    def flaky_scandir(path='.', *a, **k):
        if os.path.basename(os.fspath(path)) == 'locked':
            raise OSError('denied')
        return real_scandir(path, *a, **k)

    monkeypatch.setattr(os, 'scandir', flaky_scandir)

    assert [p for p, _ in denygen.scan_heavy(str(proj))] == ['Read(ok/node_modules/**)']


def test_lock_file_reports_size_floored_to_kb_and_unreadable_size_as_zero(monkeypatch, tmp_path):
    proj = _proj(tmp_path)
    (proj / 'package-lock.json').write_bytes(b'x' * 2600)
    (proj / 'sub').mkdir()
    (proj / 'sub' / 'yarn.lock').write_bytes(b'y' * 10)

    real_getsize = os.path.getsize

    def flaky_getsize(path):
        if os.path.basename(os.fspath(path)) == 'yarn.lock':
            raise OSError('gone')
        return real_getsize(path)

    monkeypatch.setattr(os.path, 'getsize', flaky_getsize)

    assert dict(denygen.scan_heavy(str(proj))) == {
        'Read(**/package-lock.json)': 'package-lock.json present, 2 KB',
        'Read(**/yarn.lock)': 'sub/yarn.lock present, 0 KB',
    }


def test_merge_deny_keeps_existing_order_and_appends_only_new(tmp_path):
    proj = _proj(tmp_path)
    _write_settings(proj, '{"permissions":{"deny":["Read(.env)","Read(z/**)"]}}')

    added, existed = denygen.merge_deny(
        str(proj), ['Read(a/**)', 'Read(z/**)', 'Read(b/**)'])

    assert (added, existed) == (2, 1)
    deny = json.loads(_settings(proj).read_text(encoding='utf-8'))['permissions']['deny']
    assert deny == ['Read(.env)', 'Read(z/**)', 'Read(a/**)', 'Read(b/**)']


def test_merge_deny_all_present_leaves_bytes_unchanged(tmp_path):
    proj = _proj(tmp_path)
    sp = _write_settings(proj, '{"permissions":{"deny":["Read(a/**)","Read(b/**)"]}}')
    before = sp.read_bytes()

    assert denygen.merge_deny(str(proj), ['Read(a/**)', 'Read(b/**)']) == (0, 2)
    assert sp.read_bytes() == before


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/denygen.py:82-83 swallows the parse error, and :96 writes "
    "over the malformed file, so its user content is lost"))
def test_merge_deny_refuses_malformed_settings_and_keeps_content(tmp_path):
    proj = _proj(tmp_path)
    raw = '{"permissions": {"deny": ["Read(.env)"], "allow": ["Bash(git:*)"]'
    sp = _write_settings(proj, raw)

    denygen.merge_deny(str(proj), ['Read(node_modules/**)'])

    assert sp.read_bytes() == raw.encode('utf-8')


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/denygen.py:86-87 replaces a non-list permissions.deny with [] "
    "and writes instead of refusing"))
def test_merge_deny_refuses_non_list_deny_value(tmp_path):
    proj = _proj(tmp_path)
    raw = '{"permissions":{"deny":"Read(.env)"}}'
    sp = _write_settings(proj, raw)

    denygen.merge_deny(str(proj), ['Read(node_modules/**)'])

    assert sp.read_bytes() == raw.encode('utf-8')


def test_screen_esc_or_declined_confirm_writes_nothing(monkeypatch, tmp_path):
    proj = _proj(tmp_path)
    (proj / 'node_modules').mkdir()

    calls = _screen(monkeypatch, [('esc',)])
    denygen.deny_rules_screen(str(proj), 'proj')
    assert calls['merge'] == [] and calls['confirm'] == 0

    calls = _screen(monkeypatch, [('enter',)], confirm_answer=False)
    denygen.deny_rules_screen(str(proj), 'proj')
    assert calls['confirm'] == 1
    assert calls['merge'] == [] and calls['flash'] == 0
    assert not _settings(proj).exists()


@pytest.mark.parametrize('leave', ['esc', 'enter'])
def test_screen_with_nothing_heavy_returns_on_esc_or_enter_without_merge(monkeypatch, tmp_path, leave):
    proj = _proj(tmp_path)
    (proj / 'src').mkdir()
    (proj / 'src' / 'app.py').write_text('code', encoding='utf-8')

    calls = _screen(monkeypatch, [('x',), (leave,)])
    denygen.deny_rules_screen(str(proj), 'proj')

    assert calls['merge'] == [] and calls['confirm'] == 0
    assert any('Nothing heavy' in line for line in calls['frames'][0])
    assert not _settings(proj).exists()
