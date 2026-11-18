
import dataclasses

import pytest

from archeus.core.application import authorization as A, lifecycle, optins
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.verification import worker
from archeus.infra.db import rows as rows_module

NOW = '2026-11-13T12:00:00+00:00'


class FakeRow:

    def __init__(self, entity, version=1, by='system', created_at=NOW):
        self.entity = entity
        self.version = version
        self.created_at = created_at
        self.updated_at = NOW
        self.created_by = self.updated_by = by


class FakeTx:

    def __init__(self):
        self.placed = {}
        self.calls = []
        self.events = []

    def place(self, entity, *, version=1, by='prn_' + '0' * 26, created_at=NOW):
        row = FakeRow(entity, version=version, by=by, created_at=created_at)
        self.placed.setdefault(type(entity), []).append(row)
        return row

    def ops(self):
        return [c[0] for c in self.calls]

    def find_calls(self):
        return [c[2] for c in self.calls if c[0] == 'where']

    def inserts(self):
        return [c[3] for c in self.calls if c[0] == 'insert']

    def updates(self):
        return [c for c in self.calls if c[0] == 'update']

    def _lookup(self, cls, entity_id):
        for row in self.placed.get(cls, ()):
            if row.entity.id == entity_id:
                return row
        return None

    def get(self, cls, entity_id):
        self.calls.append(('get', cls, entity_id))
        return self._lookup(cls, entity_id)

    def where(self, cls, **eq):
        self.calls.append(('where', cls, dict(eq)))
        return [r for r in self.placed.get(cls, ())
                if all(getattr(r.entity, k, None) == v for k, v in eq.items())]

    def insert(self, entity, *, actor):
        _principal(actor, 'created_by')
        self.calls.append(('insert', type(entity), entity.id, entity, actor))
        return self.place(entity, by=actor.id)

    def update(self, cls, entity_id, fields, *, actor, expected_version=None):
        _principal(actor, 'updated_by')
        self.calls.append(('update', cls, entity_id, dict(fields), actor, expected_version))
        row = self._lookup(cls, entity_id)
        if row is None:
            raise lifecycle.NotFound(entity_id)
        if expected_version is not None and expected_version != row.version:
            raise lifecycle.VersionConflict(entity_id, expected_version, row.version)
        if set(fields) & ({'id'} | cls.state_fields()):
            raise ValueError('update may not set the id or the state; an edge does')
        frozen = set(fields) & cls.frozen_fields()
        if frozen:
            raise ValueError('%s fields are frozen once recorded: %s' % (cls.__name__,
                                                                         sorted(frozen)))
        new = dataclasses.replace(row.entity, **fields)
        out = FakeRow(new, row.version + 1, by=actor.id, created_at=row.created_at)
        self.placed[cls][:] = [out if r is row else r for r in self.placed[cls]]
        return out

    def append(self, event):
        self.calls.append(('append', event))
        self.events.append(event)


def _principal(actor, column):
    if not ids.is_id(actor.id, 'principal'):
        raise ValueError('%s must be a principal id, not %r' % (column, actor.id))


def user_device():
    return Ref('user_device', ids.new_id('principal'))


def an_account():
    return entities.Account(id=ids.new_id('account'), harness_id='fake', label='A',
                            auth_kind='api_key')


def a_project(workspace_id=None):
    return entities.Project(id=ids.new_id('project'),
                            workspace_id=workspace_id or ids.GLOBAL_WORKSPACE, name='p')


def an_optin(owner, owner_id, kind, name, opted_in=True):
    return entities.OptIn(id=ids.new_id('opt_in'), kind=kind, name=name,
                          opted_in=opted_in, **{owner + '_id': owner_id})


def cmd(tx, actor, owner_id, kind, name, opted_in, expected_version=None):
    return optins.set_opt_in(tx, actor=actor, owner_id=owner_id, kind=kind, name=name,
                             opted_in=opted_in, expected_version=expected_version)


def fake_rows_where(tx):
    def where(conn, cls, **eq):
        unknown = set(eq) - {f.name for f in dataclasses.fields(cls)}
        if unknown:
            raise LookupError('%s has no column %s' % (cls.__name__, sorted(unknown)))
        return [r for r in tx.placed.get(cls, ())
                if all(getattr(r.entity, k, None) == v for k, v in eq.items())]
    return where


