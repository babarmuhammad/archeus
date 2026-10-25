from dataclasses import replace

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities
from archeus.core.domain.actions import ACTION_CLASSES
from archeus.core.execution.command_allowlist import ROWS, Allowed, Held, classify
from v1.integration.test_execution import DONE, TOOL, _running, ended
from v1.integration.test_p21_activity import _current, x  # noqa: F401
from v1.integration.test_policy import task
from v1.unit.test_command_allowlist import CONTEXT, VECTORS


NEAR_MISSES = (
    'git --weird status',
    'pwd --help', 'ls -la .', 'cat - file.txt', 'head -n20 file.txt',
    'tail -f file.txt', 'wc -lc file.txt',
    'rg --no-config --fixed-strings --pre mytool -- word .',
    'git --no-pager status --sho',
    'git --no-pager diff --no-ext-diff --no-textconv --output=x',
    'git --no-pager log --max-count=20 --oneline --output=x',
    'git --no-pager show --no-ext-diff --no-textconv HEAD:x',
    'git --no-pager ls-files -- :/src',
    'git --no-pager rev-parse --show-top',
    'pytest -q -p myplugin tests', 'python -m other -q tests', 'node --version --import=x',
)


@pytest.fixture
def hook(x, monkeypatch, request):
    for cls in ACTION_CLASSES:
        x.rule('USER', cls, 'ALLOW')
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 30}]
    mid = x.ready(task('t1', *getattr(request, 'param', ('read', 'exec'))))
    e = _running(x, mid)
    token = 'hook_' + 'x' * 43

    def known_token(tx, actor):
        tx.update(entities.Execution, e.id, {'hook_token_hash': X.token_hash(token)}, actor=actor)
        X._event(tx, 'execution.hook', e, actor, {'seq': 0, 'decision': 'test', 'reason': ''})
    x.do(known_token)
    manager = x.manager
    pending, answers, evidence = [], [], [CONTEXT]
    monkeypatch.setattr(manager.node, 'pending_requests', lambda eid: list(pending))
    monkeypatch.setattr(manager.node, 'respond', lambda eid, seq, decision, reason:
                        answers.append({'decision': decision, 'reason': reason}))
    monkeypatch.setattr(manager, '_tail', lambda *args: None)

    def context(eid, workdir, cwd):
        assert eid == e.id and workdir == e.workdir
        assert cwd == e.workdir
        return evidence[0]
    monkeypatch.setattr(manager.node, 'command_context', context)

    def serve(command, *, mailbox_seq=None, **request_fields):
        seq = x.state(e.id).hook_seq + 1 if mailbox_seq is None else mailbox_seq
        request = dict(token=token, tool='Bash', input={'command': command})
        request.update(request_fields)
        pending[:] = [(seq, request)]
        assert manager._hooks(x.state(e.id), manager._procs[e.id], False)
        return answers[-1]
    return x, e, serve, evidence


@pytest.mark.parametrize('row_id,command', VECTORS)
def test_each_row_allows_through_manager_and_records_chip(hook, row_id, command):
    x, e, serve, evidence = hook
    result = classify(command, evidence[0])
    assert isinstance(result, Allowed) and result.row_id == row_id
    assert serve(command) == {'decision': 'allow', 'reason': ''}
    chip = _current(x, e.id)
    assert chip['decision'] == 'allow' and chip['action_class'] == result.action_class


@pytest.mark.parametrize('command', NEAR_MISSES)
def test_each_near_miss_holds_with_allow_all_classes_policy(hook, command):
    x, e, serve, evidence = hook
    assert isinstance(classify(command, evidence[0]), Held)
    assert serve(command) == {'decision': 'halt', 'reason': 'command form needs review'}
    assert _current(x, e.id) == {
        'action_class': 'exec', 'label': 'command', 'decision': 'halt', 'seq': 1}
    assert x.state(e.id).state == 'RUNNING'
    assert not [a for a in x.all(entities.Approval) if a.execution_id == e.id]
    decisions = [d for d in x.all(entities.PolicyDecision) if d.execution_id == e.id]
    assert any(d.stage == 'action' and d.decision == 'ALLOW' for d in decisions)


