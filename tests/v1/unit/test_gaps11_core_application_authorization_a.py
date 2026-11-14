"""T-1413: the uncovered branches of `archeus/core/application/authorization.py` lines
1002-1099 inclusive (`_retire`, `retire_rule`, `set_profile`, `record_unrecoverable`, and
the start of class `Authorization`) at tip 6a32dc14 (re-located at 81d83030). No source
file is edited.

Ten selected branches, denial and fail-closed first, then boundaries, then error paths:

1. 1004-1006 _retire: an already retired rule raises IllegalTrigger and writes nothing.
   Catches: the retired check dropped or inverted.
2. 1013-1015 retire_rule: a refused principal stops before the rule is loaded or updated.
   Catches: `_principal` moved after the load, or its result ignored.
3. 1007-1009 _retire: a successful retire writes retired_at = tx.now and one
   'policy_rule.retired' event with before = old.to_dict() and replaced_by (None by default).
   Catches: the payload keys, or the timestamp source.
4. 1022-1024 set_profile: a profile outside AUTONOMY_PROFILES is refused, except scope 'mission' with None.
   Catches: the mission-None exception removed, or the membership test inverted.
5. 1025-1036 set_profile scope 'user': an existing User row is updated; with none, a User
   named 'owner' is inserted; one 'user.updated' event lists the field.
   Catches: the branch order, the display name, the event fields.
6. 1037-1038 set_profile: any scope other than 'user' or 'mission' is refused and writes nothing.
   Catches: the scope guard removed.
7. 1039-1044 set_profile scope 'mission': the mission row is updated and one 'mission.updated'
   event carries its workspace and project; an unknown mission raises NotFound before any write.
   Catches: the event taking the wrong workspace or project, or the write before the load.
8. 1050-1052 record_unrecoverable: facts with no DENY return None and call no record();
   ALLOW or REVIEW alone do not count as a denial.
   Catches: the DENY filter widened, or the early return removed.
9. 1053-1060 record_unrecoverable: with DENY items the record is written at stage 'dispatch',
   decision 'DENY', outcome 'denied', reason = DENY reasons joined by '; ', plan None without an active plan.
   Catches: a reason joiner or filter change, a plan taken from the wrong place.
10. 1055-1056 record_unrecoverable: the context is built at stage 'dispatch' with tx.now, not the wall clock.
    Catches: `now=tx.now` replaced by a clock read or a different stage.

Closest existing tests: tests/v1/unit/test_gaps_core_application_authorization_a.py and
tests/v1/unit/test_gaps_core_application_authorization_b.py (no hit for these functions in the
gap files). Fakes only: a fake tx recording update, insert, append; lifecycle.load, _principal,
_rule_event, active_plan, context and record are replaced in the module under test.
No database, no real clock.
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import authorization as A
from archeus.core.application import commands, lifecycle
from archeus.core.domain import entities

NOW = '2026-10-30T12:00:00+00:00'


class Refused(Exception):
    pass


@pytest.fixture(autouse=True)
def plain_events(monkeypatch):
    def event(type, subject, actor, payload=None, **kw):
        return SimpleNamespace(type=type, subject=subject, actor=actor, payload=payload, **kw)
    monkeypatch.setattr(A, 'new_event', event)


class Tx:
    def __init__(self):
        self.now = NOW
        self.conn = object()
        self.updates, self.inserts, self.events = [], [], []

    def update(self, cls, id_, fields, *, actor):
        self.updates.append((cls, id_, dict(fields), actor))
        return SimpleNamespace(entity=SimpleNamespace(id=id_, retired_at=fields.get('retired_at')),
                               version=2)

    def insert(self, entity, *, actor):
        self.inserts.append((entity, actor))
        return SimpleNamespace(entity=entity, version=1)

    def append(self, event):
        self.events.append(event)


class _Old:
    def __init__(self, id_='rule_1', retired_at=None):
        self.id, self.retired_at = id_, retired_at

    def to_dict(self):
        return {'id': self.id, 'retired_at': self.retired_at}


@pytest.fixture
def rule_events(monkeypatch):
    seen = []

    def record(tx, type_, actor, rule_entity, payload):
        seen.append((type_, actor, rule_entity.id, payload))

    monkeypatch.setattr(A, '_rule_event', record)
    return seen


def _load(monkeypatch, entity_for_cls):
    def load(tx, cls, id_):
        if id_ not in entity_for_cls:
            raise lifecycle.NotFound(id_)
        return SimpleNamespace(entity=entity_for_cls[id_])
    monkeypatch.setattr(lifecycle, 'load', load)


# 1. 1004-1006: a retired rule is refused without writes
def test_retire_refuses_an_already_retired_rule_and_writes_nothing(monkeypatch, rule_events):
    _load(monkeypatch, {'rule_1': _Old(retired_at='2026-01-01T00:00:00+00:00')})
    tx = Tx()
    with pytest.raises(lifecycle.IllegalTrigger):
        A._retire(tx, 'actor_1', 'rule_1')
    assert tx.updates == []
    assert rule_events == []


# 2. 1013-1015: a refused principal stops retire_rule before the rule is read
def test_retire_rule_stops_at_the_principal_check_before_loading_or_writing(monkeypatch,
                                                                             rule_events):
    calls = []

    def refuse(tx, actor, scope):
        calls.append(scope)
        raise Refused('not an admin')

    monkeypatch.setattr(A, '_principal', refuse)
    monkeypatch.setattr(lifecycle, 'load', lambda *a, **k: calls.append('loaded'))
    tx = Tx()
    with pytest.raises(Refused):
        A.retire_rule(tx, actor=object(), rule_id='rule_1')
    assert calls == ['admin']
    assert tx.updates == []
    assert rule_events == []


# 3. 1007-1009: a successful retire writes retired_at and one event with before
def test_retire_writes_retired_at_and_one_event_with_the_old_row(monkeypatch, rule_events):
    old = _Old()
    _load(monkeypatch, {'rule_1': old})
    tx = Tx()
    row = A._retire(tx, 'actor_1', 'rule_1')
    assert tx.updates == [(entities.PolicyRule, 'rule_1', {'retired_at': NOW}, 'actor_1')]
    assert row.entity.retired_at == NOW
    assert rule_events == [('policy_rule.retired', 'actor_1', 'rule_1',
                            {'before': old.to_dict(), 'replaced_by': None})]


def test_retire_carries_the_replacement_into_the_event(monkeypatch, rule_events):
    _load(monkeypatch, {'rule_1': _Old()})
    A._retire(Tx(), 'actor_1', 'rule_1', replaced_by='rule_2')
    assert rule_events[0][3]['replaced_by'] == 'rule_2'


# 4. 1022-1024: an unknown profile is refused, except clearing a mission's profile
@pytest.mark.parametrize('profile', ['reckless', 'AUTONOMOUS', ''])
def test_set_profile_refuses_a_profile_outside_the_set(monkeypatch, profile):
    monkeypatch.setattr(A, '_principal', lambda *a: None)
    tx = Tx()
    with pytest.raises(ValueError):
        A.set_profile(tx, actor=object(), scope='user', profile=profile)
    assert tx.updates == [] and tx.inserts == [] and tx.events == []


def test_set_profile_allows_clearing_a_mission_profile(monkeypatch):
    monkeypatch.setattr(A, '_principal', lambda *a: None)
    _load(monkeypatch, {'mission_1': SimpleNamespace(workspace_id='ws_1', project_id='p_1')})
    tx = Tx()
    out = A.set_profile(tx, actor=object(), scope='mission', profile=None, mission_id='mission_1')
    assert out == {'scope': 'mission', 'mission_id': 'mission_1', 'profile': None}
    assert tx.updates[0][2] == {'autonomy_profile': None}


# 5. 1025-1036: user scope updates an existing row, or inserts 'owner' when none exists
def test_set_profile_user_updates_the_existing_user_row(monkeypatch):
    monkeypatch.setattr(A, '_principal', lambda *a: None)
    monkeypatch.setattr(A.rows, 'where', lambda conn, cls: [SimpleNamespace(
        entity=SimpleNamespace(id='user_1'))])
    tx = Tx()
    out = A.set_profile(tx, actor='actor_1', scope='user', profile='careful')
    assert out == {'scope': 'user', 'profile': 'careful'}
    assert tx.updates == [(entities.User, 'user_1', {'autonomy_profile': 'careful'}, 'actor_1')]
    assert tx.inserts == []
    assert [e.type for e in tx.events] == ['user.updated']
    assert tx.events[0].payload == {'fields': ['autonomy_profile'], 'autonomy_profile': 'careful'}


def test_set_profile_user_inserts_the_owner_when_no_user_row_exists(monkeypatch):
    monkeypatch.setattr(A, '_principal', lambda *a: None)
    monkeypatch.setattr(A.rows, 'where', lambda conn, cls: [])
    tx = Tx()
    A.set_profile(tx, actor='actor_1', scope='user', profile='autonomous')
    assert tx.updates == []
    (entity, actor), = tx.inserts
    assert isinstance(entity, entities.User)
    assert entity.display_name == 'owner'
    assert entity.autonomy_profile == 'autonomous'
    assert actor == 'actor_1'
    assert [e.type for e in tx.events] == ['user.updated']


# 6. 1037-1038: any other scope is refused with no write
@pytest.mark.parametrize('scope', ['workspace', 'project', None])
def test_set_profile_refuses_any_other_scope_without_writing(monkeypatch, scope):
    monkeypatch.setattr(A, '_principal', lambda *a: None)
    tx = Tx()
    with pytest.raises(ValueError):
        A.set_profile(tx, actor=object(), scope=scope, profile='standard')
    assert tx.updates == [] and tx.inserts == [] and tx.events == []


# 7. 1039-1044: mission scope updates the row and names its workspace and project
def test_set_profile_mission_updates_and_names_its_workspace_and_project(monkeypatch):
    monkeypatch.setattr(A, '_principal', lambda *a: None)
    _load(monkeypatch, {'mission_1': SimpleNamespace(workspace_id='ws_1', project_id='p_1')})
    tx = Tx()
    out = A.set_profile(tx, actor='actor_1', scope='mission', profile='standard',
                        mission_id='mission_1')
    assert out == {'scope': 'mission', 'mission_id': 'mission_1', 'profile': 'standard'}
    assert tx.updates == [(entities.Mission, 'mission_1', {'autonomy_profile': 'standard'},
                           'actor_1')]
    (ev,) = tx.events
    assert ev.type == 'mission.updated'
    assert ev.payload == {'fields': ['autonomy_profile'], 'autonomy_profile': 'standard'}
    assert ev.workspace == 'ws_1' and ev.project == 'p_1'


def test_set_profile_mission_refuses_an_unknown_mission_before_any_write(monkeypatch):
    monkeypatch.setattr(A, '_principal', lambda *a: None)
    _load(monkeypatch, {})
    tx = Tx()
    with pytest.raises(lifecycle.NotFound):
        A.set_profile(tx, actor=object(), scope='mission', profile='standard',
                      mission_id='missing')
    assert tx.updates == [] and tx.events == []


# 8-10. 1050-1060: record_unrecoverable records only a DENY, at dispatch, with tx.now
@pytest.fixture
def recorded(monkeypatch):
    calls = {'context': [], 'record': []}

    def context(conn, mission, **kw):
        calls['context'].append((mission, kw))
        return ('ctx', kw['stage'])

    def record(tx, **kw):
        calls['record'].append(kw)
        return 'recorded'

    monkeypatch.setattr(A, 'context', context)
    monkeypatch.setattr(A, 'record', record)
    return calls


def _facts(*items):
    return SimpleNamespace(evaluated=list(items))


def test_record_unrecoverable_returns_none_without_a_deny(monkeypatch, recorded):
    monkeypatch.setattr(commands, 'active_plan', lambda conn, mid: None)
    facts = _facts({'decision': 'ALLOW', 'reason': 'fine'}, {'decision': 'REVIEW', 'reason': 'ask'})
    assert A.record_unrecoverable(Tx(), actor='actor_1', mission=SimpleNamespace(id='m1'),
                                  facts=facts) is None
    assert recorded['record'] == [] and recorded['context'] == []


def test_record_unrecoverable_writes_the_deny_at_dispatch_with_no_plan(monkeypatch, recorded):
    monkeypatch.setattr(commands, 'active_plan', lambda conn, mid: None)
    items = [{'decision': 'ALLOW', 'reason': 'ok'}, {'decision': 'DENY', 'reason': 'r1'},
             {'decision': 'DENY', 'reason': 'r2'}]
    mission = SimpleNamespace(id='m1')
    out = A.record_unrecoverable(Tx(), actor='actor_1', mission=mission, facts=_facts(*items))
    assert out == 'recorded'
    (kw,) = recorded['record']
    assert kw['stage'] == 'dispatch'
    assert kw['decision'] == 'DENY'
    assert kw['outcome'] == 'denied'
    assert kw['reason'] == 'r1; r2'
    assert kw['plan'] is None
    assert kw['mission'] is mission
    assert kw['items'] == items
    assert kw['ctx'] == ('ctx', 'dispatch')


def test_record_unrecoverable_carries_the_active_plan_when_there_is_one(monkeypatch, recorded):
    plan = SimpleNamespace(id='plan_1')
    monkeypatch.setattr(commands, 'active_plan', lambda conn, mid: SimpleNamespace(entity=plan))
    A.record_unrecoverable(Tx(), actor='actor_1', mission=SimpleNamespace(id='m1'),
                           facts=_facts({'decision': 'DENY', 'reason': 'no'}))
    assert recorded['record'][0]['plan'] is plan
    assert recorded['context'][0][1]['plan'] is plan


def test_record_unrecoverable_builds_the_context_at_the_transaction_time(monkeypatch, recorded):
    monkeypatch.setattr(commands, 'active_plan', lambda conn, mid: None)
    tx = Tx()
    A.record_unrecoverable(tx, actor='actor_1', mission=SimpleNamespace(id='m1'),
                           facts=_facts({'decision': 'DENY', 'reason': 'no'}))
    (_mission, kw), = recorded['context']
    assert kw['now'] == tx.now == NOW
    assert kw['stage'] == 'dispatch'
    assert kw['actor'] == 'actor_1'
