import pytest

from archeus.core.execution import canonical as C
from archeus.core.execution.command_allowlist import Allowed, Held
from archeus.node.local import LocalNode
from v1.unit.test_command_allowlist import CONTEXT, VECTORS


@pytest.mark.parametrize('row_id,command', VECTORS)
def test_hook_uses_table_without_legacy_parser(monkeypatch, tmp_path, row_id, command):
    def forbidden(*args):
        pytest.fail('legacy command parser reached real hook')
    monkeypatch.setattr(C, 'command', forbidden)
    (actions, unclassified), result = C.canonicalise_hook(
        'Bash', {'command': command}, {'workdir': str(tmp_path)}, CONTEXT)
    assert isinstance(result, Allowed) and result.row_id == row_id
    assert not unclassified
    assert len(actions) == 1 and actions[0].action_class == result.action_class


@pytest.mark.parametrize('command', ['pwd', "sed 's/" + r'\a' * 30 + "' f"])
def test_missing_profile_holds_without_legacy_parser(monkeypatch, command):
    def forbidden(*args):
        pytest.fail('legacy command parser reached held input')
    monkeypatch.setattr(C, 'command', forbidden)
    (actions, unclassified), result = C.canonicalise_hook('Bash', command, {'workdir': '.'})
    assert isinstance(result, Held)
    assert unclassified and actions[0].action_class == 'exec'
    assert actions[0].argv == (command,) and actions[0].target == 'command'


def test_node_does_not_invent_profile():
    assert LocalNode.command_context(None, 'execution', 'workspace', 'cwd') is None


def test_typed_paths_are_relative_to_request_cwd(tmp_path):
    (actions, unclassified), result = C.canonicalise_hook(
        'Bash', 'rg --no-config --fixed-strings -- needle tests',
        {'workdir': str(tmp_path), 'cwd': str(tmp_path / 'sub')}, CONTEXT)
    assert isinstance(result, Allowed) and not unclassified
    assert actions[0].paths == ('sub/tests',)
    assert 'needle' not in actions[0].paths


def test_structured_tool_does_not_require_command_profile(tmp_path):
    ctx = {'workdir': str(tmp_path)}
    request = {'file_path': 'file.txt'}
    canon, result = C.canonicalise_hook('Read', request, ctx)
    assert result is None and canon == C.canonicalise('Read', request, ctx)


@pytest.mark.parametrize('command,cls', (
    *((program + ' file.txt', cls) for program, cls in C._HELD_PROGRAM_CLASSES.items()),
    *((program + ' ' + sub + ' value', cls)
      for (program, sub), cls in C._HELD_SUBCOMMAND_CLASSES.items()),
))
def test_held_risk_labels_never_call_legacy(monkeypatch, command, cls):
    def forbidden(*args):
        pytest.fail('legacy classifier reached HELD risk input')
    monkeypatch.setattr(C, 'canonicalise', forbidden)
    monkeypatch.setattr(C, '_norm', forbidden)
    (actions, unclassified), result = C.canonicalise_hook('Bash', command, {'workdir': '.'})
    assert isinstance(result, Held) and not unclassified
    assert len(actions) == 1 and actions[0].action_class == cls
    assert actions[0].argv == (command,)


@pytest.mark.parametrize('command', (
    'unknown destroy', 'terraform destroyer', 'terraform DESTROY',
    "terraform 'destroy'", 'git --no-pager push origin main', 'git pusher',
    'RM file', 'rm.exe file', '/bin/rm file', "'rm' file", 'g""it push',
    'env terraform destroy', 'terraform destroy; pwd',
))
def test_held_risk_lookup_is_exact(monkeypatch, command):
    def forbidden(*args):
        pytest.fail('legacy classifier reached unknown HELD input')
    monkeypatch.setattr(C, 'canonicalise', forbidden)
    (actions, unclassified), result = C.canonicalise_hook('Bash', command, {'workdir': '.'})
    assert isinstance(result, Held) and unclassified
    assert actions[0].action_class == 'exec' and actions[0].target == 'command'
    assert actions[0].argv == (command,)


