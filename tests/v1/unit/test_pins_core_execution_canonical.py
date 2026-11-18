"""T-832: pins on the security-relevant conditions of `archeus/core/execution/canonical.py` that
the existing tests left free. Each test below states one condition of that module in both
directions (held and not held, or the exact value the module promises), so a mutant that loosens,
tightens or drops the condition fails on an assertion. The conditions already pinned elsewhere
are listed, with their covering test, in QWEN-DONE-T-832.md rather than repeated here."""

import os

import pytest

from archeus.core.execution import canonical as C
from archeus.core.execution.command_allowlist import Allowed
from archeus.core.policy import rules
from v1.unit.test_command_allowlist import CONTEXT


def bash(cmd, ctx=None):
    """The one action (or the unclassified pair) `canonicalise` gives this Bash command."""
    actions, unclassified = C.canonicalise('Bash', cmd, ctx or {})
    assert len(actions) == 1
    return actions[0], unclassified


def host_of_url(url):
    """The chip host an ordinary `curl <url>` call carries."""
    action, _ = bash('curl %s' % url, {})
    return action.chip_host


def tool_call(tool, tool_input, ctx=None):
    """The one action (or the unclassified pair) `canonicalise` gives this structured tool call."""
    actions, unclassified = C.canonicalise(tool, tool_input, ctx or {})
    assert len(actions) == 1
    return actions[0], unclassified


@pytest.mark.parametrize('refusal', (OSError, ValueError), ids=('oserror', 'valueerror'))
def test_a_path_the_os_refuses_to_resolve_is_one_unclassified_exec(tmp_path, monkeypatch, refusal):
    # `except (OSError, ValueError)` in `canonicalise`: realpath raises either, and the call is a
    # parse failure, never a crash and never an action carrying a path the OS refused to resolve.
    def refuse(path, *args, **kwargs):
        raise refusal('the os refuses this path')

    monkeypatch.setattr(os.path, 'realpath', refuse)
    for tool, tool_input in (('Read', {'file_path': 'file.txt'}),
                             ('Write', {'file_path': 'file.txt'}),
                             ('Bash', {'command': 'cat file.txt'})):
        actions, unclassified = C.canonicalise(tool, tool_input, {'workdir': str(tmp_path)})
        assert unclassified is True and [a.action_class for a in actions] == ['exec']
        assert actions[0].paths in (None, ('.',))


def test_a_relative_path_with_no_workdir_is_never_resolved_against_the_real_directory(tmp_path,
                                                                                       monkeypatch):
    # The no-workdir arm of `workspace_path`: without it a relative path would be resolved
    # against the process's own directory and reported as a path outside the workspace.
    monkeypatch.chdir(tmp_path)
    action, unclassified = tool_call('Read', {'file_path': 'src/a.py'}, {})
    assert (action.action_class, action.paths, unclassified) == ('read', ('src/a.py',), False)
    assert rules.inside(action.paths[0], '@workspace/**')


def test_a_name_that_only_begins_with_two_dots_stays_inside_the_workspace(tmp_path):
    # `rel.startswith(os.pardir + os.sep)`: the separator is what makes it an escape, and an
    # escape is named absolutely so that no rule can read it back into the workspace.
    ctx = {'workdir': str(tmp_path)}
    inside, _ = tool_call('Write', {'file_path': '..secret'}, ctx)
    outside, _ = tool_call('Write', {'file_path': '../outside'}, ctx)
    assert inside.paths == ('..secret',) and rules.inside(inside.paths[0], '@workspace/**')
    escaped = os.path.realpath(os.path.join(str(tmp_path), os.pardir, 'outside'))
    assert outside.paths == (escaped.replace('\\', '/'),)
    assert not rules.inside(outside.paths[0], '@workspace/**')


@pytest.mark.parametrize('cmd', (
    pytest.param('curl -Xget https://h.example/x', id='glued-lower'),
    pytest.param('curl -XGET https://h.example/x', id='glued-upper'),
    pytest.param('curl --request=get https://h.example/x', id='equals-lower'),
    pytest.param('curl --request=GET https://h.example/x', id='equals-upper'),
    pytest.param('curl https://h.example/x -X', id='method-option-last'),
))
def test_a_request_of_get_is_not_a_send_however_it_is_written(cmd):
    # The `-X`/`--request` arms of `_sends`: the method is compared upper-cased, and a method
    # option with nothing after it means GET.
    action, unclassified = bash(cmd, {})
    assert (action.action_class, action.host, unclassified) == ('web', 'h.example', False)


