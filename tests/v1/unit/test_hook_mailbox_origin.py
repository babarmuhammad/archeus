"""K-O3 (T-058; T-053 pins P3 and P4): who may be answered through an execution's
hook mailbox, pinned on `serve_hook` as it stands. Every refusal here is a halt,
never a deny-and-continue, and nothing is ever allowed or approved.

Covered elsewhere and not repeated: a random foreign token halts (test_execution
E44), replay and reorder against a live process (E45), a request judged on the
state inside its transaction (test_execution_security S03), and a terminal
execution holds no credential (S06). These run in-process on a seeded database:
no harness, no process."""

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

TOKENS = {'a': 'hook_' + 'a' * 43, 'b': 'hook_' + 'b' * 43}
FOREIGN = "the request is not this execution's"


@pytest.fixture
def rig():
    """Two RUNNING executions, A and B, of one task, each holding its own hook
    token's digest as `prepare_process` records it (process 1, hook_seq 0)."""
    db = Database.open()
    who = Ref('user_device', ids.new_id('principal'))
    mid, pid, tid = (ids.new_id(k) for k in ('mission', 'plan', 'task'))
    eids = {k: ids.new_id('execution') for k in TOKENS}

    def seed(tx, **_):
        for row in (
                entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                 objective='o', state='EXECUTING'),
                entities.Plan(id=pid, mission_id=mid, state='APPROVED'),
                entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                              kind='code_change', state='RUNNING', max_attempts=2)):
            tx.insert(row, actor=who)
        for n, (k, eid) in enumerate(eids.items(), 1):
            tx.insert(entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                         attempt=n, state='RUNNING', process_seq=1,
                                         workdir='w', isolated=False,
                                         hook_token_hash=X.token_hash(TOKENS[k])), actor=who)
        tx.append(new_event('mission.updated', Ref('mission', mid), who, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(seed, {})
    yield db, who, eids
    db.close()


def _ask(db, eid, seq, token):
    return db.writer.execute(X.serve_hook, {
        'actor': Ref('system', ids.new_id('principal')), 'policy': None, 'execution_id': eid,
        'seq': seq, 'request': {'token': token, 'tool': 'Read'}, 'canon': ([], ()),
        'cwd_ok': True, 'branch_ok': True, 'disarmed': False})


def _e(db, eid):
    with db.read() as r:
        return rows.get(r, entities.Execution, eid).entity


def _forge(db, who, eid, fields):
    def put(tx, **_):
        tx.update(entities.Execution, eid, fields, actor=who)
        X._event(tx, 'execution.hook', rows.get(tx.conn, entities.Execution, eid).entity, who,
                 {'seq': None, 'decision': 'test', 'reason': 'forged by the test'})
    db.writer.execute(put, {})


def _nothing_approved(db):
    with db.read() as r:
        assert rows.where(r, entities.Approval) == []


def test_the_current_token_gets_past_the_mailbox_checks(rig):
    """Control: the seed has no dispatch decision, so the binding is the guard
    that halts it - after the seq and token checks let it through."""
    db, who, eids = rig
    out = _ask(db, eids['a'], 1, TOKENS['a'])
    assert out['decision'] == 'halt'
    assert out['reason'] != FOREIGN and 'already answered' not in out['reason']


def test_a_stale_process_token_halts_after_its_successor_is_prepared(rig):
    """P3: a later process gets a new digest (`prepare_process` records it and
    keeps hook_seq); the earlier process's token is foreign from then on, even
    on a sequence number the mailbox has never answered."""
    db, who, eids = rig
    old, new = TOKENS['a'], 'hook_' + 'n' * 43
    _forge(db, who, eids['a'], {'process_seq': 2, 'hook_token_hash': X.token_hash(new)})
    out = _ask(db, eids['a'], 1, old)
    assert (out['decision'], out['reason']) == ('halt', FOREIGN)
    assert _e(db, eids['a']).state == 'RUNNING'           # a halt is an answer, not a stop
    assert _ask(db, eids['a'], 2, new)['reason'] != FOREIGN
    _nothing_approved(db)


def test_another_executions_real_token_halts_this_one_and_leaves_its_owner_alone(rig):
    """P4: A's genuine token in B's mailbox. B halts and its sequence number is
    spent; A's mailbox, state and sequence are untouched."""
    db, who, eids = rig
    out = _ask(db, eids['b'], 1, TOKENS['a'])
    assert (out['decision'], out['reason']) == ('halt', FOREIGN)
    assert _e(db, eids['b']).hook_seq == 1
    a = _e(db, eids['a'])
    assert (a.state, a.hook_seq) == ('RUNNING', 0)
    assert _ask(db, eids['b'], 1, TOKENS['b'])['reason'] == 'request 1 was already answered'
    _nothing_approved(db)


def test_a_replayed_or_older_sequence_number_halts_without_moving_the_counter(rig):
    db, who, eids = rig
    _forge(db, who, eids['a'], {'hook_seq': 5})
    for seq in (5, 3, 0):
        out = _ask(db, eids['a'], seq, TOKENS['a'])
        assert (out['decision'], out['reason']) == ('halt', 'request %d was already answered'
                                                    % seq)
        assert _e(db, eids['a']).hook_seq == 5
    _nothing_approved(db)


def test_a_cleared_digest_answers_no_token_at_all(rig):
    """After the digest is cleared (every end path clears it) a RUNNING row is
    the worst case: even the token that matched before is foreign."""
    db, who, eids = rig
    _forge(db, who, eids['a'], {'hook_token_hash': None})
    for seq, tok in enumerate((TOKENS['a'], TOKENS['b'], '', None), 1):
        out = _ask(db, eids['a'], seq, tok)
        assert (out['decision'], out['reason']) == ('halt', FOREIGN)
    _nothing_approved(db)
