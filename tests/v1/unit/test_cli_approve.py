"""`archeus approve`: list, show, decide (T-840). No Core, no network: the
same fakes the other CLI tests use for `_running` and `_get`."""

import sys

import pytest

from archeus.cli import main as cli
from archeus.cli._api import endpoints
from archeus.cli.tui import sync

APPROVAL = {'id': 'apr_1', 'kind': 'plan', 'state': 'PENDING',
            'action_hash': 'af3ea' * 6 + 'ab', 'mission_id': 'msn_9', 'plan_id': 'pln_2',
            'presented': {'what': [{'class': 'write', 'target': 'src/a.py'},
                                   {'class': 'deploy', 'target': 'prod'}],
                          'why': 'the plan asks for write and deploy'},
            'expires_at': '2026-11-02T00:00:00Z', 'eligible': True, 'version': 3}


def _core(monkeypatch, *answers):
    """`_running` answers, and `_get` replays *answers* in order: a dict is
    Core's answer, a refusal dict is Core's refusal (the fake prints it in
    words exactly as the real `_get` does)."""
    got = []

    def fake(info, method, path, body=None, refusal=None):
        a = answers[len(got)] if len(got) < len(answers) else {}
        got.append((method, path, body))
        if 'code' in a:
            if refusal is not None:
                refusal.update(a)
            print(sync.explain(a), file=sys.stderr)
            return None
        return a

    monkeypatch.setattr(cli, '_running', lambda: {'port': 9001})
    monkeypatch.setattr(cli, '_get', fake)
    return got


# ── (1) the list ─────────────────────────────────────────────────────────────

def test_a_bare_approve_lists_the_pending_ones_with_what_they_would_do(monkeypatch, capsys):
    got = _core(monkeypatch, {'approvals': [dict(APPROVAL)]})
    assert cli.main(['approve']) == 0
    assert got == [('GET', endpoints.list_approvals(state='PENDING'), None)]
    out = capsys.readouterr().out
    assert 'apr_1' in out and 'plan' in out and 'msn_9' in out
    assert 'write src/a.py' in out and 'deploy prod' in out


def test_an_empty_list_says_so_and_still_exits_0(monkeypatch, capsys):
    _core(monkeypatch, {'approvals': []})
    assert cli.main(['approve']) == 0
    assert capsys.readouterr().out == 'nothing waits on you\n'


def test_a_list_Core_does_not_answer_is_exit_2(monkeypatch, capsys):
    _core(monkeypatch, {'code': 'network', 'status': 0, 'detail': {}})
    assert cli.main(['approve']) == 2
    assert 'could not be reached' in capsys.readouterr().err


# ── (2) the show: the human sees what they would approve ────────────────────

def test_approve_one_shows_it_with_the_action_hash(monkeypatch, capsys):
    got = _core(monkeypatch, dict(APPROVAL))
    assert cli.main(['approve', 'apr_1']) == 0
    assert got == [('GET', endpoints.get_approval('apr_1'), None)]
    out = capsys.readouterr().out
    assert 'action hash: %s' % APPROVAL['action_hash'] in out
    assert 'msn_9' in out and 'write src/a.py' in out


def test_an_unknown_approval_prints_Core_s_words_and_exits_2(monkeypatch, capsys):
    _core(monkeypatch, {'status': 404, 'code': 'not_found', 'detail': {}})
    assert cli.main(['approve', 'apr_gone']) == 2
    assert 'It no longer exists.' in capsys.readouterr().err


# ── (3) the decide: the hash the human saw goes back, echoed ────────────────

@pytest.mark.parametrize('verdict,decision,state',
                         [('allow', 'approve', 'APPROVED'), ('deny', 'reject', 'REJECTED')])
def test_a_decision_posts_what_Core_asked_for_and_nothing_else(monkeypatch, capsys,
                                                                verdict, decision, state):
    got = _core(monkeypatch, {'approval_id': 'apr_1', 'state': state,
                              'decision': decision, 'changed': True, 'version': 4})
    assert cli.main(['approve', 'apr_1', verdict, '--hash', APPROVAL['action_hash']]) == 0
    assert len(got) == 1
    method, path, body = got[0]
    assert method == 'POST' and path == endpoints.decide_approval('apr_1')
    assert body['decision'] == decision
    assert body['action_hash'] == APPROVAL['action_hash']
    assert body['note'] is None and body['idempotency_key']
    assert 'apr_1: %s' % state in capsys.readouterr().out