@pytest.mark.parametrize('cmd', (
    pytest.param('curl -XPUT https://h.example/x', id='glued'),
    pytest.param('curl --request=put https://h.example/x', id='equals'),
))
def test_a_request_of_anything_but_get_is_a_send(cmd):
    action, unclassified = bash(cmd, {})
    assert (action.action_class, unclassified) == ('external_comm', False)


def test_the_url_given_to_the_url_option_is_the_url_of_the_call():
    # The `--url` arm of `_url_arg`, which is the only way to name a url without repeating it.
    action, _ = bash('curl --url https://h.example/x', {})
    assert (action.action_class, action.host, action.chip_host) == ('web', 'h.example', 'h.example')
    dropped, _ = bash('curl --url', {})
    assert dropped.chip_host is None


def test_a_url_glued_to_a_value_flag_is_not_the_url_of_the_call():
    # `a[:2] in values`: `-ohttp://…` carries a filename, not the url the call is about.
    action, _ = bash('curl -ohttp://decoy.example/x https://h.example/x', {})
    assert (action.host, action.chip_host) == ('h.example', 'h.example')


@pytest.mark.parametrize('host,chip', (
    pytest.param('a' * 20 + '.example', 'a' * 20 + '.example', id='letters-20'),
    pytest.param('a' * 21 + '.example', '….example', id='letters-21'),
    pytest.param('ab1cd.example', '….example', id='mixed-5'),
    pytest.param('ab1c.example', 'ab1c.example', id='mixed-4'),
    pytest.param('1234567.example', '….example', id='digits-7'),
    pytest.param('123456.example', '123456.example', id='digits-6'),
))
def test_a_host_label_is_a_secret_only_past_its_length(host, chip):
    # The three length arms of `_token_like`: a long mixed label, a short mixed one that carries a
    # digit, and a pure-digit label longer than a port.
    assert host_of_url('https://%s/x' % host) == chip


def test_only_the_two_powershell_switches_that_run_code_hold_it():
    # `run not in PWSH_NOT_CODE`: `-CommandName` and `-ExecutionPolicy` begin with a code letter
    # but do not run code, and holding them would deny an ordinary scripted run.
    held, was = bash('pwsh -cRemove-Item x', {})
    assert was is True and held.action_class == 'exec'
    named, was_named = bash('pwsh -ConfigurationName session.x ./script.ps1', {})
    assert (named.action_class, was_named) == ('exec', False)


def test_a_node_module_hook_is_code_only_when_it_carries_a_data_url():
    # The second conjunct of the node arm of `_payload`: the hook option alone names a file.
    named, was_named = bash('node --import helper.mjs server.js', {})
    assert (named.action_class, was_named) == ('exec', False)
    _, was_inlined = bash('node --import data:text/javascript,globalThis.a=1 server.js', {})
    assert was_inlined is True


def test_a_one_letter_long_option_is_not_an_abbreviation_of_a_carrier():
    # `len(name) >= 2` in `_abbrev`: an exact match is held, an unresolvable prefix is not.
    named, was_named = bash('tar --u mytool -cf a b', {})
    assert (named.action_class, was_named) == ('exec', False)
    _, was_named_in_full = bash('tar --use-compress-program mytool -cf a b', {})
    assert was_named_in_full is True


@pytest.mark.parametrize('cmd', (
    pytest.param('mytool -rm x', id='dashed'),
    pytest.param('mytool --opt=cp x', id='assigned'),
))
def test_a_program_name_behind_a_dash_or_an_equals_still_names_a_command(cmd):
    # `piece.split('=')` and `part.lstrip('-')` in `_names_command`.
    _, unclassified = bash(cmd, {})
    assert unclassified is True


def test_a_value_that_is_not_a_program_name_names_no_command():
    _, unclassified = bash('mytool --opt=level src', {})
    assert unclassified is False


def test_base64_decoding_is_a_payload_and_reading_a_file_is_not():
    # `'--decode' in args`: the long form of `-d` runs the same payload.
    _, was_decoded = bash('base64 --decode f', {})
    assert was_decoded is True
    encoded, was_encoded = bash('base64 -w 0 f', {})
    assert (encoded.action_class, was_encoded) == ('exec', False)


def test_the_production_environment_is_named_whatever_the_case_of_the_flag():
    # `a.lower() in PROD`: the owner's release gate is the environment, not its spelling.
    raised, _ = bash('vercel --PROD', {})
    assert (raised.action_class, raised.environment) == ('deploy', 'prod')
    plain, _ = bash('vercel deploy', {})
    assert plain.environment is None


