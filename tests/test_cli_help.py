"""`archeus --help` answers, and it answers about the whole CLI.

A pip install is most people's first contact with this tool, and `--help` is the
only thing they can type without reading the docs. Two hazards, both guarded
here: it used to fall through to `run()` and START THE TUI (a released package
that opens a full-screen UI when asked for help is broken), and a hand-written
help text drifts from the dispatch table below it — the same rot that produced a
`docs/gui-audit.md` listing seventeen routes which never existed.

So the subcommands are enumerated from the SOURCE of `run()`, not from a list
kept here.
"""

import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import cli as cli_mod, main as main_mod

#: dispatches a user never types — archeus spawns these at itself. They stay
#: out of the help text on purpose; naming them here is what makes that a
#: decision instead of an omission.
INTERNAL = {'--bg-scan', '--failover-serve', '--gateway-serve', '--self-update',
            'statusline'}


def _is_argv(node):
    """`sys.argv[...]` — the only left-hand side a dispatch can have."""
    return (isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == 'argv')


def _dispatched():
    """Every command run() dispatches on: `sys.argv[1] == 'x'`,
    `sys.argv[1] in ('a','b')` and the `sys.argv[1:3] == ['workspace','status']`
    pair. Read off the source so the help text cannot fall behind it."""
    src = io.open(main_mod.__file__, encoding='utf-8').read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == 'run')
    found = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare) or not _is_argv(node.left):
            continue
        right = node.comparators[0]
        if isinstance(right, ast.Constant) and isinstance(right.value, str):
            found.add(right.value)
        elif isinstance(right, (ast.List, ast.Tuple, ast.Set)):
            parts = [e.value for e in right.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if not parts:
                continue
            # `== ['workspace','status']` is ONE command spelled in two words;
            # `in ('--help','-h')` is several spellings of one.
            if isinstance(node.ops[0], ast.In):
                found.update(parts)
            else:
                found.add(' '.join(parts))
    return found


def _run(monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, 'argv', ['archeus'] + argv)
    main_mod.run()
    return capsys.readouterr().out


@pytest.mark.parametrize('flag', ['--help', '-h', 'help'])
def test_help_prints_without_starting_a_ui(monkeypatch, capsys, flag):
    """render.screen_init() is what would take over the terminal — it is below
    the dispatch, so reaching it at all is the failure."""
    from claude_sessions import render
    monkeypatch.setattr(render, 'screen_init',
                        lambda *a, **k: pytest.fail('--help started the TUI'))
    out = _run(monkeypatch, capsys, [flag])
    assert 'archeus' in out and 'USAGE' in out
    assert 'COMMANDS' in out


def test_every_user_facing_subcommand_is_in_the_help(monkeypatch, capsys):
    missing = [c for c in _dispatched() - INTERNAL if c not in cli_mod.HELP]
    assert not missing, 'dispatches run() handles but --help never mentions: %s' % missing


def test_the_enumeration_still_finds_the_dispatch(monkeypatch):
    """The gate above is worthless if the walk stops matching the source shape."""
    found = _dispatched()
    assert {'workspace status', 'recall', 'review', '--help'} <= found, found


def test_version_prints_a_version(monkeypatch, capsys):
    out = _run(monkeypatch, capsys, ['--version'])
    assert out.strip(), 'no version printed'


def test_the_help_says_where_the_state_lives(monkeypatch, capsys):
    """The three questions support answers most often: which settings file, which
    config dir, where a project's memory is."""
    out = _run(monkeypatch, capsys, ['--help'])
    for expected in ('archeus.json', 'CLAUDE_CONFIG_DIR', '.archeus/memory'):
        assert expected in out, expected
