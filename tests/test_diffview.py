import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, ESC, ENTER

from claude_sessions import diffview, config


# ── pure helpers ─────────────────────────────────────────────

def test_unified_and_stat():
    old = "alpha\nbeta\ngamma\n"
    new = "alpha\nBETA\ngamma\ndelta\n"
    added, removed = diffview.stat(old, new)
    assert added == 2 and removed == 1            # +BETA +delta, -beta


def test_stat_no_change():
    assert diffview.stat("x\ny", "x\ny") == (0, 0)


def test_colorize_tags():
    lines = diffview.colorize(['@@ -1 +1 @@', '+added', '-removed', ' ctx',
                               '--- a (before)', '+++ b (after)'])
    joined = '\n'.join(lines)
    assert config.C_OK in [l for l in lines if 'added' in l][0]
    assert config.C_ERR in [l for l in lines if 'removed' in l][0]
    assert config.C_ACCENT in [l for l in lines if l.lstrip().startswith('\x1b') and '@@' in l][0]
    # context line untouched
    assert ' ctx' in lines


# ── snapshot store ───────────────────────────────────────────

def test_snapshot_roundtrip(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('repo')

    diffview.record(actual, folder, 'claude_md', 'v1\n', 'v2\nmore\n')
    assert diffview.load_prev(actual, folder, 'claude_md') == 'v1\n'
    lc = diffview.last_change(actual, folder, 'claude_md')
    assert lc and lc['added'] >= 1 and lc['key'] == 'claude_md'
    # snapshot lives in the project working dir
    assert os.path.isfile(os.path.join(actual, '.archeus', 'snapshots', 'claude_md.prev'))

    # second update overwrites .prev with the now-old version
    diffview.record(actual, folder, 'claude_md', 'v2\nmore\n', 'v3\n')
    assert diffview.load_prev(actual, folder, 'claude_md') == 'v2\nmore\n'


def test_last_change_none_when_absent(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('repo')
    assert diffview.last_change(actual, folder, 'system_prompt') is None
    assert diffview.load_prev(actual, folder, 'system_prompt') == ''


# ── display ──────────────────────────────────────────────────

def test_show_renders_changes(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    res, cap, _ = run_flow(monkeypatch, ESC, diffview.show,
                           "line1\nline2\n", "line1\nCHANGED\n", "CLAUDE.md")
    assert 'CHANGED' in cap.plain
    assert 'CLAUDE.md' in cap.plain


def test_show_no_changes(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    res, cap, _ = run_flow(monkeypatch, ESC, diffview.show,
                           "same\n", "same\n", "system prompt")
    assert 'no changes' in cap.plain.lower()


def test_confirm_approve(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    res, cap, _ = run_flow(monkeypatch, ENTER, diffview.confirm,
                           "old line\n", "new line\n", "CLAUDE.md")
    assert res is True
    assert 'REVIEW' in cap.plain


def test_confirm_reject(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    res, _, _ = run_flow(monkeypatch, ESC, diffview.confirm,
                         "old\n", "new\n", "CLAUDE.md")
    assert res is False


def test_confirm_toggle_full_then_approve(monkeypatch, tmp_path):
    from harness import typed
    Sandbox(monkeypatch, tmp_path)
    keys = typed('f') + ENTER          # toggle diff→full, then approve
    res, cap, _ = run_flow(monkeypatch, keys, diffview.confirm,
                           "old\n", "brand new text\n", "CLAUDE.md")
    assert res is True
    assert 'brand new text' in cap.plain


def test_confirm_first_creation_shows_full(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    # no old content → preview shows full proposed text; ENTER approves
    res, cap, _ = run_flow(monkeypatch, ENTER, diffview.confirm,
                           '', 'brand new content\n', 'CLAUDE.md')
    assert res is True
    assert 'brand new content' in cap.plain
