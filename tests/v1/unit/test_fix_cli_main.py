"""Regression tests for hostile-audit findings on archeus/cli/main.py."""

import pytest

from archeus.cli import main


@pytest.mark.parametrize('scopes', ['', ',', ' ,'])
def test_an_empty_scope_selection_is_refused_not_widened_to_every_pairing_scope(
        scopes, monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(main, '_running', lambda: {'port': 1})
    monkeypatch.setattr(main, '_get', lambda *a, **k: sent.append(a) or {})
    assert main.pair({'scopes': scopes}) == 2
    assert sent == [] and 'scopes' in capsys.readouterr().err


@pytest.mark.parametrize('answer', [ValueError('not JSON'), None, {}])
def test_an_answer_that_is_not_cores_does_not_skip_the_local_emergency_stop(
        answer, monkeypatch, capsys):
    from archeus.cli.tui import client
    from archeus.infra import discovery
    from archeus.node.local import LocalNode

    def post(self, path, body):
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', {'port': 1}))
    monkeypatch.setattr(discovery, 'read_local_token', lambda: 'tok')
    monkeypatch.setattr(client.Core, 'post', post)
    stopped = []
    monkeypatch.setattr(LocalNode, 'estop_without_core',
                        staticmethod(lambda: stopped.append(1) or ([], None)))
    assert main.estop() == 0 and stopped == [1]


def test_a_registry_line_that_is_valid_json_but_not_an_object_does_not_stop_the_estop(
        archeus_home):
    import json
    import os

    from archeus.node.local import LocalNode, processes_registry
    spawn = {'op': 'spawn', 'execution_id': 'exe_1', 'process_seq': 1, 'pid': 1}
    os.makedirs(os.path.dirname(processes_registry()), exist_ok=True)
    with open(processes_registry(), 'w', encoding='utf-8') as f:
        f.write('null\n5\n"x"\n{"op": "end"}\n' + json.dumps(spawn) + '\n')
    assert LocalNode.unended() == [spawn]