@pytest.mark.parametrize('command', (
    "sed 's/" + r'\a' * 30 + "' f",
    "sed --expr='e x' f", 'git branch -{},D} x',
    'git push origin main; pwd', 'bash -c pwd', 'x' * 4097,
))
def test_adversarial_and_interpreter_held_inputs_skip_legacy(monkeypatch, command):
    def forbidden(*args):
        pytest.fail('unsafe legacy command parser reached')
    monkeypatch.setattr(C, 'command', forbidden)
    (actions, unclassified), result = C.canonicalise_hook('Bash', command, {'workdir': '.'})
    assert isinstance(result, Held) and unclassified
    assert actions[0].argv == (command,)


def test_unclassified_held_commands_have_distinct_approval_identity():
    first, _ = C.canonicalise_hook('Bash', 'mytool first', {'workdir': '.'})
    second, _ = C.canonicalise_hook('Bash', 'mytool second', {'workdir': '.'})
    assert first[0][0] != second[0][0]


@pytest.mark.parametrize('first,second', (
    (None, ['rm', '-rf', '/']), (['first'], ['second']),
    ({'command': 'first'}, {'command': 'second'}), (1, '1'), (1, True),
))
def test_non_string_commands_never_share_approval_identity(first, second):
    from archeus.core.domain.actions import action_hash, binding

    bind = binding(mission_id='mission', plan_id='plan', plan_version=1,
                   plan_digest='digest', task_id='task', task_key='t1', execution_id='execution')

    def identity(value):
        (actions, unclassified), result = C.canonicalise_hook(
            'Bash', {'command': value}, {'workdir': '.'})
        assert isinstance(result, Held) and unclassified
        return action_hash('action', bind, [a.canonical_dict() for a in actions])

    assert identity(first) != identity(second)
    assert identity(first) == identity(first)


def test_held_risk_approval_binds_raw_command():
    first, _ = C.canonicalise_hook('Bash', "git push 'origin' main", {'workdir': '.'})
    second, _ = C.canonicalise_hook('Bash', 'git push origin main', {'workdir': '.'})
    assert first[0][0].canonical() != second[0][0].canonical()


@pytest.mark.parametrize('url,host,chip', (
    pytest.param('https://hunter2.example/x', 'hunter2.example', '….example', id='Z150'),
    pytest.param('https://private_name.example/x', 'private_name.example', None, id='Z152'),
    pytest.param('h.example/x', 'h.example', None, id='Z173'),
    pytest.param('a.b', 'a.b', None, id='Z175'),
    pytest.param('https://user:pw@real.example/x', 'real.example', 'real.example', id='Z174'),
    pytest.param('a.b', 'a.b', None, id='Z188'),
    pytest.param('https://abcdefghijklmnopqrstu.example/x',
                 'abcdefghijklmnopqrstu.example', '….example', id='Z198'),
    pytest.param('https://hunter2.example/x', 'hunter2.example', '….example', id='Z199'),
    pytest.param('https://api.hunter2.example/x', 'api.hunter2.example', 'api.….example', id='Z200'),
    pytest.param('https://api.example.hunter2/x', 'api.example.hunter2', 'api.example.…', id='Z211'),
    pytest.param('https://12345678.example/x', '12345678.example', '….example', id='Z212'),
))
def test_structured_host_privacy(url, host, chip):
    from archeus.core.execution.command_allowlist import ROWS, classify

    assert {row.program for row in ROWS}.isdisjoint({'curl', 'wget'})
    for program in ('curl', 'wget'):
        assert isinstance(classify(program + ' ' + url, CONTEXT), Held)
    (actions, unclassified), eligibility = C.canonicalise_hook('WebFetch', {'url': url}, {})
    assert eligibility is None and not unclassified
    assert len(actions) == 1
    assert actions[0].host == host
    assert actions[0].chip_host == chip
