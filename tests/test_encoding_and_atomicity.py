"""Two invariants that every existing fixture in this suite was too ASCII and
too crash-free to exercise.

1. `subprocess.run(text=True)` with no `encoding=` decodes with the ANSI
   codepage on Windows (cp1252 here). One accented author name or emoji in a
   commit message raises INSIDE subprocess, and every caller wraps the call in a
   broad `except` that reports the whole feature as unavailable — so git status
   goes blank and the CLAUDE.md commit block silently empties.

2. The settings files archeus writes are parsed by Claude Code itself. A plain
   open(path,'w') that dies partway leaves truncated JSON and breaks the user's
   session, not just archeus.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import config as _c
from claude_sessions import repos, workspace

BRANCH = 'caffè-日本'
AUTHOR = 'Ünïcode Persön'
MESSAGE = 'add café ▕ support · €'


def _has_git():
    try:
        subprocess.run(['git', '--version'], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


@pytest.fixture
def wild_repo(tmp_path):
    """A real repo whose branch, author and commit subject are all non-ASCII."""
    if not _has_git():
        pytest.skip('git not installed')
    d = tmp_path / 'repo'
    d.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME=AUTHOR, GIT_AUTHOR_EMAIL='u@example.com',
               GIT_COMMITTER_NAME=AUTHOR, GIT_COMMITTER_EMAIL='u@example.com')
    (d / 'README.md').write_text('# wild\n', encoding='utf-8')
    for args in (['init', '-q'], ['checkout', '-q', '-b', BRANCH], ['add', '-A'],
                 ['commit', '-q', '-m', MESSAGE]):
        r = subprocess.run(['git', *args], cwd=str(d), capture_output=True,
                           env=env, encoding='utf-8', errors='ignore', timeout=30)
        if r.returncode != 0 and args[0] != 'checkout':
            pytest.skip('git setup failed: %s' % (r.stderr or '')[:120])
    return str(d)


def test_git_reads_survive_a_non_ascii_branch_and_author(wild_repo):
    assert repos._git(['log', '--oneline', '-1'], wild_repo) is not None
    assert BRANCH in (repos._git(['branch', '--show-current'], wild_repo) or '')
    assert 'café' in (repos._git(['log', '-1', '--format=%s'], wild_repo) or '')
    assert AUTHOR in (repos._git(['log', '-1', '--format=%an'], wild_repo) or '')


def test_workspace_still_recognises_the_repo(wild_repo):
    """This used to return ('','','') — read by the caller as 'not a repo'."""
    sha, short, branch = workspace._git_head(wild_repo)
    assert sha and len(short) == 7
    assert branch == BRANCH


def test_the_claude_md_commit_block_is_not_empty(wild_repo, monkeypatch, tmp_path):
    """The highest-impact instance: this text is injected into every session."""
    from claude_sessions import claude_md
    monkeypatch.setattr(claude_md, 'find_git_repos', lambda root, max_depth=2: [wild_repo])
    block = claude_md._build_autogen_block(wild_repo, None, commits=5)
    assert 'café' in block
    assert '```' in block                      # the commit fence actually rendered


# ── atomicity ────────────────────────────────────────────────

def test_write_atomic_leaves_no_temp_file(tmp_path):
    p = tmp_path / 'settings.json'
    assert _c.write_json_atomic(str(p), {'a': 1})
    assert json.loads(p.read_text(encoding='utf-8')) == {'a': 1}
    assert [f.name for f in tmp_path.iterdir()] == ['settings.json']


def test_a_failed_write_leaves_the_original_intact(tmp_path, monkeypatch):
    """The whole point: Claude Code parses this file. Half of it is worse than
    the old version of it."""
    p = tmp_path / 'settings.json'
    p.write_text(json.dumps({'hooks': {'Stop': []}, 'keep': 'me'}), encoding='utf-8')
    before = p.read_text(encoding='utf-8')

    real_replace = os.replace
    monkeypatch.setattr(os, 'replace',
                        lambda *a, **k: (_ for _ in ()).throw(OSError('disk full')))
    assert _c.write_json_atomic(str(p), {'clobbered': True}) is False
    monkeypatch.setattr(os, 'replace', real_replace)

    assert p.read_text(encoding='utf-8') == before
    assert json.loads(before)['keep'] == 'me'
    assert [f.name for f in tmp_path.iterdir()] == ['settings.json']   # temp cleaned up


def test_write_atomic_creates_missing_parents(tmp_path):
    p = tmp_path / 'a' / 'b' / '.claude' / 'settings.json'
    assert _c.write_json_atomic(str(p), {'ok': 1})
    assert p.is_file()


def test_no_settings_writer_bypasses_the_atomic_helper():
    """Policy. Five of these sites were written the plain way one at a time, and
    a sixth would be too if nothing held the line."""
    import ast
    import pathlib
    pkg = pathlib.Path(__file__).resolve().parent.parent / 'claude_sessions'
    offenders = []
    for f in sorted(pkg.glob('*.py')):
        tree = ast.parse(f.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'open'):
                continue
            mode = node.args[1].value if (len(node.args) > 1
                                          and isinstance(node.args[1], ast.Constant)) else ''
            if 'w' not in str(mode):
                continue
            src = ast.get_source_segment(f.read_text(encoding='utf-8'), node) or ''
            if 'settings' in src or 'settings' in f.stem:
                offenders.append(f'{f.name}:{node.lineno}')
    assert not offenders, 'settings written without write_atomic: %s' % offenders


def test_no_captured_subprocess_spawns_a_visible_console():
    """Policy, and it is a VISIBLE bug: on Windows every console child gets its
    own window unless CREATE_NO_WINDOW is passed. Opening the Repos or Tools tab
    runs git across a dozen repos, so the user watched a dozen black windows
    flash open and shut — while the output went to a pipe and the window showed
    nothing at all.

    Only CAPTURED spawns are covered. A spawn that deliberately shows a console
    (proc.spawn_terminal, the failover proxy's log window, launching claude
    itself) passes CREATE_NEW_CONSOLE and is exempt by that fact.
    """
    import ast
    import pathlib
    pkg = pathlib.Path(__file__).resolve().parent.parent / 'claude_sessions'
    offenders = []
    for f in sorted(pkg.glob('*.py')):
        src = f.read_text(encoding='utf-8')
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (fn.attr if isinstance(fn, ast.Attribute) else
                    fn.id if isinstance(fn, ast.Name) else '')
            if name not in ('run', 'Popen'):
                continue
            if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                    and fn.value.id == 'subprocess'):
                continue
            seg = ast.get_source_segment(src, node) or ''
            captured = ('capture_output' in seg or 'subprocess.PIPE' in seg
                        or 'DEVNULL' in seg)
            if not captured:
                continue                      # inherits our console on purpose
            if 'creationflags' in seg:
                continue                      # says what it wants, either way
            offenders.append(f'{f.name}:{node.lineno}')
    assert not offenders, (
        'captured subprocess with no creationflags (flashes a console on '
        'Windows): %s' % offenders)


def test_every_captured_spawn_goes_through_proc_run():
    """`proc.py` says it is the one place a subprocess starts, and that claim is
    what the test suite's stubs are built on: the endpoint floor patches
    `proc.run`, so a module calling `subprocess.run` directly runs the REAL
    binary during tests. `mcp.get_mcp_status` did exactly that — every endpoint
    test that touched MCP ran `claude mcp list` against the user's own account,
    which the conftest file-restore guard caught as damage to `~/.claude.json`.

    Exempt: `proc.py` itself, and a spawn that deliberately shows a console
    (those pass CREATE_NEW_CONSOLE and are covered by the test above).
    """
    import ast
    import pathlib
    pkg = pathlib.Path(__file__).resolve().parent.parent / 'claude_sessions'
    offenders = []
    for f in sorted(pkg.glob('*.py')):
        if f.name == 'proc.py':
            continue
        src = f.read_text(encoding='utf-8')
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            # `subprocess.run` only. A raw Popen is a STREAMING seam — the
            # cancellable job runner, the progress-bar reader, a detached
            # worker — and each of those is a deliberate thing proc.run cannot
            # express. A blocking captured `run` has no such excuse.
            if not (isinstance(fn, ast.Attribute) and fn.attr == 'run'
                    and isinstance(fn.value, ast.Name) and fn.value.id == 'subprocess'):
                continue
            offenders.append('%s:%d' % (f.name, node.lineno))
    assert not offenders, (
        'subprocess used directly instead of proc.run — the test stubs cannot '
        'see these, so they run for real: %s' % offenders)


def test_a_test_cannot_write_a_real_file_outside_the_temp_area():
    """The guard that exists because a run of this suite replaced the real
    ~/.claude/settings.json statusLine with the literal 'x' a test uses as a
    stand-in. conftest wraps the one helper every settings writer routes
    through; if that wrapper stops being armed, this passes silently and the
    next leak reaches the user's machine, so assert it bites."""
    import pytest
    from claude_sessions import config
    real = os.path.join(os.path.expanduser('~'), '.claude', 'settings.json')
    with pytest.raises(AssertionError, match='outside the pytest temp area'):
        config.write_atomic(real, '{}')