def test_a_stranger_touches_no_tx_call_at_all_even_for_a_real_project():
    tx = FakeTx()
    prj = tx.place(a_project()).entity
    stranger_kinds = ('brain', 'execution', 'automation', 'node', 'system')
    for kind in stranger_kinds:
        with pytest.raises(A.NotPermitted, match='only a user device'):
            cmd(tx, Ref(kind, ids.new_id('principal')), prj.id, 'mcp', 'gh', True)
    with pytest.raises(A.NotPermitted, match='only a user device'):
        cmd(tx, Ref('user', ids.new_id('principal')), prj.id, 'mcp', 'gh', True)
    with pytest.raises(A.NotPermitted, match='only a user device'):
        cmd(tx, Ref('brain', ids.new_id('principal')), prj.id, 'mcp', 'gh', False)
    assert tx.calls == [] and tx.events == []
    out = cmd(tx, user_device(), prj.id, 'mcp', 'gh', True)
    assert out['changed'] is True and out['opt_in']['project_id'] == prj.id
    assert tx.ops() == ['get', 'where', 'insert', 'append']


def test_the_device_gate_wins_before_the_owner_id_grammar_is_even_read():
    bad_owners = [None, '', 'acc_not-a-ulid', 'account', 'prj_', 42]
    for owner in bad_owners:
        tx = FakeTx()
        with pytest.raises(A.NotPermitted, match='only a user device'):
            cmd(tx, Ref('brain', ids.new_id('principal')), owner, 'mcp', 'gh', True)
        assert tx.calls == []
        with pytest.raises(ValueError, match='neither'):
            cmd(tx, user_device(), owner, 'mcp', 'gh', True)
        assert tx.calls == []


def test_a_stale_expected_version_refuses_an_already_opted_out_ask_with_no_update_and_no_event():
    tx = FakeTx()
    acc = tx.place(an_account()).entity
    oid = tx.place(an_optin('account', acc.id, 'mcp', 'gh', opted_in=False),
                   version=2).entity.id
    for stale in (0, 1, 99):
        with pytest.raises(lifecycle.VersionConflict) as ei:
            cmd(tx, user_device(), acc.id, 'mcp', 'gh', False, expected_version=stale)
        assert (ei.value.entity_id, ei.value.expected, ei.value.current) == (oid, stale, 2)
    assert tx.ops() == ['get', 'where'] * 3
    out = cmd(tx, user_device(), acc.id, 'mcp', 'gh', False)
    assert out['changed'] is False and out['opt_in']['version'] == 2
    assert out['opt_in']['opted_in'] is False and out['opt_in']['id'] == oid
    assert tx.ops() == ['get', 'where'] * 4 and tx.events == []


def test_the_flip_hands_tx_update_exactly_the_new_value_the_actor_and_the_caller_version():
    tx = FakeTx()
    acc = tx.place(an_account()).entity
    actor = user_device()
    oid = tx.place(an_optin('account', acc.id, 'mcp', 'gh', opted_in=True)).entity.id
    with pytest.raises(lifecycle.VersionConflict) as ei:
        cmd(tx, actor, acc.id, 'mcp', 'gh', False, expected_version=9)
    assert (ei.value.entity_id, ei.value.expected, ei.value.current) == (oid, 9, 1)
    (lost,) = tx.updates()
    assert lost[1] is entities.OptIn and lost[2] == oid
    assert lost[3] == {'opted_in': False}
    assert lost[4] == actor and lost[5] == 9
    assert tx.events == []
    won = cmd(tx, actor, acc.id, 'mcp', 'gh', False, expected_version=1)
    assert won['changed'] is True and won['opt_in']['version'] == 2
    assert won['opt_in']['opted_in'] is False and won['opt_in']['id'] == oid
    (e,) = tx.events
    assert e.subject == Ref('opt_in', oid) and e.actor == actor
    assert e.payload == {'owner': 'account', 'owner_id': acc.id, 'kind': 'mcp',
                         'name': 'gh', 'opted_in': False, 'version': 2}


def test_a_missing_owner_refuses_with_the_loads_normal_notfound_and_stops_before_the_find():
    for kind, factory in (('account', an_account), ('project', a_project)):
        tx = FakeTx()
        gone = factory().id
        with pytest.raises(lifecycle.NotFound) as ei:
            cmd(tx, user_device(), gone, 'mcp', 'gh', True)
        assert ei.value.args[0] == gone
        assert tx.ops() == ['get'] and tx.events == []
        tx2 = FakeTx()
        with pytest.raises(lifecycle.NotFound):
            cmd(tx2, user_device(), gone, 'mcp', 'gh', False)
        assert tx2.ops() == ['get'] and tx2.events == []


