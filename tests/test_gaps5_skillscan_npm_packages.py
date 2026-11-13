import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        raise AssertionError('skillscan token analysis must never spawn or exec: %r' % (a,))

    for name in ('run', 'call', 'check_output', 'check_call'):
        monkeypatch.setattr(subprocess, name, _deny)
    for name in ('system', 'execv', 'execve', 'execvp', 'spawnv'):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, _deny)
    yield spawned


def test_npm_dash_p_starved_at_the_end_stores_an_empty_value_without_exception(
        _no_privileged_side_effects):
    assert skillscan._package_command('npm', ['x', '-p']) == ('npm', '', False)
    assert _no_privileged_side_effects == []


@pytest.mark.xfail(strict=True, reason=(
    'defect at claude_sessions/skillscan.py:308/327: a -p at the end of the '
    'token list takes the empty-string default from next(iter(rest[i:i+1]), '
    "''), and _npx_unpinned then reads the empty package as 'no package', so "
    'the truncated fetch launcher `npm x -p` is silently accepted instead of '
    'refused fail-closed'))
def test_npm_x_dash_p_starved_at_the_end_is_refused_fail_closed():
    assert _flagged('npm', ['x', '-p'])
    assert skillscan._npx_unpinned(['npm', 'x', '-p']) is True


def test_a_named_pin_does_not_hide_an_unsafe_named_package_across_the_delimiter():
    args = ['exec', '--package=pinned@1.2.3', '--package=remote', '--', 'binary']
    assert skillscan._package_command('npm', args) == ('npm', 'remote', False)
    assert _flagged('npm', args)


def test_named_selection_picks_the_git_url_and_keeps_local_and_share_apart():
    url = 'git+https://example.invalid/evil/repo#semver@1.2.3'
    args = ['exec', '--package=@scope/tool@1.2.3', '--package=' + url]
    assert skillscan._package_command('npm', args) == ('npm', url, False)
    assert _flagged('npm', args)
    assert skillscan._package_command('npm', ['exec', '--package=./evil']) == ('npm', './evil', False)
    assert skillscan._npx_unpinned(['npm', 'exec', '--package=./evil']) is False
    share = '//host/share/evil'
    assert skillscan._package_command('npm', ['exec', '--package=./evil',
                                              '--package=' + share]) == ('npm', share, False)
    assert skillscan._npx_unpinned(['npm', 'exec', '--package=./evil',
                                    '--package=' + share]) is True


def test_option_values_around_the_verb_are_never_the_package_or_the_verb():
    attached = ['--registry', 'value', 'x', '--cache=cache', '-p', 'remote', 'binary']
    assert skillscan._package_command('npm', attached) == ('npm', 'remote', False)
    assert _flagged('npm', attached)
    spaced = ['--registry', 'value', 'x', '--cache', 'cache', '-p', 'remote', 'binary']
    assert skillscan._package_command('npm', spaced) == ('npm', 'remote', False)
    assert _flagged('npm', spaced)


@pytest.mark.parametrize('value_opt, verb', [('--cache', 'exec'), ('--userconfig', 'x')])
def test_a_value_flag_directly_before_the_verb_is_read_as_a_boolean_flag(value_opt, verb):
    # Real npm would take the verb as the option value; the scanner reads it
    # as a flag and finds the verb, which fails closed.
    args = [value_opt, verb, 'evil']
    assert skillscan._package_command('npm', args) == ('npm', 'evil', False)
    assert _flagged('npm', args)


@pytest.mark.parametrize('tokens, flagged', [
    (['npm', 'exec', 'evil'], True),
    (['npm', 'x', 'evil@latest'], True),
    (['npm', 'exec', 'pkg@1.2.3'], False),
    (['npm', 'exec', './local-tool'], False),
    (['npmfm', 'exec', 'evil'], False),
    (['npm', 'install', 'left-pad'], False),
    (['npm', 'run', 'build'], False),
    (['npm', '--cache', '/tmp', 'tool'], False),
    (['npm'], False),
    ([], False),
])
def test_npx_unpinned_end_to_end_for_npm_token_lists_only(tokens, flagged):
    assert skillscan._npx_unpinned(tokens) is flagged


def test_only_npm_rescans_named_packages_after_the_first_positional():
    seq = ['safe@1.2.3', '--package=evil']
    assert skillscan._package_command('npm', ['exec'] + seq) == ('npm', 'evil', False)
    assert _flagged('npm', ['exec'] + seq)
    for launcher in ('pnpm', 'yarn'):
        assert skillscan._package_command(launcher, ['dlx'] + seq) == (launcher, 'safe@1.2.3', False)
        assert _mcp(launcher, ['dlx'] + seq) == []


def test_a_named_package_owns_the_classification_and_the_call_is_not_the_fetch():
    args = ['exec', 'positional', '--call=remote', '--package=safe@1.2.3']
    assert skillscan._package_command('npm', args) == ('npm', 'safe@1.2.3', False)
    assert _mcp('npm', args) == []
    assert skillscan._package_command('npm', ['exec', 'positional', '--call=remote']) \
        == ('npm', 'remote', False)


def test_an_empty_call_is_not_no_call_and_no_package_and_runs_nothing(
        _no_privileged_side_effects):
    assert skillscan._package_command('npm', ['exec', '--call=', 'evil']) == ('npm', '', False)
    assert skillscan._npx_unpinned(['npm', 'exec', '--call=', 'evil']) is False
    assert skillscan._package_command('npm', ['exec', 'evil']) == ('npm', 'evil', False)
    assert skillscan._package_command('npm', ['exec', '--call', 'evil']) == ('npm', 'evil', False)
    assert skillscan._npx_unpinned(['npm', 'exec', '--call', 'evil']) is True
    assert skillscan._npx_unpinned(['npx', '-c', 'evil', '--no-install']) is True
    assert _no_privileged_side_effects == []


def test_the_double_dash_freezes_flags_so_an_earlier_named_pin_survives():
    args = ['exec', '-p', 'safe@1.2.3', '--', '--package=evil']
    assert skillscan._package_command('npm', args) == ('npm', 'safe@1.2.3', False)
    assert _mcp('npm', args) == []