@pytest.mark.parametrize('command', (
    pytest.param('wget --post-data=x https://h.example/x', id='Z153'),
    pytest.param('curl --request=POST https://h.example/x', id='Z170'),
    pytest.param('curl -dx=1 https://h.example/x', id='Z171'),
    pytest.param('curl -XPOST https://h.example/x', id='Z172'),
    pytest.param('find . -delete', id='Z240'),
    pytest.param('git push -fu origin main', id='Z248'),
    pytest.param('git push origin +main', id='Z249'),
    pytest.param('git push --delete origin x', id='Z277'),
))
def test_redefined_write_send_forms_never_auto_allow(hook, command):
    x, e, serve, evidence = hook
    evidence[0] = replace(CONTEXT, programs=CONTEXT.programs | {command.split()[0]})
    assert serve(command)['decision'] in ('halt', 'deny')
    assert isinstance(classify(command, evidence[0]), Held)
    assert _current(x, e.id)['decision'] != 'allow'


@pytest.mark.parametrize('row_id,command', VECTORS)
def test_each_matched_row_still_obeys_policy_deny(hook, row_id, command):
    x, e, serve, evidence = hook
    result = classify(command, evidence[0])
    assert isinstance(result, Allowed) and result.row_id == row_id
    x.rule('MISSION', result.action_class, 'DENY', scope_ref=e.mission_id)
    assert serve(command)['decision'] == 'deny'
    assert _current(x, e.id)['decision'] == 'deny'


@pytest.mark.parametrize('command', [command for _, command in VECTORS])
def test_missing_profile_holds_every_row(hook, command):
    x, e, serve, evidence = hook
    evidence[0] = None
    assert serve(command) == {'decision': 'halt', 'reason': 'command form needs review'}


@pytest.mark.parametrize('command', (
    'git branch -{},D} x',
    "sed 's/" + r'\a' * 30 + "' f",
    'rm --rec build', 'git branch --del x', 'git ls-remote --u x ./nonexist',
    "sed --expr='e x' f", 'tar --rmt=mytool -cf h:a b', 'man -Hmytool f',
    'curl -sd x https://h.example/x', 'curl -sSF a=@b https://h.example/x',
    'curl -vXPOST https://h.example/x',
    'wget -e use_askpass=mytool https://h.example/x', 'npm pu',
))
def test_six_review_bypass_families_hold_through_manager(hook, command):
    x, e, serve, evidence = hook
    assert isinstance(classify(command, evidence[0]), Held)
    assert serve(command)['decision'] in ('halt', 'deny')
    assert not {'/', '@'} & set(_current(x, e.id)['label'])


@pytest.mark.parametrize('context,command', (
    (replace(CONTEXT, git_profile=False), 'git --no-pager status'),
    (replace(CONTEXT, programs=frozenset()), 'pwd'),
    (replace(CONTEXT, posix_shell=False), 'pwd'),
    (replace(CONTEXT, paths={}), 'cat file.txt'),
))
def test_missing_trusted_evidence_holds(hook, context, command):
    x, e, serve, evidence = hook
    evidence[0] = context
    assert serve(command)['decision'] == 'halt'


def test_request_cannot_attest_its_own_profile(hook):
    x, e, serve, evidence = hook
    evidence[0] = None
    assert serve('pwd', command_context=CONTEXT, row_id='A01')['decision'] == 'halt'


def test_held_input_still_obeys_deny_and_ask(hook):
    x, e, serve, evidence = hook
    x.rule('MISSION', 'exec', 'ASK', scope_ref=e.mission_id)
    assert serve('npm pu')['reason'].startswith('waiting for your approval')
    assert x.state(e.id).state == 'AWAITING_APPROVAL'


def test_matched_row_cannot_override_locked_floor(hook):
    x, e, serve, evidence = hook
    x.rule('USER', 'read', 'DENY', locked=True)
    x.rule('MISSION', 'read', 'ALLOW', scope_ref=e.mission_id)
    assert serve('pwd')['decision'] == 'deny'


