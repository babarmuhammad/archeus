import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import skillscan


@pytest.fixture(autouse=True)
def no_privileged_side_effects(monkeypatch):

    def _never(*args, **kwargs):
        raise AssertionError('the token parser must never run what it parses')

    import subprocess
    for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
        monkeypatch.setattr(subprocess, name, _never)
    for name in ('system', 'execv', 'execve', 'spawnv', 'spawnve'):
        monkeypatch.setattr(os, name, _never)


def _mcp(command, args):
    return skillscan.lint(json.dumps({'mcpServers': {'s': {'command': command, 'args': args}}}))


def _pkg(command, args):
    return skillscan._package_command(command, args)


def _refused(command, args):
    assert skillscan._npx_unpinned([command, *args]) is True
    f, = _mcp(command, args)
    assert (f.rule, f.severity, f.line) == ('mcp-command-exec', 'med', 1)
    assert f.reason == 'an MCP server that runs a shell wrapper or fetches an unpinned package'
    return f


def _allowed(command, args):
    assert skillscan._npx_unpinned([command, *args]) is False
    assert _mcp(command, args) == []


def test_a_bare_boolean_value_after_yes_is_the_value_and_evil_still_fetches():
    f = _refused('npm', ['exec', '--yes', 'false', 'evil'])
    assert f.match == 'npm exec --yes false evil'
    assert _pkg('npm', ['exec', '--yes', 'false', 'evil']) == ('npm', 'evil', False)
    f = _refused('npm', ['exec', '--yes=true', 'evil'])
    assert f.match == 'npm exec --yes=true evil'
    assert _pkg('npm', ['exec', '--yes=true', 'evil']) == ('npm', 'evil', False)
    _refused('npm', ['exec', '--yes', 'true', 'evil'])
    assert _pkg('npm', ['exec', '--yes', 'true', 'evil']) == ('npm', 'evil', False)
    _allowed('npm', ['exec', '--yes', 'false'])
    assert _pkg('npm', ['exec', '--yes', 'false']) == ('npm', None, False)
    _allowed('npm', ['exec', '--yes', 'true'])
    assert _pkg('npm', ['exec', '--yes', 'true']) == ('npm', None, False)


def test_the_no_flag_pair_suppresses_only_true_and_the_boundary_freezes_it():
    _allowed('npm', ['x', '--no=true', 'evil'])
    assert _pkg('npm', ['x', '--no=true', 'evil']) == ('npm', 'evil', True)
    f = _refused('npm', ['x', '--no=false', 'evil'])
    assert f.match == 'npm x --no=false evil'
    assert _pkg('npm', ['x', '--no=false', 'evil']) == ('npm', 'evil', False)
    _allowed('npm', ['x', '--no=true', '--', 'evil'])
    assert _pkg('npm', ['x', '--no=true', '--', 'evil']) == ('npm', 'evil', True)
    _refused('npm', ['x', '--no=false', '--', 'evil'])
    assert _pkg('npm', ['x', '--no=false', '--', 'evil']) == ('npm', 'evil', False)
    _allowed('npm', ['x', '--no', '--', 'evil'])
    assert _pkg('npm', ['x', '--no', '--', 'evil']) == ('npm', 'evil', True)
    _refused('npm', ['x', '--no-install', '--yes', 'evil'])
    assert _pkg('npm', ['x', '--no-install', '--yes', 'evil']) == ('npm', 'evil', False)


def test_the_first_unsafe_named_spec_wins_over_pins_locals_and_the_command():
    args = ['exec', '-p', 'safe@1.2.3', '-p', './tools/helper', '-p', 'eviltracer',
            '-p', 'other@1.2.3', '--', 'run']
    f = _refused('npm', args)
    assert f.match == 'npm ' + ' '.join(args)
    assert _pkg('npm', args) == ('npm', 'eviltracer', False)
    all_safe = ['exec', '-p', 'safe@1.2.3', '-p', './tools/helper', '-p', 'other@9.9.9', '--', 'run']
    _allowed('npm', all_safe)
    assert _pkg('npm', all_safe) == ('npm', 'safe@1.2.3', False)


def test_a_bare_package_option_after_a_pinned_sibling_selects_the_unpinned_spec():
    args = ['exec', '-p', 'good@1.2.3', '--package', 'other', '--', 'cmd']
    f = _refused('npm', args)
    assert f.match == 'npm ' + ' '.join(args)
    assert _pkg('npm', args) == ('npm', 'other', False)
    swapped = ['exec', '--package', 'other', '-p', 'good@1.2.3', '--', 'cmd']
    _refused('npm', swapped)
    assert _pkg('npm', swapped) == ('npm', 'other', False)


def test_call_text_is_the_package_until_a_named_package_outvotes_it():
    args = ['x', '-c', 'evil --x']
    f = _refused('npm', args)
    assert f.match == 'npm x -c evil --x'
    assert _pkg('npm', args) == ('npm', 'evil --x', False)
    overruled = ['x', '-c', 'evil --x', '-p', 'safe@1.2.3']
    _allowed('npm', overruled)
    assert _pkg('npm', overruled) == ('npm', 'safe@1.2.3', False)


