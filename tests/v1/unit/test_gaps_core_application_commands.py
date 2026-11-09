"""T-710: the highest-risk uncovered branches of
`archeus/core/application/commands.py` — what may be guessed, what may be
claimed, and every refusal that must write nothing.

The module's existing coverage reaches it only through the runtime harness
(tests/v1/integration/test_skeleton.py and friends), which drives whole
missions through the engine, so a branch that refuses — a resume with no
record of its hold, a token that is not a digest, a priority that is a bool —
was mostly steered around rather than hit. This file drives the commands
directly over a real database, the way the sibling application modules' unit
tests do (tests/v1/unit/test_gaps_core_application_verification.py):
`Database.open()` and `db.writer.execute(command, kwargs)`. Missions move
through the real `commands.Missions` under the P1 allow-all policy — with the
persisted guard snapshot where the branch is about the rows and an injected
one where it is about the order of the exits — so every move proven here is a
real edge of P3's machine and every refusal leaves the rows and the event log
exactly as they were. Nothing spawns a process, touches git or reaches the
network; the only OS interface is the database under the test's own
`ARCHEUS_HOME` (the autouse fixture of tests/v1/conftest.py).
"""

import hashlib
import json

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle
from archeus.core.domain import entities, guards, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import IdempotencyConflict

HEAD = 'c' * 40            # the mission branch head, as recorded
OTHER = 'f' * 40           # a revision the mission branch is not at
SHA = 'a' * 64             # a sha256 hex digest, well-formed and meaningless
PIN = 'pbkdf2_sha256$200000$%s$%s' % ('d' * 32, 'e' * 64)     # a PIN at rest


def who(kind='user_device'):
    """A principal of *kind*: the only thing a caller may claim to be."""
    return Ref(kind, ids.new_id('principal'))


def missions(facts=None):
    """The real `Missions` under the P1 allow-all policy. *facts*, when given,
    fixes the guard snapshot; when not, the persisted one reads the rows — the
    difference is exactly what half of these branches decide."""
    if facts is None:
        return commands.Missions(policy=ports.AllowAllPolicy())
    return commands.Missions(policy=ports.AllowAllPolicy(), facts=lambda tx, row: facts)


# ── seeding: one transaction each, no command and no process ────────────────

def _seed(db, actor, **over):
    """One mission, with the event its insert owes. Keywords override any
    field — state included: an insert is not a move, only `transition` is."""
    f = dict(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
             title='M', objective='o', origin='api')
    f.update(over)
    m = entities.Mission(**f)

    def run(tx, **_):
        tx.insert(m, actor=actor)
        tx.append(new_event('mission.created', Ref('mission', m.id), actor,
                            payload={'title': m.title}, workspace=m.workspace_id,
                            project=m.project_id))
    db.writer.execute(run, {})
    return m.id