def test_the_verify_baseline_the_command_writes_is_exactly_the_row_the_worker_gate_reads():
    tx = FakeTx()
    prj = tx.place(a_project(workspace_id=ids.new_id('workspace'))).entity
    out = cmd(tx, user_device(), prj.id, 'verify', 'baseline', True)
    assert out['changed'] is True
    (row,) = tx.inserts()
    assert (row.kind, row.name, row.opted_in) == ('verify', 'baseline', True)
    assert row.opted_in is True and isinstance(row.opted_in, bool)
    assert (row.project_id, row.account_id) == (prj.id, None)
    (e,) = tx.events
    assert e.subject == Ref('opt_in', row.id)
    assert e.payload['owner'] == 'project' and e.payload['name'] == 'baseline'
    assert (e.workspace, e.project) == (prj.workspace_id, prj.id)
    tx.place(an_optin('project', ids.new_id('project'), 'verify', 'baseline'))
    tx_saved, rows_live = rows_module.where, fake_rows_where(tx)
    rows_module.where = rows_live
    try:
        eff = optins.effective(object(), account_id=None, project_id=prj.id)
        assert eff == (('project', 'verify', 'baseline'),)
        assert eff == (worker.BASELINE,)
        assert optins.effective(object(), account_id=None, project_id=None) == ()
    finally:
        rows_module.where = tx_saved
    tx2 = FakeTx()
    acc = tx2.place(an_account()).entity
    with pytest.raises(ValueError, match='verify opt-in'):
        cmd(tx2, user_device(), acc.id, 'verify', 'baseline', True)
    assert tx2.ops() == ['get', 'where']


def test_find_matches_kind_and_name_exactly_so_verify_and_verify_are_two_rows():
    tx = FakeTx()
    prj = tx.place(a_project()).entity
    actor = user_device()
    first = cmd(tx, actor, prj.id, 'plugin', 'verify', True)
    assert first['changed'] is True
    second = cmd(tx, actor, prj.id, 'plugin', 'Verify', True)
    assert second['changed'] is True and second['opt_in']['id'] != first['opt_in']['id']
    again = cmd(tx, actor, prj.id, 'plugin', 'verify', True)
    assert again['changed'] is False and again['opt_in']['id'] == first['opt_in']['id']
    other_kind = cmd(tx, actor, prj.id, 'mcp', 'verify', True)
    assert other_kind['changed'] is True and other_kind['opt_in']['id'] not in (
        first['opt_in']['id'], second['opt_in']['id'])
    assert [(c['kind'], c['name']) for c in tx.find_calls()] == [
        ('plugin', 'verify'), ('plugin', 'Verify'), ('plugin', 'verify'), ('mcp', 'verify')]
    kinds_names = sorted((r.kind, r.name) for r in tx.inserts())
    assert kinds_names == [('mcp', 'verify'), ('plugin', 'Verify'), ('plugin', 'verify')]
    assert len(tx.events) == 3


def test_a_falsy_non_boolean_ask_on_no_row_is_the_write_free_opt_out():
    for falsy in (0, ''):
        tx = FakeTx()
        acc = tx.place(an_account()).entity
        out = cmd(tx, user_device(), acc.id, 'mcp', 'gh', falsy)
        assert out == {'opt_in': None, 'changed': False}
        assert tx.ops() == ['get', 'where'], falsy
        assert tx.events == []


def test_a_truthy_non_boolean_first_ask_is_refused_before_any_row_is_written():
    tx = FakeTx()
    acc = tx.place(an_account()).entity
    for truthy in ('yes', 1):
        with pytest.raises(ValueError, match='boolean'):
            cmd(tx, user_device(), acc.id, 'mcp', 'gh', truthy)
    assert tx.calls == [] and tx.events == []


def test_asking_a_true_row_with_the_integer_one_is_refused_as_an_unvalidated_opted_in():
    tx = FakeTx()
    acc = tx.place(an_account()).entity
    row = tx.place(an_optin('account', acc.id, 'mcp', 'gh', opted_in=True)).entity
    with pytest.raises(ValueError, match='boolean'):
        cmd(tx, user_device(), acc.id, 'mcp', 'gh', 1)
    (kept,) = tx.placed[entities.OptIn]
    assert (kept.entity.id, kept.version, kept.entity.opted_in) == (row.id, 1, True)
    assert tx.events == []


def test_asking_a_true_row_with_a_truthy_string_is_refused_before_the_flip():
    tx = FakeTx()
    acc = tx.place(an_account()).entity
    row = tx.place(an_optin('account', acc.id, 'mcp', 'gh', opted_in=True)).entity
    with pytest.raises(ValueError, match='boolean'):
        cmd(tx, user_device(), acc.id, 'mcp', 'gh', 'yes')
    assert tx.updates() == []
    (kept,) = tx.placed[entities.OptIn]
    assert (kept.entity.id, kept.version, kept.entity.opted_in) == (row.id, 1, True)
    assert tx.events == []
