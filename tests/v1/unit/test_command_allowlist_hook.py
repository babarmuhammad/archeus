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


@pytest.mark.parametrize('command,classes', (
    ('git push origin main', ['git_push']),
    ('terraform destroy -auto-approve', ['destructive']),
    ('touch file.txt', ['write_repo']),
    ('curl -d body https://h.example/x', ['external_comm']),
))
def test_held_risk_classes_retain_legacy_policy_identity(command, classes):
    ctx = {'workdir': '.'}
    canon, result = C.canonicalise_hook('Bash', command, ctx)
    assert isinstance(result, Held)
    assert canon == C.canonicalise('Bash', command, ctx)
    assert not canon[1]
    assert [a.action_class for a in canon[0]] == classes


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
