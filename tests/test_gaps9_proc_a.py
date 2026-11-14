"""T-1353 · highest-risk test gaps in claude_sessions/proc.py 672-722.

Slice: `_spawn_posix` (672-722, including the keep_open wrapper at 693-696 and
the darwin branch at 698-706) at tip 10d688c0, read again in the worktree at
pv20-fx87e. Selected branches, ranked (denial first, then boundaries, then
error paths):

 1. 716-722 — no terminal found: the command is detached with start_new_session
    and a failed spawn returns (None, str) instead of raising.
 2. 693-696 — keep_open with empty argv: no `exec` wrapper; the login shell is
    the inner command.
 3. 696 — keep_open quotes every argv word with _quote before `; exec <shell>`;
    words with spaces, quotes or $ stay one word.
 4. 708-710 — a TERMINAL that is empty or not on PATH is skipped.
 5. 711-715 — a candidate whose Popen raises moves on to the next candidate.
 6. 699-706 — darwin: the script is built with _quote for cwd and inner and
    passed through _applescript_str; an osascript failure returns (None, str).
 7. 698 — cwd None falls back to os.getcwd() in the darwin script.
 8. 712-713 — the terminal invocation always uses start_new_session=True and the
    given env, never shell=True.
 9. 708 — the TERMINAL flag is '-e' and candidate order is TERMINAL first, then
    _POSIX_TERMINALS.
10. 690-693 — argv None falls back to the SHELL env value, then /bin/sh, as the
    command.

Seams: proc.subprocess.Popen is a recorder, shutil.which is a set lookup,
proc.sys is replaced so the platform is chosen by the test, os.getcwd is fixed,
and TERMINAL and SHELL are set through monkeypatch. No real terminal, no real
process, no claude, codex or pi.
"""

import os
import shlex
import shutil
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import proc