def test_foreign_token_and_replay_cannot_replace_chip(hook):
    x, e, serve, evidence = hook
    assert serve('pwd')['decision'] == 'allow'
    before = _current(x, e.id)
    assert 'not this execution' in serve('node --version', token='foreign')['reason']
    assert _current(x, e.id) == before
    assert 'already answered' in serve('node --version', mailbox_seq=1)['reason']
    assert _current(x, e.id) == before


@pytest.mark.parametrize('row', ROWS, ids=lambda row: row.id)
def test_every_option_vector_and_operand_cardinality_through_hook(hook, row):
    x, e, serve, evidence = hook
    operands = {
        'none': ('',),
        'P*': ('', 'file.txt', 'file.txt tests'),
        'F+': ('file.txt', 'file.txt "two words.txt"'),
        'search': ('-- word file.txt', '-- word file.txt tests'),
        'optional_paths': ('', '-- file.txt', '-- file.txt tests'),
        'optional_head': ('', 'HEAD'),
        'head': ('HEAD',),
    }
    for options in row.options:
        for operand in operands[row.operands]:
            command = ' '.join((row.program, *row.prefix, *options, operand)).strip()
            result = classify(command, evidence[0])
            assert isinstance(result, Allowed) and result.row_id == row.id
            assert serve(command)['decision'] == 'allow', command


def test_held_input_still_obeys_policy_deny(hook):
    x, e, serve, evidence = hook
    x.rule('MISSION', 'exec', 'DENY', scope_ref=e.mission_id)
    assert serve('npm pu')['decision'] == 'deny'


@pytest.mark.parametrize('hook', [('read',)], indirect=True)
def test_matched_exec_still_obeys_task_contract(hook):
    x, e, serve, evidence = hook
    assert serve('node --version')['reason'].startswith('waiting for your approval')


def test_held_secret_never_reaches_chip_or_hook_event(hook):
    x, e, serve, evidence = hook
    assert serve('curl --pass hunter2.x https://h.example/x')['decision'] == 'halt'
    assert 'hunter2' not in str(_current(x, e.id))
    assert 'hunter2' not in str(x.events('execution.hook'))


@pytest.mark.parametrize('repeat', (False, True))
def test_approved_held_push_resumes_same_execution_once(x, repeat):
    command = 'git push origin main'
    assert isinstance(classify(command, CONTEXT), Held)
    x.scenarios['t1'] = [TOOL('Bash', command)] * (2 if repeat else 1) + [DONE]
    mid = x.ready_approved(task('t1', 'write_repo', 'git_push'))
    e = x.drive(mid, lambda: (x.exe(mission_id=mid) is not None
                              and x.exe(mission_id=mid).state == 'AWAITING_APPROVAL'
                              and x.exe(mission_id=mid)))
    approval = x.pending(mid)
    x.decide(approval)
    if repeat:
        x.drive(mid, lambda: (x.state(e.id).process_seq == 2
                              and x.state(e.id).state == 'AWAITING_APPROVAL'))
        next_approval = x.pending(mid)
        assert next_approval.id != approval.id
        assert next_approval.action_hash == approval.action_hash
        assert next_approval.state == 'PENDING'
        assert [ev['payload']['decision'] for ev in x.events('execution.hook')] == [
            'halt', 'allow', 'halt']
        x.decide(next_approval)
    x.drive(mid, ended(x, e.id))
    assert (x.state(e.id).state, x.state(e.id).process_seq) == (
        'ENDED_OK', 3 if repeat else 2)
    assert x.one(entities.Approval, id=approval.id).state == 'CONSUMED'
    if repeat:
        assert x.one(entities.Approval, id=next_approval.id).state == 'CONSUMED'
    else:
        assert [ev['payload']['decision'] for ev in x.events('execution.hook')] == [
            'halt', 'allow']


