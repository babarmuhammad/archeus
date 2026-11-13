"""T-1306: non-npm launchers and verb discovery in claude_sessions/skillscan.py, source
lines 237-337 (_verb_index, _package_command for bunx, bun x, pnpm dlx, yarn dlx).

Selected branches: 254-258 (verb search stops at the first positional), 259-260 (value
flag directly before the verb), 261-262 (bare boolean skipped only for npm's known flags),
263 (no verb), 273-277 (launcher without a verb), 292-293 (non-npm launchers stop at the
first positional), 303-304 (bare boolean is a package token for non-npm launchers).
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


def test_bunx_bare_false_after_no_is_the_package_and_fails_closed():
    assert skillscan._package_command('bunx', ['--no', 'false', 'evil'])[1:] == ('false', False)
    assert _flagged('bunx', ['--no', 'false', 'evil'])


def test_bun_x_bare_true_after_no_yes_is_the_package_and_fails_closed():
    assert skillscan._package_command('bun', ['x', '--no-yes', 'true', 'evil'])[1:] == ('true', False)
    assert _flagged('bun', ['x', '--no-yes', 'true', 'evil'])


def test_pnpm_dlx_no_install_false_is_a_package_token_not_a_suppression():
    assert skillscan._package_command('pnpm', ['dlx', '--no-install', 'false', 'evil'])[1:] == ('false', False)
    assert _flagged('pnpm', ['dlx', '--no-install', 'false', 'evil'])


def test_yarn_dlx_yes_false_keeps_the_false_token_as_the_package(_no_privileged_side_effects):
    assert skillscan._package_command('yarn', ['dlx', '--yes', 'false', 'evil'])[1:] == ('false', False)
    assert _flagged('yarn', ['dlx', '--yes', 'false', 'evil'])
    assert _no_privileged_side_effects == []


def test_pnpm_workspace_value_flag_is_read_as_a_boolean_so_dlx_is_the_verb():
    assert skillscan._package_command('pnpm', ['-w', 'dlx', 'evil']) == ('pnpm', 'evil', False)
    assert _flagged('pnpm', ['-w', 'dlx', 'evil'])


def test_npm_cache_value_before_exec_is_the_verb_only_when_no_dir_is_given():
    assert skillscan._package_command('npm', ['--cache', 'exec']) == ('npm', None, False)
    assert _mcp('npm', ['--cache', 'exec']) == []
    assert skillscan._package_command('npm', ['--cache', '/tmp', 'exec', 'evil']) == ('npm', 'evil', False)
    assert _flagged('npm', ['--cache', '/tmp', 'exec', 'evil'])


def test_a_positional_before_the_verb_hides_a_later_verb_word():
    assert skillscan._package_command('npm', ['run', 'exec', 'evil']) == (None, None, False)
    assert _mcp('npm', ['run', 'exec', 'evil']) == []
    assert skillscan._package_command('pnpm', ['install', 'dlx', 'evil']) == (None, None, False)
    assert _mcp('pnpm', ['install', 'dlx', 'evil']) == []


def test_an_unknown_boolean_word_before_the_verb_is_a_positional_not_skipped():
    assert skillscan._package_command('pnpm', ['--silent', 'false', 'dlx', 'evil']) == (None, None, False)
    assert _mcp('pnpm', ['--silent', 'false', 'dlx', 'evil']) == []


@pytest.mark.parametrize('command, args, launcher', [
    ('pnpm', [], 'pnpm'), ('pnpm', ['-w'], 'pnpm'), ('yarn', ['dlx'], 'yarn'),
    ('bunx', [], 'bunx'), ('bun', ['x'], 'bun'),
])
def test_empty_or_dangling_launcher_arguments_have_no_package_and_no_index_error(command, args, launcher):
    result = skillscan._package_command(command, args)
    assert result[1] is None and result[2] is False
    assert result[0] in (None, launcher)
    assert _mcp(command, args) == []


@pytest.mark.parametrize('command, args', [
    ('pnpm', ['dlx', 'evil', '--no', 'true']),
    ('bunx', ['evil', '--no', 'true']),
    ('yarn', ['dlx', 'evil', '--no-install']),
    ('bun', ['x', 'evil', '--no', 'true']),
])
def test_non_npm_launchers_stop_at_the_first_positional_so_later_suppressions_do_not_apply(command, args):
    assert _flagged(command, args)