@pytest.fixture
def rig(monkeypatch):
    r = SimpleNamespace(spawned=[], raise_for=set(), present=set(),
                        sys=SimpleNamespace(platform='linux'))

    def fake_popen(argv, **kw):
        r.spawned.append((list(argv), kw))
        if argv[0] in r.raise_for:
            raise RuntimeError('spawn refused')
        return 'child'

    monkeypatch.setattr(proc.subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(shutil, 'which',
                        lambda name, *a, **k: name if name in r.present else None)
    monkeypatch.setattr(proc, 'sys', r.sys)
    monkeypatch.setattr(os, 'getcwd', lambda: '/synthetic/here')
    monkeypatch.delenv('TERMINAL', raising=False)
    monkeypatch.delenv('SHELL', raising=False)
    return r


def _spawn(argv, cwd='/synthetic/work', env=None, keep_open=False):
    return proc._spawn_posix(argv, cwd, env, 'title', keep_open)


def test_no_terminal_detaches_the_bare_command(rig):
    env = {'SYNTH': '1'}
    assert _spawn(['claude'], env=env) == ('child', '')
    assert rig.spawned == [(['claude'], {'cwd': '/synthetic/work', 'env': env,
                                         'start_new_session': True})]


def test_no_terminal_and_a_failed_spawn_returns_a_failure_not_a_raise(rig):
    rig.raise_for = {'claude'}
    assert _spawn(['claude']) == (None, 'spawn refused')
    assert len(rig.spawned) == 1


def test_keep_open_with_no_argv_runs_the_login_shell_without_exec(rig, monkeypatch):
    monkeypatch.setenv('SHELL', '/synthetic/sh')
    rig.present = {'xterm'}
    _spawn([], keep_open=True)
    assert rig.spawned[0][0] == ['xterm', '-e', '/synthetic/sh']


def test_keep_open_quotes_each_word_and_keeps_it_one_word(rig, monkeypatch):
    monkeypatch.setenv('SHELL', '/synthetic/sh')
    rig.present = {'xterm'}
    argv = ['claude', 'a b', "it's", '$HOME']
    _spawn(argv, keep_open=True)
    cmd = rig.spawned[0][0]
    assert cmd[:3] == ['xterm', '-e', '/synthetic/sh']
    script = cmd[4]
    assert script.endswith('; exec /synthetic/sh')
    assert shlex.split(script[:-len('; exec /synthetic/sh')]) == argv


@pytest.mark.parametrize('terminal', ['', 'no-such-terminal'])
def test_unusable_terminal_name_is_skipped(rig, monkeypatch, terminal):
    monkeypatch.setenv('TERMINAL', terminal)
    rig.present = {'xterm'}
    _spawn(['claude'])
    assert rig.spawned[0][0] == ['xterm', '-e', 'claude']
    assert all(argv[0] != 'no-such-terminal' for argv, _ in rig.spawned)


def test_a_candidate_that_fails_to_spawn_hands_over_to_the_next(rig, monkeypatch):
    monkeypatch.setenv('TERMINAL', 'alpha-term')
    rig.present = {'alpha-term', 'xterm'}
    rig.raise_for = {'alpha-term'}
    assert _spawn(['claude']) == ('child', '')
    assert [argv[0] for argv, _ in rig.spawned] == ['alpha-term', 'xterm']


def test_every_candidate_failing_falls_back_to_the_detached_command(rig):
    rig.present = {'xterm'}
    rig.raise_for = {'xterm'}
    assert _spawn(['claude']) == ('child', '')
    assert rig.spawned[-1] == (['claude'], {'cwd': '/synthetic/work', 'env': None,
                                           'start_new_session': True})


def test_darwin_builds_the_terminal_script_with_quoted_cwd_and_argv(rig):
    rig.sys.platform = 'darwin'
    env = {'SYNTH': '1'}
    assert _spawn(['claude', 'a b'], cwd='/synthetic/my dir', env=env) == ('child', '')
    assert rig.spawned == [(
        ['osascript', '-e',
         'tell application "Terminal" to do script '
         '"cd \'/synthetic/my dir\' && claude \'a b\'"'],
        {'env': env})]


def test_darwin_osascript_failure_returns_a_failure(rig):
    rig.sys.platform = 'darwin'
    rig.raise_for = {'osascript'}
    assert _spawn(['claude'], cwd='/synthetic/work') == (None, 'spawn refused')


def test_darwin_with_no_cwd_uses_the_process_directory(rig):
    rig.sys.platform = 'darwin'
    _spawn(['claude'], cwd=None)
    assert rig.spawned[0][0][2].endswith('do script "cd /synthetic/here && claude"')


def test_terminal_spawn_is_detached_with_the_given_env_and_no_shell(rig, monkeypatch):
    monkeypatch.setenv('TERMINAL', 'alpha-term')
    rig.present = {'alpha-term'}
    env = {'SYNTH': '1'}
    _spawn(['claude'], env=env)
    argv, kw = rig.spawned[0]
    assert isinstance(argv, list)
    assert kw == {'cwd': '/synthetic/work', 'env': env, 'start_new_session': True}
    assert kw['env'] is env


def test_terminal_name_is_tried_first_with_the_dash_e_flag(rig, monkeypatch):
    monkeypatch.setenv('TERMINAL', 'mygem')
    rig.present = {'mygem', 'konsole', 'xterm'}
    _spawn(['claude'])
    assert rig.spawned[0][0] == ['mygem', '-e', 'claude']


def test_posix_candidates_are_tried_in_list_order(rig):
    rig.present = {'xterm', 'konsole', 'gnome-terminal'}
    _spawn(['claude'])
    assert rig.spawned[0][0] == ['gnome-terminal', '--', 'claude']


@pytest.mark.parametrize('shell, expected', [('/synthetic/sh', '/synthetic/sh'),
                                             ('', '/bin/sh')])
def test_no_argv_runs_the_shell_from_the_environment(rig, monkeypatch, shell, expected):
    monkeypatch.setenv('SHELL', shell)
    _spawn(None)
    assert rig.spawned[0][0] == [expected]