@pytest.mark.parametrize('allow_all', (False, True))
def test_destructive_held_command_denies_before_hold(x, allow_all):
    command = 'terraform destroy -auto-approve'
    assert isinstance(classify(command, CONTEXT), Held)
    if allow_all:
        for cls in ACTION_CLASSES:
            x.rule('USER', cls, 'ALLOW')
    x.scenarios['t1'] = [TOOL('Bash', command), DONE]
    mid = x.ready(task('t1', 'write_repo', 'exec'))
    e = x.drive(mid, lambda: x.exe(mission_id=mid))
    x.drive(mid, ended(x, e.id))
    assert x.state(e.id).state == 'ENDED_ERROR'
    assert [ev['payload']['decision'] for ev in x.events('execution.hook')] == ['deny']
    assert _current(x, e.id)['action_class'] == 'destructive'
    assert not [a for a in x.all(entities.Approval) if a.execution_id == e.id]


@pytest.mark.parametrize('tool,command', (
    ('Bash', 'Remove-Item -Recurse x'), ('PowerShell', 'Remove-Item -Recurse x'),
    ('PowerShell', 'ls'), ('bash', 'rm -rf x'), ('BASH', 'pwd'),
    ('pwsh', 'pwd'), ('pwsh.exe', 'pwd'), ('powershell.exe', 'pwd'),
    ('cmd', 'pwd'), ('cmd.exe', 'pwd'), ('conhost', 'pwd'),
    ('UnknownExecutor', 'rm -rf x'), ('UnknownExecutor', 'ls'),
))
def test_every_executor_miss_halts(hook, tool, command):
    x, e, serve, evidence = hook
    assert serve(command, tool=tool) == {
        'decision': 'halt', 'reason': 'command form needs review'}


@pytest.mark.parametrize('tool,tool_input', (
    ('Read', {'file_path': 'file.txt'}), ('Glob', {'pattern': '*'}),
    ('Grep', {'pattern': 'word'}), ('LS', {'path': '.'}),
    ('Write', {'file_path': 'file.txt'}), ('Edit', {'file_path': 'file.txt'}),
    ('MultiEdit', {'file_path': 'file.txt'}), ('NotebookEdit', {'notebook_path': 'file.txt'}),
    ('WebFetch', {'url': 'https://example.com'}), ('WebSearch', {'query': 'word'}),
))
@pytest.mark.parametrize('hook', [('read', 'exec', 'write_repo', 'web')], indirect=True)
def test_structured_tools_preserve_hook_behavior(hook, tool, tool_input):
    x, e, serve, evidence = hook
    assert serve(None, tool=tool, input=tool_input) == {'decision': 'allow', 'reason': ''}


@pytest.mark.parametrize('tool_input', ({'command': 'rm -rf x'}, {},
                                      {'file_path': 'file.txt', 'command': 'rm -rf x'}))
def test_structured_command_or_unclassified_is_held(hook, tool_input):
    x, e, serve, evidence = hook
    assert serve(tool_input.get('command'), tool='Read', input=tool_input)['decision'] == 'halt'


@pytest.mark.parametrize('field', ('command', 'cmd', 'script', 'commandLine'))
def test_unknown_command_fields_are_held(hook, field):
    x, e, serve, evidence = hook
    assert serve(None, tool='UnknownExecutor', input={field: 'rm -rf x'})['decision'] == 'halt'


@pytest.mark.parametrize('tool', ('Task', 'SendMessage', 'Monitor', 'ScheduleWakeup',
                                 'CronCreate', 'CronDelete', 'CronList', 'ToolSearch', 'Workflow'))
def test_named_nonexecutors_follow_policy(hook, tool):
    x, e, serve, evidence = hook
    assert serve('rm -rf x', tool=tool) == {'decision': 'allow', 'reason': ''}
    x.rule('MISSION', 'exec', 'DENY', scope_ref=e.mission_id)
    assert serve('rm -rf x', tool=tool)['decision'] == 'deny'


@pytest.mark.parametrize('tool', ('Bash', 'PowerShell', 'pwsh.exe', 'CMD'))
def test_an_executor_name_is_held_without_a_command_field(hook, tool):
    x, e, serve, evidence = hook
    assert serve(None, tool=tool, input={}) == {
        'decision': 'halt', 'reason': 'command form needs review'}