def test_a_push_to_a_remote_named_by_a_url_names_the_host_behind_it():
    # The `or host_of(remote)` of the push action: a remote the owner never configured still
    # says where the commits go.
    ctx = {'workdir': 'workspace', 'branch': 'archeus/m/t', 'remotes': {'origin': 'github.com'}}
    action, unclassified = bash('git push https://github.com/o/r.git main', ctx)
    assert (action.action_class, action.target, action.host, action.chip_host, unclassified) == (
        'git_push', 'https://github.com/o/r.git', 'github.com', 'github.com', False)


def test_a_pushed_ref_names_the_branch_it_lands_on():
    # `ref.split(':')[-1] or ref.split(':')[0]`: `<src>:<dst>` pushes onto <dst>, and a deletion
    # of a branch names that branch rather than nothing.
    ctx = {'workdir': 'workspace', 'branch': None, 'remotes': {}}
    onto, _ = bash('git push origin HEAD:main', ctx)
    assert onto.branch == 'main'
    deleted, _ = bash('git push origin main:', ctx)
    assert deleted.branch == 'main'


def test_a_push_that_names_nothing_takes_the_workspace_remote_and_branch():
    # The two defaults of the push action: `origin`, and the branch of the turn's context.
    ctx = {'workdir': 'workspace', 'branch': 'archeus/m/t', 'remotes': {'origin': 'github.com'}}
    action, unclassified = bash('git push', ctx)
    assert (action.action_class, action.target, action.host, action.branch, unclassified) == (
        'git_push', 'origin', 'github.com', 'archeus/m/t', False)


def test_a_held_risk_is_named_by_the_program_and_subcommand_the_table_holds():
    # The `target` of `risk_action`: a held `git push` is the subcommand the owner approves, not
    # the program, and `argv` carries the whole command plus the tool name.
    (actions, unclassified), _ = C.canonicalise_hook('Bash', 'git push value', {'workdir': 'ws'})
    assert unclassified is False and len(actions) == 1
    assert (actions[0].action_class, actions[0].target) == ('git_push', 'git push')
    (plain, _), _ = C.canonicalise_hook('Bash', 'rm file.txt', {'workdir': 'ws'})
    assert (plain[0].action_class, plain[0].target, plain[0].argv) == (
        'destructive', 'rm', ('rm file.txt', 'Bash'))


def test_an_allowed_command_carries_its_scanned_argv_its_workspace_paths_and_its_git_target(
        tmp_path):
    # The `Allowed` arm of `canonicalise_hook`: argv is what the shell would run, paths are the
    # row's operands resolved into the workspace (falling back to cwd, then workdir), and a git
    # row is named by program plus subcommand so a rule can match it.
    ctx = {'workdir': str(tmp_path), 'cwd': str(tmp_path / 'sub'), 'branch': 'archeus/m/t'}
    (actions, unclassified), result = C.canonicalise_hook('Bash', 'git --no-pager status', ctx,
                                                          CONTEXT)
    assert isinstance(result, Allowed) and unclassified is False
    action, = actions
    assert (action.action_class, action.target, action.argv, action.paths, action.branch) == (
        ('read', 'git status', ('git', '--no-pager', 'status'), ('sub',), 'archeus/m/t'))
    (bare, _), _ = C.canonicalise_hook('Bash', 'pwd', {'workdir': str(tmp_path)}, CONTEXT)
    assert bare[0].paths == ('.',)


def test_a_command_of_exactly_the_stored_maximum_is_stored_whole():
    # `len(cmd) <= MAX_STORED_COMMAND`: the boundary itself is still the command the owner saw,
    # and one over it is the digest that binds it.
    exact = 'x' * C.MAX_STORED_COMMAND
    (actions, unclassified), _ = C.canonicalise_hook('Bash', exact, {'workdir': 'ws'})
    assert unclassified is True and actions[0].argv == (exact, 'Bash')
    (over, _), _ = C.canonicalise_hook('Bash', exact + 'y', {'workdir': 'ws'})
    assert over[0].argv[:1] == ('str',) and over[0].argv[3] == 'Bash' and len(over[0].argv) == 4


def test_a_read_that_names_no_path_is_pinned_to_the_workspace():
    # `got or ('.',)` in `_paths`: an option-only invocation still reads the workspace, and the
    # approval must say so.
    action, unclassified = bash('ls -la', {'workdir': 'workspace'})
    assert (action.action_class, action.paths, unclassified) == ('read', ('.',), False)


def test_a_command_that_is_not_a_carrier_is_pinned_to_the_workspace():
    # The `paths=('.',)` of the final plain-exec return: a program this module does not know is
    # still run in the workspace, so it is never an action without a path.
    action, unclassified = bash('zqxxp --level 3', {'workdir': 'workspace'})
    assert (action.action_class, action.target, action.paths, unclassified) == (
        'exec', 'zqxxp', ('.',), False)