def test_option_values_before_and_after_the_verb_are_never_the_package():
    attached = ['--cache', 'cache-dir', 'exec', '--registry=registry.invalid', 'evil']
    f = _refused('npm', attached)
    assert f.match == 'npm ' + ' '.join(attached)
    assert _pkg('npm', attached) == ('npm', 'evil', False)
    spaced = ['--cache', 'cache-dir', 'exec', '--registry', 'registry.invalid', 'evil']
    _refused('npm', spaced)
    assert _pkg('npm', spaced) == ('npm', 'evil', False)
    pinned = ['--cache', 'cache-dir', 'exec', '--registry=registry.invalid', 'pkg@1.2.3']
    _allowed('npm', pinned)
    assert _pkg('npm', pinned) == ('npm', 'pkg@1.2.3', False)


def test_everything_after_the_double_dash_is_payload_that_cannot_change_suppression():
    f = _refused('npm', ['exec', '--', 'evil', '--yes'])
    assert f.match == 'npm exec -- evil --yes'
    assert _pkg('npm', ['exec', '--', 'evil', '--yes']) == ('npm', 'evil', False)
    _allowed('npm', ['exec', '--no-install', '--', 'evil', '--yes'])
    assert _pkg('npm', ['exec', '--no-install', '--', 'evil', '--yes']) == ('npm', 'evil', True)
    _allowed('npm', ['exec', '--'])
    assert _pkg('npm', ['exec', '--']) == ('npm', None, False)


def test_npm_keeps_reading_flags_after_the_positional_where_yarn_stops():
    f = _refused('npm', ['exec', 'evil', '--package', 'other'])
    assert f.match == 'npm exec evil --package other'
    assert _pkg('npm', ['exec', 'evil', '--package', 'other']) == ('npm', 'other', False)
    f = _refused('yarn', ['dlx', 'evil', '--package', 'other'])
    assert f.match == 'yarn dlx evil --package other'
    assert _pkg('yarn', ['dlx', 'evil', '--package', 'other']) == ('yarn', 'evil', False)
    _allowed('yarn', ['dlx', 'safe@1.2.3', '--package=evil'])
    assert _pkg('yarn', ['dlx', 'safe@1.2.3', '--package=evil']) == ('yarn', 'safe@1.2.3', False)
    _refused('npm', ['exec', 'safe@1.2.3', '--package=evil'])
    assert _pkg('npm', ['exec', 'safe@1.2.3', '--package=evil']) == ('npm', 'evil', False)


def test_dlx_and_bun_x_fetch_behind_an_env_prefix_and_a_valued_option_but_yarn_add_does_not():
    f = _refused('env', ['FOO=1', 'pnpm', '--registry', 'https://example.invalid', 'dlx', 'evil'])
    assert f.match == 'env FOO=1 pnpm --registry https://example.invalid dlx evil'
    assert _pkg('env', ['FOO=1', 'pnpm', '--registry', 'https://example.invalid', 'dlx', 'evil']) \
        == ('pnpm', 'evil', False)
    _refused('FOO=1', ['BAR=2', 'yarn', '--cache', '/tmp', 'dlx', 'evil'])
    assert _pkg('FOO=1', ['BAR=2', 'yarn', '--cache', '/tmp', 'dlx', 'evil']) == ('yarn', 'evil', False)
    _refused('env', ['FOO=1', 'bun', '--loglevel', 'warn', 'x', 'evil'])
    assert _pkg('env', ['FOO=1', 'bun', '--loglevel', 'warn', 'x', 'evil']) == ('bun', 'evil', False)
    for command, args in [('env', ['FOO=1', 'yarn', 'add', 'evil']),
                          ('FOO=1', ['yarn', '--cache', '/tmp', 'add', 'evil']),
                          ('env', ['FOO=1', 'bun', '--loglevel', 'warn', 'add', 'evil'])]:
        _allowed(command, args)
        assert _pkg(command, args) == (None, None, False)


def test_a_suffixed_npm_still_needs_a_fetch_verb_after_a_global_value_option():
    f = _refused('npm.cmd', ['--loglevel', 'warn', 'x', 'evil'])
    assert f.match == 'npm.cmd --loglevel warn x evil'
    assert _pkg('npm.cmd', ['--loglevel', 'warn', 'x', 'evil']) == ('npm', 'evil', False)
    f = _refused('C:\\Program Files\\nodejs\\npm.CMD', ['--loglevel', 'warn', 'x', 'evil'])
    assert f.match == 'C:\\Program Files\\nodejs\\npm.CMD --loglevel warn x evil'
    assert _pkg('C:\\Program Files\\nodejs\\npm.CMD', ['--loglevel', 'warn', 'x', 'evil']) \
        == ('npm', 'evil', False)
    _refused('NPM.EXE', ['--cache', '/tmp', 'exec', 'evil'])
    assert _pkg('NPM.EXE', ['--cache', '/tmp', 'exec', 'evil']) == ('npm', 'evil', False)
    for command, args in [('npm.cmd', ['--loglevel', 'warn', 'install', 'evil']),
                          ('npm.exe', ['--cache', '/tmp', 'install', 'evil'])]:
        _allowed(command, args)
        assert _pkg(command, args) == (None, None, False)
