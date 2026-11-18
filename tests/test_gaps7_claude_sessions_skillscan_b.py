"""T-1305: npm exec/x option handling and package precedence in claude_sessions/skillscan.py,
source lines 237-337 (_VALUE_OPTS, _verb_index, _package_command, _npx_unpinned).

Selected branches: 259-262 (value flag before the verb, bare boolean before the verb),
286-289 (`--` ends the option scan), 305-311 (--no-install, --no and --yes values),
312-314 (--yes value), 315-318 (value options at the end of the list), 326-329 (named
package wins over the positional and the call), 337 (pin and local classification).
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


@pytest.mark.parametrize('verb', ['exec', 'x'])
def test_exec_and_x_read_the_same_package_after_a_global_cache_value(verb, _no_privileged_side_effects):
    assert skillscan._package_command('npm', ['--cache', '/tmp', verb, 'evil']) == ('npm', 'evil', False)
    assert _flagged('npm', ['--cache', '/tmp', verb, 'evil'])
    assert skillscan._package_command('npm', ['--cache', '/tmp', verb, 'evil', '--no', 'true']) \
        == ('npm', 'evil', True)
    assert not _flagged('npm', ['--cache', '/tmp', verb, 'evil', '--no', 'true'])
    assert _no_privileged_side_effects == []


def test_npm_no_install_false_enables_the_fetch_while_npx_rewrites_the_same_flag(
        _no_privileged_side_effects):
    assert skillscan._package_command('npm', ['exec', '--no-install=false', 'evil']) == ('npm', 'evil', False)
    assert _flagged('npm', ['exec', '--no-install=false', 'evil'])
    assert skillscan._package_command('npm', ['exec', '--no-install=true', 'evil']) == ('npm', 'evil', True)
    assert not _flagged('npm', ['exec', '--no-install=true', 'evil'])
    assert not _flagged('npx', ['--no-install=false', 'evil'])
    assert _no_privileged_side_effects == []


def test_npm_no_install_with_an_unknown_equals_value_does_not_suppress():
    assert skillscan._package_command('npm', ['exec', '--no-install=garbage', 'evil']) == ('npm', 'evil', False)
    assert _flagged('npm', ['exec', '--no-install=garbage', 'evil'])


def test_a_yes_before_no_true_keeps_the_fetch_visible():
    assert skillscan._package_command('npm', ['exec', '--yes', '--no=true', 'evil']) == ('npm', 'evil', False)
    assert _flagged('npm', ['exec', '--yes', '--no=true', 'evil'])


def test_a_no_true_before_a_bare_yes_keeps_the_fetch_visible():
    assert skillscan._package_command('npm', ['exec', '--no=true', '--yes', 'evil']) == ('npm', 'evil', False)
    assert _flagged('npm', ['exec', '--no=true', '--yes', 'evil'])


def test_a_later_unsafe_named_package_is_selected_over_an_earlier_pin():
    args = ['exec', '--package=remote', '--package=pinned@1.2.3']
    assert skillscan._package_command('npm', args) == ('npm', 'remote', False)
    assert _flagged('npm', args)


def test_a_named_pin_takes_precedence_over_the_positional_package():
    args = ['exec', 'evil', '--package=safe@1.2.3']
    assert skillscan._package_command('npm', args) == ('npm', 'safe@1.2.3', False)
    assert _mcp('npm', args) == []


def test_a_dangling_package_flag_does_not_erase_an_earlier_unsafe_name():
    assert skillscan._package_command('npm', ['exec', '--package=evil', '-p']) == ('npm', 'evil', False)
    assert _flagged('npm', ['exec', '--package=evil', '-p'])


def test_a_value_option_at_the_end_never_invents_a_package(_no_privileged_side_effects):
    assert skillscan._package_command('npm', ['exec', 'safe@1.2.3', '--cache']) == ('npm', 'safe@1.2.3', False)
    assert skillscan._npx_unpinned(['npm', 'exec', 'safe@1.2.3', '--cache']) is False
    assert skillscan._package_command('npm', ['exec', '--cache']) == ('npm', None, False)
    assert skillscan._npx_unpinned(['npm', 'exec', '--cache']) is False
    assert _no_privileged_side_effects == []


def test_an_exact_pin_with_npm_x_options_is_not_a_finding_and_a_malformed_pin_is():
    assert skillscan._npx_unpinned(['npm', 'x', 'pkg@1.2.3', '--no-install']) is False
    assert skillscan._npx_unpinned(['npm', 'x', 'pkg@1.2.3-beta.1', '-y']) is False
    assert skillscan._npx_unpinned(['npm', 'x', 'pkg@1.2.3.4', '-y']) is True