def _insert(db, actor, entity, subject=None, type_='mission.updated'):
    """One more row, with the event its insert owes (a plan, a review, an
    approval): what no command of this module can put there as a starting
    state — for a verdict, a hold, or a row that only the engine creates."""
    sub = subject if subject is not None else Ref('mission', entity.mission_id)

    def run(tx, **_):
        tx.insert(entity, actor=actor)
        tx.append(new_event(type_, sub, actor, payload={'fields': []},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return entity.id


_UNSET = object()


def _register(db, actor, **over):
    """A client registered as P3.5b does it: the token arrives only as a hash.
    Each call gets its own digest unless the test names one — token_hash is
    unique in `tokens`, and a registration is about one client at a time."""
    token = over.pop('token_hash', _UNSET)
    if token is _UNSET:
        token = hashlib.sha256(ids.new_id('device').encode()).hexdigest()
    kw = dict(name='client', platform='web', token_hash=token, scopes=('observe',))
    kw.update(over)
    return db.writer.execute(commands.register_device, dict(actor=actor, **kw))


def _row(db, cls, entity_id):
    with db.read() as c:
        r = rows.get(c, cls, entity_id)
    return None if r is None else r.entity


def _version(db, cls, entity_id):
    with db.read() as c:
        r = rows.get(c, cls, entity_id)
    return None if r is None else r.version


def _all(db, cls, **eq):
    with db.read() as c:
        return [r.entity for r in rows.where(c, cls, **eq)]


def _events(db, type_):
    """The payloads of the events of *type_*, oldest first."""
    with db.read() as c:
        return [json.loads(p) for (p,) in c.execute(
            'SELECT payload FROM events WHERE type = ? ORDER BY seq', (type_,))]


def _n_events(db):
    with db.read() as c:
        return c.execute('SELECT COUNT(*) FROM events').fetchone()[0]


def _tokens(db):
    with db.read() as c:
        return [dict(r) for r in c.execute('SELECT * FROM tokens ORDER BY rowid')]


def _facts(db, mission_id):
    """`persisted_facts` as the guards see it, in JSON shape: what the snapshot
    knows about a mission's rows, and — the point — what it refuses to guess."""
    def probe(tx):
        row = tx.get(entities.Mission, mission_id)
        f = commands.persisted_facts(tx, row)
        return {'plan_version': f.plan_version, 'cost': f.cost_within_ceiling,
                'review': f.review, 'tasks': sorted(t.key for t in f.tasks),
                'criteria': [[c.check, c.verification] for c in f.criteria]}
    return db.writer.execute(probe, {})


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    try:
        yield d
    finally:
        d.close()


# ── what a caller may claim (principals, devices, tokens) ───────────────────

def test_register_principal_records_the_kind_and_the_scopes_it_is_given(db):
    """commands.py:35 (`p = entities.Principal(..., scopes=tuple(scopes))`) and
    38-41 (the `principal.created` payload): widened — a scope outside its kind's set,
    an unknown kind — hands every later gate an actor that can do what its kind
    may never do (domain-model §3.3)."""
    actor_out = db.writer.execute(commands.register_principal,
                                  dict(kind='user_device', scopes=['observe', 'approve']))
    assert set(actor_out) == {'id', 'version', 'seq'} and actor_out['version'] == 1
    p = _row(db, entities.Principal, actor_out['id'])
    assert (p.kind, p.scopes) == ('user_device', ('observe', 'approve'))
    assert _events(db, 'principal.created') == [
        {'kind': 'user_device', 'scopes': ['observe', 'approve']}]
    bare = db.writer.execute(commands.register_principal, dict(kind='system'))
    assert _row(db, entities.Principal, bare['id']).scopes == ()
    before = _n_events(db)
    with pytest.raises(ValueError, match='cannot hold'):
        db.writer.execute(commands.register_principal, dict(kind='system', scopes=['approve']))
    with pytest.raises(ValueError):                       # `_CHOICES` on kind
        db.writer.execute(commands.register_principal, dict(kind='wizard', scopes=[]))
    assert len(_all(db, entities.Principal)) == 2 and _n_events(db) == before


def test_register_device_records_principal_active_device_and_the_token_hash(db):
    """commands.py:140-152 (the principal at :140, `client_type=client_type or
    ('cli' if platform == 'tui' else 'spa')` at :147, the `code_redeemed` fire
    at :149 and `insert_token` with only the digest at :151-152): the one
    transaction that credentials come from. A
    device left PAIRING authenticates as nothing; a token recorded as anything
    other than the digest is a leaked secret."""
    actor = who('system')
    out = _register(db, actor, platform='tui', token_hash=SHA, pin_hash=PIN,
                    expires_at='2030-01-01T00:00:00Z')
    assert (out['state'], out['version']) == ('ACTIVE', 2)
    d = _row(db, entities.Device, out['device_id'])
    assert (d.client_type, d.principal_id, d.pin_hash, d.state, d.supersede) == (
        'cli', out['principal_id'], PIN, 'ACTIVE', None)
    assert _row(db, entities.Principal, out['principal_id']).scopes == ('observe',)
    (tok,) = _tokens(db)
    assert (tok['token_hash'], tok['kind'], tok['principal_id'],
            tok['revoked_at'], tok['expires_at']) == (
        SHA, 'device', out['principal_id'], None, '2030-01-01T00:00:00Z')
    assert json.loads(tok['scopes']) == ['observe'] and tok['created_by'] == actor.id
    web = _register(db, actor)                             # another client, the other type
    assert _row(db, entities.Device, web['device_id']).client_type == 'spa'


@pytest.mark.parametrize('bad', ['z' * 64, 'A' * 64, 'a' * 63, 'a' * 65, 'deadbeef',
                                 None, 1234, 12.5, []],
                         ids=['not-hex', 'upper-hex', 'too-short', 'too-long',
                              'short-hex', 'missing', 'number', 'float', 'list'])
def test_register_device_refuses_a_token_hash_that_is_not_a_sha256_digest(db, bad):
    """commands.py:133-134 (`if not (isinstance(token_hash, str) and
    entities._HEX64.fullmatch(token_hash))`): the command's own words say the
    token never enters it — this line is the only thing that keeps that true.
    Weaken it and a plaintext credential is stored where a digest belongs, or
    a non-string reaches `bytes.fromhex` at the first authentication."""
    before = _n_events(db)
    with pytest.raises(ValueError, match='token_hash is a sha256 hex digest'):
        _register(db, who('system'), token_hash=bad)
    assert _all(db, entities.Device) == [] and _all(db, entities.Principal) == []
    assert _tokens(db) == [] and _n_events(db) == before


def test_supersede_revokes_the_active_holder_of_its_slot_and_nothing_else(db):
    """commands.py:136-139 (`if r.entity.supersede == supersede and
    r.entity.state == 'ACTIVE'` at :137): a slot taken twice must kill the old shell's
    credential at the next launch. Dropping the state test revokes a PAIRING
    client that never held the slot; dropping the slot test revokes every
    client on the machine."""
    actor = who('system')
    first = _register(db, actor, supersede='desktop shell')
    second = _register(db, actor, supersede='desktop shell')
    assert _row(db, entities.Device, first['device_id']).state == 'REVOKED'
    assert _row(db, entities.Device, second['device_id']).state == 'ACTIVE'
    toks = {t['principal_id']: t for t in _tokens(db)}
    assert toks[first['principal_id']]['revoked_at'] is not None
    assert toks[second['principal_id']]['revoked_at'] is None
    assert any('superseded by a new desktop shell' in e['reason']
               for e in _events(db, 'device.state_changed'))
    free = _register(db, actor)                            # no slot: never touched
    third = _register(db, actor, supersede='desktop shell')
    assert _row(db, entities.Device, free['device_id']).state == 'ACTIVE'
    assert _row(db, entities.Device, second['device_id']).state == 'REVOKED'
    assert _row(db, entities.Device, third['device_id']).state == 'ACTIVE'
    pairing_principal = db.writer.execute(commands.register_principal,
                                          dict(kind='user_device', scopes=['observe']))['id']
    pairing = ids.new_id('device')                         # a holder still PAIRING
    _insert(db, actor, entities.Device(id=pairing, principal_id=pairing_principal,
                                       name='half', platform='web', supersede='desktop shell'),
            subject=Ref('device', pairing), type_='device.state_changed')
    fourth = _register(db, actor, supersede='desktop shell')
    assert _row(db, entities.Device, pairing).state == 'PAIRING'      # never held: not revoked
    assert _row(db, entities.Device, fourth['device_id']).state == 'ACTIVE'
    with pytest.raises(ValueError):                        # `_CHOICES` on supersede
        _register(db, actor, supersede='admin')


def test_revoking_a_device_revokes_exactly_its_principals_tokens(db):
    """commands.py:159-160 (`row, e = lifecycle.fire(..., 'revoke', ...)` then
    `tx.revoke_tokens(row.entity.principal_id)`): the credential outlives the
    client unless both halves move together — and revoking by anything other
    than this device's own principal kills an unrelated client's token."""
    actor = who('system')
    a = _register(db, actor, token_hash=SHA)
    b = _register(db, actor, token_hash='b' * 64)
    out = db.writer.execute(commands.revoke_device, dict(actor=actor,
                                                          device_id=a['device_id']))
    assert (out['state'], out['changed'], out['version']) == ('REVOKED', True, 3)
    toks = {t['principal_id']: t for t in _tokens(db)}
    assert toks[a['principal_id']]['revoked_at'] is not None
    assert toks[b['principal_id']]['revoked_at'] is None
    before = _n_events(db)
    with pytest.raises(lifecycle.IllegalTrigger, match="no 'revoke' edge from REVOKED"):
        db.writer.execute(commands.revoke_device, dict(actor=actor,
                                                       device_id=a['device_id']))
    with pytest.raises(lifecycle.NotFound):
        db.writer.execute(commands.revoke_device, dict(actor=actor,
                                                       device_id=ids.new_id('device')))
    assert _row(db, entities.Device, a['device_id']).state == 'REVOKED'
    assert _n_events(db) == before                         # both refusals wrote nothing


def test_record_connection_traces_presence_and_refuses_an_unknown_device(db):
    """commands.py:169-170 (`if tx.get(entities.Device, device_id) is None:
    raise lifecycle.NotFound`) and 173 (`if not opened: payload['reason'] =
    reason`): presence is audit, so an event and nothing else; invented for a
    device that does not exist, it is a log that lies, and a half-written one
    (an open with no close, a close with no reason) is the lie by omission."""
    actor = who('system')
    d = _register(db, actor)
    before = _n_events(db)
    out = db.writer.execute(commands.record_connection,
                            dict(actor=actor, device_id=d['device_id'],
                                 connection_id='conn-1', opened=True, reason='ignored'))
    assert set(out) == {'seq'} and isinstance(out['seq'], int)
    assert _events(db, 'device.stream_opened') == [{'connection_id': 'conn-1'}]
    assert _events(db, 'device.stream_closed') == []
    db.writer.execute(commands.record_connection,
                      dict(actor=actor, device_id=d['device_id'],
                           connection_id='conn-1', opened=False, reason='client left'))
    assert _events(db, 'device.stream_closed') == [{'connection_id': 'conn-1',
                                                    'reason': 'client left'}]
    assert (_row(db, entities.Device, d['device_id']).state,
            _version(db, entities.Device, d['device_id'])) == ('ACTIVE', 2)
    before2 = _n_events(db)
    with pytest.raises(lifecycle.NotFound):
        db.writer.execute(commands.record_connection,
                          dict(actor=actor, device_id=ids.new_id('device'),
                               connection_id='conn-2', opened=True))
    assert _n_events(db) == before2


def test_a_pin_check_that_was_never_asked_never_hashes(db, monkeypatch):
    """commands.py:110-111 (`if not (record and isinstance(pin, str) and pin):
    return False`): inverted or widened, an empty PIN against no record
    becomes a step-up accepted on nothing — and each such call is 200 000
    pbkdf2 iterations handed to whoever sends `{}`. The counting patch proves
    the refusal short-circuits *before* the hash, which no post-hoc assert can."""
    calls = []
    real = hashlib.pbkdf2_hmac
    monkeypatch.setattr(commands.hashlib, 'pbkdf2_hmac',
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    record = commands.hash_pin('2468')                    # the minting hashes too
    calls.clear()
    assert commands.pin_matches(record, '2468') is True
    assert len(calls) == 1
    for bad_record, bad_pin in [(None, '2468'), ('', '2468'), (record, None),
                                (record, ''), (record, 2468), (record, True)]:
        assert commands.pin_matches(bad_record, bad_pin) is False
    assert commands.pin_matches(record, '0000') is False            # compared, not equal
    assert len(calls) == 2                                  # that one did hash


# ── missions: what may be claimed about a mission ───────────────────────────

def test_a_mission_can_only_name_a_registered_project(db):
    """commands.py:81-82 (`if project_id is not None and tx.get(entities.Project,
    project_id) is None: raise lifecycle.NotFound(project_id)`): an invented
    project id would give the mission a provenance nothing owns — and every
    later read that joins on it dangles."""
    actor = who()
    ghost = ids.new_id('project')
    before = _n_events(db)
    with pytest.raises(lifecycle.NotFound):
        db.writer.execute(commands.create_mission,
                          dict(actor=actor, title='t', objective='o', project_id=ghost))
    assert _all(db, entities.Mission) == [] and _n_events(db) == before
    prj = entities.Project(id=ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE,
                           name='p')
    _insert(db, actor, prj, subject=Ref('project', prj.id), type_='project.created')
    out = db.writer.execute(commands.create_mission,
                            dict(actor=actor, title='Ship it', objective='o',
                                 project_id=prj.id,
                                 success_criteria=[{'text': 'it works', 'check': 'automatic'}]))
    assert (out['state'], out['version'], isinstance(out['seq'], int)) == ('CREATED', 1, True)
    m = _row(db, entities.Mission, out['id'])
    assert (m.project_id, m.title, m.success_criteria) == (
        prj.id, 'Ship it', ({'text': 'it works', 'check': 'automatic'},))
    assert _events(db, 'mission.created')[-1] == {'title': 'Ship it'}


def test_replaying_the_same_request_twice_creates_one_mission(db):
    """The writer's replay half as commands.py depends on it (writer.py:434-438
    the stored-response return, 475-477 the `IdempotencyConflict`): the same
    create, twice, is one mission and one event — and the *same key over a
    different body* is not a replay at all but a collision, answered with an
    error rather than silently running the second request."""
    actor = who()
    kw = dict(actor=actor, title='once', objective='o')
    first = db.writer.execute(commands.create_mission, kw, idempotency_key='K1')
    second = db.writer.execute(commands.create_mission, dict(kw), idempotency_key='K1')
    assert second == first
    assert len(_all(db, entities.Mission)) == 1
    assert len(_events(db, 'mission.created')) == 1
    with pytest.raises(IdempotencyConflict):
        db.writer.execute(commands.create_mission, dict(kw, title='other'),
                          idempotency_key='K1')
    assert len(_all(db, entities.Mission)) == 1
    assert db.writer.execute(commands.create_mission, dict(kw),
                             idempotency_key='K1') == first      # still only ever one


def test_reprioritise_refuses_a_priority_that_is_not_an_int(db):
    """commands.py:451-452 (`if not isinstance(priority, int) or
    isinstance(priority, bool)`): `True` is the int that is not one — dropped,
    it sorts a mission at priority 1, and a float, a string or a missing
    priority is a dispatch order the router cannot compare."""
    actor = who()
    mid = _seed(db, actor)
    before, was = _n_events(db), _version(db, entities.Mission, mid)
    for bad in (True, False, '3', 2.5, None):
        with pytest.raises(ValueError, match='priority is an integer'):
            db.writer.execute(missions().reprioritise,
                              dict(actor=actor, mission_id=mid, priority=bad))
    assert (_row(db, entities.Mission, mid).priority,
            _version(db, entities.Mission, mid), _n_events(db)) == (0, was, before)


@pytest.mark.parametrize('state', ['COMPLETED', 'CANCELLED'], ids=['completed', 'cancelled'])
def test_reprioritise_refuses_a_mission_that_has_ended(db, state):
    """commands.py:455-457 (`if m.state in states.terminal('mission'): raise
    lifecycle.IllegalTrigger(..., 'the mission has ended')`): an ended mission
    dispatches nothing, so a priority on it is a queue entry for a ghost —
    and history that was quietly rewritten."""
    actor = who()
    mid = _seed(db, actor, state=state)
    before = _n_events(db)
    with pytest.raises(lifecycle.IllegalTrigger, match='the mission has ended'):
        db.writer.execute(missions().reprioritise,
                          dict(actor=actor, mission_id=mid, priority=5))
    assert _row(db, entities.Mission, mid).priority == 0 and _n_events(db) == before


def test_reprioritise_writes_once_and_repeats_itself_quietly(db):
    """commands.py:458-459 (`if m.priority == priority: return _result(row)`)
    with the recorded side (the `mission.updated` carrying the *was*) and the
    `expected_version` the update checks: setting the same priority twice must
    not age the row or the log, and a stale version must not be applied over a
    newer one."""
    actor = who()
    mid = _seed(db, actor)
    ms = missions()
    quiet = db.writer.execute(ms.reprioritise, dict(actor=actor, mission_id=mid, priority=0))
    assert (quiet['changed'], quiet['seq'], quiet['transitions'],
            quiet['version']) == (False, None, [], 1)
    out = db.writer.execute(ms.reprioritise, dict(actor=actor, mission_id=mid, priority=5))
    assert (out['changed'], out['version'], isinstance(out['seq'], int)) == (True, 2, True)
    assert _row(db, entities.Mission, mid).priority == 5
    again = db.writer.execute(ms.reprioritise, dict(actor=actor, mission_id=mid, priority=5))
    assert (again['changed'], again['version'], again['seq']) == (False, 2, None)
    assert _events(db, 'mission.updated') == [{'priority': 5, 'was': 0}]
    with pytest.raises(lifecycle.VersionConflict):
        db.writer.execute(ms.reprioritise, dict(actor=actor, mission_id=mid,
                                                priority=7, expected_version=1))
    assert _row(db, entities.Mission, mid).priority == 5


# ── holds and their release: nothing may be guessed ─────────────────────────

def test_a_hold_with_no_record_of_where_it_came_from_is_never_resumed(db):
    """commands.py:480-483 (`if held_from is None: raise lifecycle.IllegalTrigger
    (..., 'no record of where the mission was held from; resuming would guess')`):
    the row says PAUSED and nothing else; every guess is a state the mission
    may never have been in — with it, an EXECUTING plan-less mission would look
    ready to dispatch."""
    actor = who()
    mid = _seed(db, actor, state='PAUSED')                    # held_from never recorded
    ms = missions(guards.MissionFacts())
    before, was = _n_events(db), _version(db, entities.Mission, mid)
    with pytest.raises(lifecycle.IllegalTrigger, match='resuming would guess'):
        db.writer.execute(ms.resume, dict(actor=who('system'), mission_id=mid, reason='go'))
    m = _row(db, entities.Mission, mid)
    assert (m.state, m.held_from, m.pause_batch_id) == ('PAUSED', None, None)
    assert _version(db, entities.Mission, mid) == was and _n_events(db) == before


def test_a_resume_only_ends_in_execution_when_the_hold_proves_it(db):
    """commands.py:477-480 (`trigger = {'PAUSED': 'resume', 'BLOCKED':
    'unblock'}.get(...)` — the IllegalTrigger for any other state) and :486
    (`then = 'redispatch' if held_from in PLAN_IN_FORCE else
    'redispatch_before_plan'`): a mission held from EXECUTING goes back to its
    plan; a mission held before its first plan starts over from UNDERSTANDING.
    Swapping the two either dispatches a plan that was never approved or drops
    approved work back to square one."""
    actor = who()
    held = _seed(db, actor, state='PAUSED', held_from='EXECUTING')
    out = db.writer.execute(missions().resume,
                            dict(actor=who('system'), mission_id=held, reason='go'))
    assert out['state'] == 'EXECUTING' and out['changed'] is True
    assert [(t['from'], t['to'], t['trigger']) for t in out['transitions']] == [
        ('PAUSED', 'RESUMED', 'resume'), ('RESUMED', 'EXECUTING', 'redispatch')]
    m = _row(db, entities.Mission, held)                     # the hold is forgotten on exit
    assert (m.held_from, m.pause_batch_id) == (None, None)

    before_plan = _seed(db, actor, state='BLOCKED', held_from='REASONING')
    out2 = db.writer.execute(missions().resume,
                             dict(actor=who('system'), mission_id=before_plan, reason='go'))
    assert out2['state'] == 'UNDERSTANDING'
    assert [(t['from'], t['to'], t['trigger']) for t in out2['transitions']] == [
        ('BLOCKED', 'RESUMED', 'unblock'), ('RESUMED', 'UNDERSTANDING', 'redispatch_before_plan')]

    running = _seed(db, actor, state='EXECUTING')             # not a hold at all
    with pytest.raises(lifecycle.IllegalTrigger, match="no 'resume' edge from EXECUTING"):
        db.writer.execute(missions().resume,
                          dict(actor=who('system'), mission_id=running, reason='go'))
    assert _row(db, entities.Mission, running).state == 'EXECUTING'


def test_a_pause_batch_holds_and_releases_exactly_its_own_missions(db):
    """commands.py:422-423 (the `if not running: return {'pause_batch_id':
    None, 'changed': False, ...}` of pause_all — pausing nothing records
    nothing) and 440-445 (resume_all), with the `resumable` filter it obeys at
    commands.py:71-72: `state == 'PAUSED' and m.pause_batch_id == b.id`). A
    batch that releases a mission paused on its own over-rules a person; one
    that leaves its own behind strands them; and a second call must
    change nothing at all."""
    actor = who('system')
    m1 = _seed(db, actor, state='EXECUTING')
    m2 = _seed(db, actor, state='EXECUTING')
    idle = _seed(db, actor, state='APPROVED')                  # not EXECUTING: not held
    ms = missions(guards.MissionFacts())
    out = db.writer.execute(ms.pause_all, dict(actor=actor))
    batch = out['pause_batch_id']
    assert out['changed'] is True and sorted(x['id'] for x in out['missions']) == sorted([m1, m2])
    assert _events(db, 'pause_batch.created') == [{'mission_ids': [m1, m2]}]
    assert _row(db, entities.Mission, idle).state == 'APPROVED'
    for mid in (m1, m2):
        m = _row(db, entities.Mission, mid)
        assert (m.state, m.held_from, m.pause_batch_id) == ('PAUSED', 'EXECUTING', batch)

    back = db.writer.execute(ms.resume_all, dict(actor=actor))
    assert (back['changed'], back['pause_batch_id']) == (True, batch)
    assert sorted(x['id'] for x in back['missions']) == sorted([m1, m2])
    assert _events(db, 'pause_batch.resumed') == [{'mission_ids': [m1, m2]}]
    for mid in (m1, m2):
        m = _row(db, entities.Mission, mid)
        assert (m.state, m.held_from, m.pause_batch_id) == ('EXECUTING', None, None)

    before = _n_events(db)
    twice = db.writer.execute(ms.resume_all, dict(actor=actor))
    assert (twice['changed'], twice['missions'], twice['pause_batch_id']) == (False, [], batch)
    assert _n_events(db) == before                            # an empty batch records nothing

    db.writer.execute(ms.pause, dict(actor=actor, mission_id=m1, reason='user pause'))
    assert _row(db, entities.Mission, m1).pause_batch_id is None
    assert db.writer.execute(ms.resume_all, dict(actor=actor))['changed'] is False
    assert _row(db, entities.Mission, m1).state == 'PAUSED'   # never the batch's to release


def test_pausing_nothing_records_nothing(db):
    """commands.py:422-423 (the `if not running` answer itself): a Pause all
    over no EXECUTING mission must leave no empty batch — the newest batch is
    what /v1/status reports and Resume all inverts, and an empty one makes both
    of them about nothing."""
    actor = who('system')
    _seed(db, actor, state='CREATED')
    _seed(db, actor, state='CREATED', priority=3)              # priority is not state
    _seed(db, actor, state='APPROVED')
    out = db.writer.execute(missions(guards.MissionFacts()).pause_all, dict(actor=actor))
    assert out == {'pause_batch_id': None, 'changed': False, 'missions': []}
    assert _all(db, entities.PauseBatch) == []


# ── the engine's step and the plan decision it records ─────────────────────

def test_advance_refuses_a_stale_version_and_a_quiet_point_moves_nothing(db):
    """commands.py:525-526 (`if expected_version is not None and
    expected_version != row.version: raise lifecycle.VersionConflict`) and
    540 (the `return _result(row, [], considered)` of a point with no open
    exit): an engine that overwrites a newer row loses a user's move, and a
    quiet pass that wrote an event would wake every reader forever."""
    actor = who()
    mid = _seed(db, actor, state='EXECUTING')
    ms = missions(guards.MissionFacts())
    before = _n_events(db)
    with pytest.raises(lifecycle.VersionConflict):
        db.writer.execute(ms.advance, dict(actor=actor, mission_id=mid,
                                           expected_version=7, reason='stale'))
    out = db.writer.execute(ms.advance, dict(actor=actor, mission_id=mid, reason='pass'))
    assert (out['changed'], out['state'], out['seq'], out['transitions']) == (
        False, 'EXECUTING', None, [])
    assert [c['trigger'] for c in out['considered']] == [
        'unrecoverable', 'task_failed_retryable', 'all_tasks_done']
    assert not any(c['taken'] for c in out['considered'])
    assert _n_events(db) == before
    approved = _seed(db, actor, state='APPROVED')              # not a decision point
    assert db.writer.execute(ms.advance,
                             dict(actor=actor, mission_id=approved))['considered'] == []


def test_advance_takes_the_first_exit_the_facts_allow_in_declared_order(db):
    """commands.py:528-539 (the `for trigger in DECISIONS.get(state, ())` loop
    with its first-`ok`-is-taken `return`): the order is the meaning. A retryable
    failure of a mission whose *other* tasks are done must go to REPLANNING, not
    be completed by `all_tasks_done`; a mission that is merely done reaches
    VERIFYING exactly once."""
    actor = who()
    done = _seed(db, actor, state='EXECUTING')
    f = guards.MissionFacts(plan_version=1, tasks=(
        guards.TaskFact('t1', 'code_change', 'SUCCEEDED'),))
    out = db.writer.execute(missions(f).advance, dict(actor=actor, mission_id=done))
    assert [c['taken'] for c in out['considered']] == [False, False, True]
    assert (out['state'], out['changed'], out['version']) == ('VERIFYING', True, 2)
    assert out['transitions'][0]['trigger'] == 'all_tasks_done'

    failed = _seed(db, actor, state='EXECUTING')
    f2 = guards.MissionFacts(plan_version=1, tasks=(
        guards.TaskFact('t1', 'code_change', 'SUCCEEDED'),
        guards.TaskFact('t2', 'code_change', 'FAILED', attempts=2, max_attempts=2,
                        failure_class='tooling')))
    out2 = db.writer.execute(missions(f2).advance, dict(actor=actor, mission_id=failed))
    assert [c['taken'] for c in out2['considered']] == [False, True]   # the loop stops at the hit
    assert (out2['state'], out2['transitions'][0]['trigger']) == (
        'REPLANNING', 'task_failed_retryable')


def test_the_engine_never_declares_a_mission_unrecoverable(db):
    """commands.py:318 + 531 (`declared_by=actor.kind if declared and actor is
    not None else None`, and `advance`'s snapshot taken without `declared`, so
    it is False): `advance` runs on the engine's clock and an ENGINE PASS
    is nobody's declaration of failure — only an explicit `fire` by a user
    device declares one. Drop the flag and every quiet engine pass over a
    denied policy becomes a FAILED mission."""
    actor = who()
    mid = _seed(db, actor, state='EXECUTING')                  # criteria, no plan
    ms = missions()                                             # the persisted snapshot
    out = db.writer.execute(ms.advance, dict(actor=actor, mission_id=mid))
    assert out['considered'][0] == {'trigger': 'unrecoverable', 'taken': False,
                                    'reason': 'nothing makes the mission unrecoverable'}
    before = _n_events(db)
    with pytest.raises(lifecycle.GuardFailed, match='nothing makes the mission unrecoverable'):
        db.writer.execute(ms.fire, dict(actor=who('system'), mission_id=mid,
                                        trigger='unrecoverable', reason='gave up'))
    assert _row(db, entities.Mission, mid).state == 'EXECUTING' and _n_events(db) == before
    declared = db.writer.execute(ms.fire, dict(actor=who(), mission_id=mid,
                                                trigger='unrecoverable', reason='gave up'))
    assert declared['state'] == 'FAILED' and declared['changed'] is True
    assert _row(db, entities.Mission, mid).state == 'FAILED'


@pytest.mark.parametrize('band, ceiling, taken', [
    (None, None, 'plan_needs_approval'),
    ('medium', None, 'plan_auto_approved'),
    ('high', None, 'plan_needs_approval'),
    ('high', 'high', 'plan_auto_approved')],
    ids=['no-band', 'under-ceiling', 'over-ceiling', 'ceiling-raised'])
def test_the_plan_decision_waits_on_what_the_rows_say_about_cost(db, band, ceiling, taken):
    """commands.py:230-232 (`cost_within_ceiling=None if band is None else
    (COST_BANDS.index(band) <= COST_BANDS.index(auto_approve_ceiling(m)))` and
    `auto_approve_ceiling`'s `.get('max_cost_band') or AUTO_APPROVE_CEILING`)
    seen through `advance` at PLANNING: a plan with no band yet, or one over
    the ceiling, is auto-approved — free — if this reads the comparison wrong,
    the rows, and the `decided_plan_version` recorded with the move
    (commands.py:334-335) is what stops the same plan being decided twice."""
    actor = who()
    over = {'state': 'PLANNING'}
    if ceiling is not None:
        over['resource_preferences'] = {'max_cost_band': ceiling}
    mid = _seed(db, actor, **over)
    pid = _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=mid,
                                           state='PROPOSED', plan_version=1,
                                           estimated_cost=band))
    _insert(db, actor, entities.Task(id=ids.new_id('task'), plan_id=pid, mission_id=mid,
                                     key='t1', title='T', kind='code_change',
                                     state='SUCCEEDED'))
    out = db.writer.execute(missions().advance, dict(actor=actor, mission_id=mid))
    assert out['transitions'][0]['trigger'] == taken
    assert out['state'] == ('APPROVED' if taken == 'plan_auto_approved'
                            else 'APPROVAL_REQUIRED')
    assert [c['taken'] for c in out['considered']] == (
        [True] if taken == 'plan_auto_approved' else [False, True])
    assert _row(db, entities.Mission, mid).decided_plan_version == 1     # recorded by _fire
    assert _all(db, entities.PolicyDecision) == []   # a script-y plan authorises nothing


def test_the_guard_snapshot_refuses_to_know_what_the_rows_do_not_hold(db):
    """commands.py:209-217 + 220-223 (`persisted_facts`: the `v.entity.revision ==
    m.integration_head` binding of D10, the latest-wins `checked[criterion] =
    v.entity.state`, the whole-plan binding `plan_id=plan.entity.id`, and the
    early `if plan is None: return MissionFacts(criteria=criteria)`): a verdict
    of another revision, or of the plan the mission no longer runs, counted as
    today's would complete a mission nobody verified."""
    actor = who()
    mid = _seed(db, actor, state='VERIFYING', integration_head=HEAD,
                success_criteria=({'text': 'it works', 'check': 'automatic'},))
    empty = _facts(db, mid)
    assert empty == {'plan_version': None, 'cost': None, 'review': None,
                     'tasks': [], 'criteria': [['automatic', None]]}   # fail closed
    pid = _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=mid,
                                           state='APPROVED', plan_version=1))

    def verdict(**over):
        row = dict(id=ids.new_id('verification'), subject=Ref('mission', mid),
                   verifier='generic_human', plan_id=pid, criterion=0,
                   revision=HEAD, state='PASSED')
        row.update(over)
        v = entities.Verification(**row)
        return _insert(db, actor, v, subject=Ref('verification', v.id),
                       type_='verification.created')

    verdict(revision=OTHER, state='PASSED')              # P13 D10: another revision
    assert _facts(db, mid)['criteria'] == [['automatic', None]]
    verdict()                                            # at the recorded head
    assert _facts(db, mid)['criteria'] == [['automatic', 'PASSED']]
    verdict(state='FAILED')                              # oldest first: the latest wins
    assert _facts(db, mid)['criteria'] == [['automatic', 'FAILED']]
    f = _facts(db, mid)
    assert (f['plan_version'], f['cost'], f['review'], f['tasks']) == (1, None, None, [])
    _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=mid,
                                     state='APPROVED', plan_version=2))
    # the plan in force is the highest version, and yesterday's verdicts stay
    # bound to the plan they were made for
    assert _facts(db, mid)['criteria'] == [['automatic', None]]