def test_the_note_travels_and_a_second_invocation_gets_a_fresh_key(monkeypatch):
    got = _core(monkeypatch, {'state': 'REJECTED'}, {'state': 'REJECTED'})
    assert cli.main(['approve', 'apr_1', 'deny', '--hash', 'h1', '--note', 'not this']) == 0
    assert cli.main(['approve', 'apr_1', 'deny', '--hash', 'h1', '--note', 'not this']) == 0
    assert got[0][2]['note'] == 'not this'
    assert got[0][2]['idempotency_key'] != got[1][2]['idempotency_key']


@pytest.mark.parametrize('argv', [['approve', 'apr_1', 'allow'],
                                  ['approve', 'apr_1', 'allow', '--note', 'n'],
                                  ['approve', 'apr_1', 'permit', '--hash', 'h'],
                                  ['approve', 'apr_1', 'allow', '--hash', '--note', 'n']])
def test_a_decision_without_its_hash_is_refused_here_and_Core_is_never_asked(
        argv, monkeypatch, capsys):
    monkeypatch.setattr(cli, '_running', lambda: pytest.fail('Core must not be asked'))
    monkeypatch.setattr(cli, '_get',
                        lambda *a, **k: pytest.fail('Core must not be asked'))
    assert cli.main(argv) == 2
    assert 'usage: archeus' in capsys.readouterr().err


def test_a_wrong_hash_is_Core_s_refusal_in_its_words_and_exit_1(monkeypatch, capsys):
    _core(monkeypatch, {'status': 422, 'code': 'guard_failed',
                        'detail': {'reason': 'the decision is for a different action',
                                   'guard': 'approve'}})
    assert cli.main(['approve', 'apr_1', 'allow', '--hash', 'not-the-one']) == 1
    assert 'the decision is for a different action' in capsys.readouterr().err


def test_a_policy_denied_423_prints_the_reason_and_exits_1(monkeypatch, capsys):
    _core(monkeypatch, {'status': 423, 'code': 'policy_denied',
                        'detail': {'reason': 'deploy is denied outside a window',
                                   'approval_id': 'apr_1'}})
    assert cli.main(['approve', 'apr_1', 'allow', '--hash', 'h1']) == 1
    err = capsys.readouterr().err
    assert 'deploy is denied outside a window' in err
    assert 'step-up' not in err


def test_a_step_up_answer_says_the_approval_belongs_to_the_app(monkeypatch, capsys):
    _core(monkeypatch, {'status': 422, 'code': 'guard_failed',
                        'detail': {'reason': 'this approval needs a valid step-up proof',
                                   'guard': 'approve'}})
    assert cli.main(['approve', 'apr_1', 'allow', '--hash', 'h1']) == 1
    assert 'needs the Archeus app' in capsys.readouterr().err


# ── Core down, and the deferred verb that is not deferred ───────────────────

def test_a_refusal_dict_also_holds_core_s_code_and_detail(monkeypatch, capsys):
    from archeus.cli.tui import client
    from archeus.infra import discovery
    monkeypatch.setattr(discovery, 'read_local_token', lambda: 'tok')

    def get(self, path):
        raise client.CoreError(422, 'guard_failed', {'reason': 'no', 'guard': 'approve'})
    monkeypatch.setattr(client.Core, 'get', get)
    refusal = {}
    assert cli._get({'port': 1}, 'GET', '/v1/approvals/apr_1', refusal=refusal) is None
    assert refusal['code'] == 'guard_failed' and refusal['status'] == 422
    assert refusal['detail']['reason'] == 'no'
    assert 'Refused: no' in capsys.readouterr().err


@pytest.mark.parametrize('argv', [['approve'], ['approve', 'apr_1'],
                                  ['approve', 'apr_1', 'allow', '--hash', 'h1']])
def test_every_form_says_Core_is_not_running_and_exits_1(argv, monkeypatch, capsys):
    def down():
        print('Core is not running: start it with `archeus core`', file=sys.stderr)
        return None
    monkeypatch.setattr(cli, '_running', down)
    monkeypatch.setattr(cli, '_get', lambda *a, **k: pytest.fail('Core must not be asked'))
    assert cli.main(argv) == 1
    assert 'Core is not running' in capsys.readouterr().err


def test_approve_is_no_longer_deferred_and_a_bare_approve_no_longer_exits_2(
        monkeypatch, capsys):
    assert 'approve' in cli.VERBS and 'approve' not in cli.DEFERRED
    _core(monkeypatch, {'approvals': []})
    assert cli.main(['approve']) == 0
    err = capsys.readouterr().err
    assert 'not available yet' not in err and 'arrives with' not in err
