"""T-1304: npx wrapper rewrites in claude_sessions/skillscan.py, source lines 266-337
(_package_command, _npx_unpinned).

Selected branches: 292-293 (npx stops at the first positional), 296-298 (npx drops the
token after --npm, -n, --node-arg), 299-302 (bare true/false after --no/--no-yes),
305-306 (--no-install rewritten whatever its value), 307-311 (--no/--no-yes/--no-install
with `=` values), 329-330 (package and no-install result).
"""
import json
import subprocess

import pytest

from claude_sessions import skillscan


def _mcp(command, args):
    return skillscan.lint(json.dumps({'mcpServers': {'s': {'command': command, 'args': args}}}))


def _flagged(command, args):
    return [f.rule for f in _mcp(command, args)] == ['mcp-command-exec']


@pytest.fixture(autouse=True)
def _no_privileged_side_effects(monkeypatch):
    spawned = []

    def _deny(*a, **k):
        spawned.append(a)
        raise AssertionError('skillscan token analysis must never spawn: %r' % (a,))

    for name in ('run', 'call', 'check_output', 'check_call', 'Popen'):
        monkeypatch.setattr(subprocess, name, _deny)
    yield spawned


@pytest.mark.parametrize('value', ['--no-install=true', '--no-install=garbage'])
def test_npx_no_install_with_any_value_suppresses_the_fetch(value, _no_privileged_side_effects):
    assert skillscan._package_command('npx', [value, 'evil']) == ('npx', 'evil', True)
    assert not _flagged('npx', [value, 'evil'])
    assert _no_privileged_side_effects == []


def test_npx_npm_option_with_nothing_after_it_leaves_no_package(_no_privileged_side_effects):
    assert skillscan._package_command('npx', ['--npm', 'evil']) == ('npx', None, False)
    assert _mcp('npx', ['--npm', 'evil']) == []
    assert _no_privileged_side_effects == []


def test_npx_npm_option_drops_one_token_and_the_next_positional_is_the_package():
    assert skillscan._package_command('npx', ['--npm', 'evil', 'tool']) == ('npx', 'tool', False)
    assert _flagged('npx', ['--npm', 'evil', 'tool'])
    assert not _flagged('npx', ['--npm', 'evil', 'tool@1.2.3'])


@pytest.mark.parametrize('option', ['--node-arg', '-n'])
def test_npx_node_arg_drops_a_following_flag_or_pin_so_the_real_package_stays_visible(option):
    assert skillscan._package_command('npx', [option, '--no-install', 'evil']) == ('npx', 'evil', False)
    assert _flagged('npx', [option, '--no-install', 'evil'])
    assert skillscan._package_command('npx', [option, 'safe@1.2.3', 'evil']) == ('npx', 'evil', False)
    assert _flagged('npx', [option, 'safe@1.2.3', 'evil'])


def test_npx_npm_option_with_an_equals_value_does_not_drop_the_next_token():
    assert skillscan._package_command('npx', ['--npm=x', '--no-install', 'evil']) == ('npx', 'evil', True)
    assert not _flagged('npx', ['--npm=x', '--no-install', 'evil'])
    assert _flagged('npx', ['--npm', '--no-install', 'evil'])


def test_npx_no_true_is_a_suppression_and_its_value_is_not_the_package():
    assert skillscan._package_command('npx', ['--no', 'true', 'evil']) == ('npx', 'evil', True)
    assert not _flagged('npx', ['--no', 'true', 'evil'])


def test_npx_no_yes_takes_a_bare_boolean_like_no_while_yes_stays_a_switch():
    assert skillscan._package_command('npx', ['--no-yes', 'true', 'evil']) == ('npx', 'evil', True)
    assert not _flagged('npx', ['--no-yes', 'true', 'evil'])
    assert skillscan._package_command('npx', ['--no-yes', 'false', 'evil']) == ('npx', 'evil', False)
    assert _flagged('npx', ['--no-yes', 'false', 'evil'])


@pytest.mark.parametrize('option', ['--no', '--no-yes'])
def test_npx_unknown_equals_value_for_no_does_not_suppress_the_fetch(option):
    assert skillscan._package_command('npx', [option + '=maybe', 'evil']) == ('npx', 'evil', False)
    assert _flagged('npx', [option + '=maybe', 'evil'])


def test_npx_flags_after_the_first_positional_are_argv_even_when_they_look_like_wrapper_options():
    assert skillscan._package_command('npx', ['evil', '--npm', 'x', '--no-install']) == ('npx', 'evil', False)
    assert _flagged('npx', ['evil', '--npm', 'x', '--no-install'])


def test_npx_node_arg_attached_value_does_not_drop_the_next_token():
    assert skillscan._package_command('npx', ['--node-arg=--no-install', 'evil']) == ('npx', 'evil', False)
    assert _flagged('npx', ['--node-arg=--no-install', 'evil'])