# ── what ends a mission, and on whose word ──────────────────────────────────

def test_nothing_completes_without_the_latest_review_of_the_plan_in_force(db):
    """commands.py:515-517 (`accept`'s `accepted` guard, judged on
    `f.review = reviews[-1].entity.state` at commands.py:229, bound to the plan
    in force at :225): the last
    verdict is the answer — an ACCEPTED review followed by a
    CHANGES_REQUESTED one is a mission under correction, not a completed one,
    and no review at all completes nothing however much earlier advice says so."""
    actor = who()
    mid = _seed(db, actor, state='REVIEWING')
    pid = _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=mid,
                                           state='APPROVED', plan_version=1))

    def review(state):
        r = entities.Review(id=ids.new_id('review'), mission_id=mid, plan_id=pid,
                            reviewer='judge', state=state)
        return _insert(db, actor, r, subject=Ref('review', r.id), type_='review.state_changed')

    ms = missions()                                        # the persisted review answer
    with pytest.raises(lifecycle.GuardFailed, match='no accepting review'):
        db.writer.execute(ms.accept, dict(actor=actor, mission_id=mid))
    review('CHANGES_REQUESTED')
    before = _n_events(db)
    with pytest.raises(lifecycle.GuardFailed, match='the latest is CHANGES_REQUESTED'):
        db.writer.execute(ms.accept, dict(actor=actor, mission_id=mid))
    assert _row(db, entities.Mission, mid).state == 'REVIEWING' and _n_events(db) == before
    review('ACCEPTED')
    out = db.writer.execute(ms.accept, dict(actor=actor, mission_id=mid))
    assert (out['state'], out['transitions'][0]['trigger']) == ('COMPLETED', 'accepted')
    assert _row(db, entities.Mission, mid).state == 'COMPLETED'

    later = _seed(db, actor, state='REVIEWING')            # accepted, then asked to change
    later_plan = _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=later,
                                                  state='APPROVED', plan_version=1))
    accepted = entities.Review(id=ids.new_id('review'), mission_id=later, plan_id=later_plan,
                               reviewer='judge', state='ACCEPTED')
    _insert(db, actor, accepted, subject=Ref('review', accepted.id),
            type_='review.state_changed')
    changes = entities.Review(id=ids.new_id('review'), mission_id=later, plan_id=later_plan,
                              reviewer='judge', state='CHANGES_REQUESTED')
    _insert(db, actor, changes, subject=Ref('review', changes.id),
            type_='review.state_changed')
    assert _facts(db, later)['review'] == 'CHANGES_REQUESTED'
    with pytest.raises(lifecycle.GuardFailed, match='the latest is CHANGES_REQUESTED'):
        db.writer.execute(ms.accept, dict(actor=actor, mission_id=later))
    assert _row(db, entities.Mission, later).state == 'REVIEWING'


