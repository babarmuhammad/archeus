import json

import pytest

from claude_sessions import skillscan


def _mcp(command, args):
    return skillscan.lint(json.dumps({'mcpServers': {'s': {'command': command, 'args': args}}}))


def test_npm_exec_no_false_consumes_false_as_value_and_still_fetches_the_package():
    assert [f.rule for f in _mcp('npm', ['exec', '--no', 'false', 'evil'])] == ['mcp-command-exec']
    assert skillscan._package_command('npm', ['exec', '--no', 'false', 'evil']) == ('npm', 'evil', False)
    assert _mcp('npm', ['exec', '--no', 'false', 'safe@1.2.3']) == []
    assert skillscan._package_command('npm', ['exec', '--no', 'false', 'safe@1.2.3']) \
        == ('npm', 'safe@1.2.3', False)


def test_npm_cache_value_before_the_verb_keeps_boolean_values_out_of_the_verb_search():
    assert skillscan._package_command('npm', ['--cache', 'x', '--no', 'true', 'evil']) == ('npm', 'evil', True)
    assert _mcp('npm', ['--cache', 'x', '--no', 'true', 'evil']) == []
    assert [f.rule for f in _mcp('npm', ['--cache', 'x', '--no', 'false', 'evil'])] == ['mcp-command-exec']
    assert skillscan._package_command('npm', ['--cache', 'x', '--no', 'false', 'evil']) == ('npm', 'evil', False)
    assert skillscan._package_command('npm', ['--cache', '/tmp', 'x', '--no', 'true', 'evil']) \
        == ('npm', 'evil', True)


def test_npm_exec_yes_false_leaves_no_install_false_and_false_is_never_the_package():
    assert [f.rule for f in _mcp('npm', ['exec', '--yes', 'false', 'evil'])] == ['mcp-command-exec']
    assert skillscan._package_command('npm', ['exec', '--yes', 'false', 'evil']) == ('npm', 'evil', False)


def test_npm_exec_no_false_then_no_true_cannot_silently_suppress_the_affirmative():
    assert skillscan._package_command('npm', ['exec', '--no=false', '--no=true', 'evil']) \
        == ('npm', 'evil', False)
    assert [f.rule for f in _mcp('npm', ['exec', '--no=false', '--no=true', 'evil'])] == ['mcp-command-exec']


def test_npm_exec_yes_false_then_no_true_keeps_positional_and_suppresses():
    assert skillscan._package_command('npm', ['exec', 'evil', '--yes=false', '--no=true']) \
        == ('npm', 'evil', True)
    assert _mcp('npm', ['exec', 'evil', '--yes=false', '--no=true']) == []


def test_npm_exec_reverse_truthy_values_keep_the_fetch_unsuppressed():
    assert skillscan._package_command('npm', ['exec', 'evil', '--yes=true', '--no=false']) \
        == ('npm', 'evil', False)
    assert [f.rule for f in _mcp('npm', ['exec', 'evil', '--yes=true', '--no=false'])] == ['mcp-command-exec']


def test_npm_locates_the_verb_after_a_consumed_boolean_value_without_shifting_the_package():
    assert skillscan._package_command('npm', ['--yes', 'false', 'x', 'evil']) == ('npm', 'evil', False)
    assert [f.rule for f in _mcp('npm', ['--yes', 'false', 'x', 'evil'])] == ['mcp-command-exec']
    assert skillscan._package_command('npm', ['--no', 'true', 'exec', 'evil']) == ('npm', 'evil', False)
    assert [f.rule for f in _mcp('npm', ['--no', 'true', 'exec', 'evil'])] == ['mcp-command-exec']


def test_only_bare_lowercase_true_and_false_are_consumed_as_boolean_values():
    assert [f.rule for f in _mcp('npm', ['exec', '--yes', 'FALSE', 'evil'])] == ['mcp-command-exec']
    assert skillscan._package_command('npm', ['exec', '--yes', 'FALSE', 'evil']) == ('npm', 'FALSE', False)
    assert _mcp('npm', ['exec', '--no', 'FALSE', 'evil']) == []
    assert skillscan._package_command('npm', ['exec', '--no', 'FALSE', 'evil']) == ('npm', 'FALSE', True)


def test_npm_double_dash_makes_no_a_literal_package_and_boolean_tokens_inert():
    assert skillscan._package_command('npm', ['x', '--', '--no', 'true', 'evil']) == ('npm', '--no', False)
    assert [f.rule for f in _mcp('npm', ['x', '--', '--no', 'true', 'evil'])] == ['mcp-command-exec']


def test_npm_exec_no_true_with_yes_true_after_the_package_is_not_suppressed():
    assert skillscan._package_command('npm', ['exec', '--no=true', 'evil', '--yes=true']) \
        == ('npm', 'evil', False)
    assert [f.rule for f in _mcp('npm', ['exec', '--no=true', 'evil', '--yes=true'])] == ['mcp-command-exec']
    assert skillscan._package_command('npm', ['exec', '--no=true', 'evil', '--yes=false']) \
        == ('npm', 'evil', True)
    assert _mcp('npm', ['exec', '--no=true', 'evil', '--yes=false']) == []


@pytest.mark.parametrize('args', [
    ['--cache'],
    ['--no'],
    ['--yes', 'true'],
    ['--no', 'true', '--cache'],
    ['--loglevel', 'silent', 'evil'],
], ids=['value-option-eof', 'boolean-option-eof', 'boolean-pair-no-verb',
        'boolean-skip-then-value-eof', 'value-pair-then-bare-token'])
def test_truncated_npm_options_and_a_missing_verb_refuse_without_indexerror(args):
    assert skillscan._package_command('npm', args) == (None, None, False)
    assert _mcp('npm', args) == []


def test_bare_npm_exec_reports_no_package_without_indexerror():
    assert skillscan._package_command('npm', ['exec']) == ('npm', None, False)
    assert _mcp('npm', ['exec']) == []
