"""A test may not start Claude, and a project folder one caused gets swept.

Ninety project folders named after pytest temp directories were sitting in the
real `~/.claude/projects` — listed back to the user in the project list, the
dashboard, usage and search — because opening the TUI sessions screen calls
`memory.spawn_background_worker`, which launches a DETACHED child that runs a
real `claude -p` memory extraction. `claude -p` writes a transcript into
`~/.claude/projects/<encoded cwd>` exactly like a session you had, so every
full run of this suite left one behind and spent a Claude call to do it.

Three things are gated here: the block (so nobody deletes the fixture and
reintroduces the spend), its NARROWNESS (blocking Popen outright took 50 tests
down, because `subprocess.run` is implemented in terms of it), and the sweep's
matcher (so it can never widen into something that deletes a real project).
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import _LEAKED_PROJECT, _starts_claude

PY = sys.executable


def test_no_test_can_start_claude():
    """The fixture is autouse, so this is what the whole suite runs under.
    Asserted through a real spawn attempt rather than by reading conftest: an
    `assert 'Popen' in source` would pass with the patch applied to the wrong
    module."""
    proc = subprocess.Popen(['claude', '-p', 'hello'])
    assert proc.returncode == 0 and proc.pid == -1, (
        'a test just started Claude — _no_test_starts_claude is not covering '
        'this run, and a detached child can outlive the suite')
    assert proc.communicate() == ('', '')


def test_the_block_lets_everything_else_through():
    """The half that 50 red tests bought: `subprocess.run` goes through Popen,
    and the hook and statusline suites run a real interpreter and read its real
    stdout — `test_the_glyphs_survive_a_pipe` cannot be written any other
    way."""
    out = subprocess.run([PY, '-c', 'print("hi")'],
                         capture_output=True, text=True)
    assert out.stdout.strip() == 'hi'


#: (argv, blocked) — what the guard has to tell apart.
ARGV = [
    (['claude', '-p', 'x'], True),
    ([r'C:\Users\me\.local\bin\claude.exe', '-p'], True),
    (['cmd', '/c', 'start', '', 'claude.cmd', '--continue'], True),
    # the detached memory worker: python, then the subcommand that ends in a
    # Claude call. This is the one that actually leaked.
    ([PY, '-m', 'claude_sessions', '--bg-scan', 'C:/p', 'C:/f'], True),
    ([PY, '-m', 'claude_sessions', '--failover-serve', '20129'], True),
    # …and the one that does NOT: the statusline never reaches Claude, which is
    # why __main__.py dispatches it before importing main.
    ([PY, '-m', 'claude_sessions', 'statusline'], False),
    ([PY, '-c', 'print(1)'], False),
    (['git', 'status', '--short'], False),
    (['npm', 'run', 'build'], False),
    ([], False),
]


@pytest.mark.parametrize('argv,blocked', ARGV)
def test_the_guard_tells_a_claude_spawn_from_every_other_spawn(argv, blocked):
    assert _starts_claude(argv) is blocked, argv


#: encoded project-folder names. The encoding maps every non-alphanumeric
#: character to '-', so a path keeps its shape and a pytest basetemp is
#: unmistakable inside one.
LEAKED = [
    'C--Users-mab-AppData-Local-Temp-pytest-of-mab-pytest-1794-test-export-writes-markdown1-work-proj',
    'C--Users-mab-AppData-Local-Temp-pytest-of-mab-pytest-1-t0-work-proj',
    '-tmp-pytest-of-runner-pytest-12-test-thing0-work-proj',      # POSIX shape
]
REAL = [
    'D--Claude',
    'D--repos',
    'C--Users-mab',
    'D--Lavoro-python-Scripts-Documentation',
    'D--work-pytest-of-plugins',        # names the words, not the shape
    'D--src-pytest-runner',
]


@pytest.mark.parametrize('name', LEAKED)
def test_the_sweep_recognises_a_leaked_project(name):
    assert _LEAKED_PROJECT.search(name), name


@pytest.mark.parametrize('name', REAL)
def test_the_sweep_leaves_a_real_project_alone(name):
    """The half that matters: this pattern is handed to `shutil.rmtree`. It
    requires BOTH halves of a pytest basetemp — `pytest-of-<user>` and a
    numbered `pytest-<n>` run directory — so a project that merely has the word
    in its path cannot match."""
    assert not _LEAKED_PROJECT.search(name), name