def test_cancel_needs_an_edge_into_cancelled_and_withdraws_open_asks(db):
    """commands.py:495-499 (the `cancel` command's `_by_state(..., pick=lambda
    to, t: to == 'CANCELLED')` at :497 followed by `authorization.withdraw` at
    :498): EXECUTING
    has no edge into CANCELLED — pause first, because a running mission has
    something running in it — and a cancel that lands must leave no approval
    still decidable (D15), while leaving what was already decided alone."""
    actor = who()
    ms = missions()
    running = _seed(db, actor, state='EXECUTING')
    pending = entities.Approval(id=ids.new_id('approval'), subject=Ref('plan', ids.new_id('plan')),
                                kind='plan', action_hash='b' * 64, requested_by=actor.id,
                                mission_id=running, expires_at='2030-01-01T00:00:00Z')
    _insert(db, actor, pending)
    before = _n_events(db)
    with pytest.raises(lifecycle.IllegalTrigger, match="no 'cancel' edge from EXECUTING"):
        db.writer.execute(ms.cancel, dict(actor=actor, mission_id=running))
    assert _row(db, entities.Approval, pending.id).state == 'PENDING'   # refusal withdrew nothing
    assert _n_events(db) == before

    created = _seed(db, actor)                             # CREATED -> CANCELLED
    open_ask = _insert(db, actor, entities.Approval(
        id=ids.new_id('approval'), subject=Ref('plan', ids.new_id('plan')), kind='plan',
        action_hash='c' * 64, requested_by=actor.id, mission_id=created,
        expires_at='2030-01-01T00:00:00Z'))
    decided = _insert(db, actor, entities.Approval(
        id=ids.new_id('approval'), subject=Ref('plan', ids.new_id('plan')), kind='plan',
        action_hash='d' * 64, requested_by=actor.id, mission_id=created, state='APPROVED',
        expires_at='2030-01-01T00:00:00Z'))
    out = db.writer.execute(ms.cancel, dict(actor=actor, mission_id=created, reason='no'))
    assert (out['state'], out['transitions'][0]['trigger']) == ('CANCELLED', 'cancel')
    assert _row(db, entities.Approval, open_ask).state == 'REJECTED'
    assert _row(db, entities.Approval, open_ask).decided_by == actor.id
    assert _row(db, entities.Approval, decided).state == 'APPROVED'    # already decided


def test_request_changes_is_refused_where_no_edge_carries_it(db):
    """commands.py:505-507 (`pick=lambda to, t: t in ('request_changes',
    'changes_requested')`) with `_by_state`'s `if not found: raise
    lifecycle.IllegalTrigger` at commands.py:546-547): from EXECUTING no
    trigger named either exists —
    answered by guessing another trigger (a `cancel`, a `reject`) would send a
    running mission somewhere its work never agreed to go."""
    actor = who()
    mid = _seed(db, actor, state='EXECUTING')
    before = _n_events(db)
    with pytest.raises(lifecycle.IllegalTrigger, match="no 'request_changes' edge from EXECUTING"):
        db.writer.execute(missions().request_changes,
                          dict(actor=actor, mission_id=mid, reason='not yet'))
    assert _row(db, entities.Mission, mid).state == 'EXECUTING' and _n_events(db) == before
