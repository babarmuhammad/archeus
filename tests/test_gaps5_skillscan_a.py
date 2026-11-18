import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import skillscan


def _mcp(command, args):
    return skillscan.lint(json.dumps({'mcpServers': {'s': {'command': command, 'args': args}}}))


def test_double_dash_after_env_ends_option_parsing_and_the_command_follows():
    assert [f.rule for f in _mcp('env', ['--', 'npx', 'evil'])] == ['mcp-command-exec']
    assert skillscan._no_env(['env', '--', 'npx', 'evil']) == ['npx', 'evil']
    assert skillscan._no_env(['env', '--', '-S', 'npx evil']) == ['-S', 'npx evil']
    assert _mcp('env', ['--', '-S', 'npx evil']) == []


@pytest.mark.parametrize('value_opt', [['-u', 'OLD'], ['--unset', 'OLD'],
                                       ['-C', '/tmp'], ['--chdir', '/tmp']])
def test_env_value_taking_options_skip_their_value_and_never_read_it_as_the_command(value_opt):
    assert [f.rule for f in _mcp('env', [*value_opt, 'npx', 'evil'])] == ['mcp-command-exec']
    assert skillscan._no_env(['env', *value_opt, 'npx', 'evil']) == ['npx', 'evil']
    assert _mcp('env', [value_opt[0], 'npx', 'evil']) == []
    assert skillscan._no_env(['env', value_opt[0], 'npx', 'evil']) == ['evil']


def test_stacked_assignment_and_env_prefixes_are_all_consumed():
    assert [f.rule for f in _mcp('FOO=1', ['env', 'BAR=2', 'npx', 'x'])] == ['mcp-command-exec']
    assert skillscan._no_env(['FOO=1', 'env', 'BAR=2', 'npx', 'x']) == ['npx', 'x']
    assert [f.rule for f in _mcp('FOO=1', ['env', 'env', 'BAR=2', 'npx', 'x'])] == ['mcp-command-exec']
    assert skillscan._no_env(['FOO=1', 'env', 'env', 'BAR=2', 'npx', 'x']) == ['npx', 'x']


def test_a_cmd_wrapper_behind_env_and_abbreviated_command_flags_are_wrappers_a_bare_shell_is_not():
    assert [f.rule for f in _mcp('env', ['cmd', '/c', 'x'])] == ['mcp-command-exec']
    assert [f.rule for f in _mcp('pwsh', ['-c', 'Write-Host hi'])] == ['mcp-command-exec']
    assert [f.rule for f in _mcp('pwsh', ['-enc', 'AAAA'])] == ['mcp-command-exec']
    assert _mcp('cmd', []) == []
    assert _mcp('pwsh', ['-NoProfile']) == []
    assert _mcp('pwsh', ['-cob', 'x']) == []


def test_a_bare_scope_and_a_single_build_identifier_are_pinned_versions():
    assert _mcp('npx', ['@scope/pkg@1.2.3']) == []
    assert _mcp('npx', ['pkg@1.2.3+build']) == []
    assert [f.rule for f in _mcp('npx', ['@scope/pkg@1.2'])] == ['mcp-command-exec']


def test_a_four_part_version_or_an_empty_build_is_not_pinned():
    assert [f.rule for f in _mcp('npx', ['pkg@1.2.3.4'])] == ['mcp-command-exec']
    assert [f.rule for f in _mcp('npx', ['pkg@1.2.3+'])] == ['mcp-command-exec']


def test_the_bare_parent_directory_is_a_local_path_not_a_package():
    assert _mcp('npx', ['..']) == []
    assert _mcp('npx', ['-y', '..']) == []


def test_env_split_string_with_a_missing_or_empty_value_splits_to_nothing_without_raising():
    assert skillscan._no_env(['env', '-S']) == []
    assert skillscan._no_env(['env', '-S', '']) == []
    assert skillscan._no_env(['env', '--split-string=']) == []
    assert _mcp('env', ['-S']) == [] and _mcp('env', ['-S', '']) == []
    assert _mcp('env', ['--split-string=']) == []
    assert skillscan._no_env(['env', '--split-string=', 'npx', 'evil']) == ['npx', 'evil']
    assert [f.rule for f in _mcp('env', ['--split-string=', 'npx', 'evil'])] == ['mcp-command-exec']
