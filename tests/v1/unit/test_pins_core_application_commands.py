"""T-831: hand mutants of `archeus/core/application/commands.py` that no existing test kills.

Every test names one condition of the module (file:line, with the verdict on all twenty, in the
T-831 report) and fails when that condition is inverted, removed or loosened. Conditions the
repo's own mutation suites already kill are listed as COVERED there and are not repeated here.

Same seams as the sibling unit tests of the application layer
(tests/v1/unit/test_gaps_core_application_verification.py, tests/v1/unit/test_execution_units.py):
the real database on the test's own `ARCHEUS_HOME` (the autouse fixture of tests/v1/conftest.py),
the real writer thread, the real mission machine, the P1 allow-all policy, a scripted guard
snapshot. No process, no network, no Windows API, no sleep, no clock, no locale-dependent text and
no path: every value compared here is one the test wrote itself.
"""

import hashlib
import itertools
import json

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.guards import MissionFacts, TaskFact
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

#: a sha256 hex digest: the only credential shape `register_device` accepts
HEX64 = 'a' * 64
#: the mission branch head a verification is recorded against (P13 D10)
HEAD = 'c' * 40
#: hashed once for the module (200k pbkdf2 rounds), so no test pays for it twice
PIN_RECORD = commands.hash_pin('482913')
#: the facts under which these guarded triggers pass, as in test_lifecycle.py
PASSING = {
    'plan_auto_approved': MissionFacts(
        plan_version=1, cost_within_ceiling=True,
        tasks=(TaskFact('t1', 'code_change', 'PENDING', action_classes=('write_repo',)),)),
}


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


def who(kind='user_device'):
    """A principal to act as: the only thing a caller may claim to be."""
    return Ref(kind, ids.new_id('principal'))


SYSTEM = who('system')


def scripted(facts=None):
    """`Missions` over the database with a fixed guard snapshot."""
    fixed = facts or MissionFacts()
    return commands.Missions(policy=ports.AllowAllPolicy(), facts=lambda tx, row: fixed)


class Recorder(commands.Missions):
    """The same object, keeping what each snapshot said declared it."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.seen = []

    def snapshot(self, tx, row, actor=None, declared=False):
        f = super().snapshot(tx, row, actor, declared)
        self.seen.append((row.entity.state, declared, f.declared_by))
        return f


def write(db, action, event_type, subject):
    """One writer transaction of its own: `action(tx)` and the event it owes (P2).

    `subject` is the (kind, id) the event is about, as every command's own event is."""
    def command(tx):
        out = action(tx)
        tx.append(new_event(event_type, Ref(subject[0], subject[1]), SYSTEM))
        return out

    return db.writer.execute(command, {})


def count(db, table):
    with db.read() as conn:
        return conn.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]


def payload(db, seq):
    with db.read() as conn:
        got = conn.execute('SELECT payload FROM events WHERE seq = ?', (seq,)).fetchone()
    return None if got is None else json.loads(got[0])


def entity(db, cls, entity_id):
    with db.read() as conn:
        row = rows.get(conn, cls, entity_id)
    return None if row is None else row.entity


def version(db, entity_id):
    with db.read() as conn:
        return rows.get(conn, entities.Mission, entity_id).version


def facts_of(db, mission_id):
    """`persisted_facts` for one mission, over a read snapshot (it only reads)."""
    class Tx:
        conn = None

        def where(self, cls, **eq):
            return rows.where(self.conn, cls, **eq)

    with db.read() as conn:
        tx = Tx()
        tx.conn = conn
        return commands.persisted_facts(tx, rows.get(conn, entities.Mission, mission_id))


def mission_row(**prefs):
    """A Mission as a row would hold it, for what `auto_approve_ceiling` reads."""
    return entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                            title='t', objective='o', resource_preferences=prefs or None)


def new_mission(db, *, criteria=0, prefs=None, to='CREATED'):
    """A mission on the database, in `to` (CREATED or PLANNING), through the real commands."""
    actor = who()
    out = db.writer.execute(commands.create_mission, {
        'actor': actor, 'title': 'M', 'objective': 'o',
        'success_criteria': [{'text': 'it works', 'check': 'automatic'}] * criteria})
    mid = out['id']
    if prefs is not None:
        write(db, lambda tx: tx.update(entities.Mission, mid, {'resource_preferences': prefs},
                                       actor=SYSTEM),
              'mission.updated', ('mission', mid))
    if to != 'CREATED':
        for trigger in ('start', 'understood', 'context_ready', 'reasoned'):
            db.writer.execute(scripted().fire, {'actor': actor, 'mission_id': mid,
                                                'trigger': trigger, 'reason': 'test'})
    return mid


def executing(db, mid):
    """PLANNING -> APPROVED -> EXECUTING, then the mission is running."""
    for trigger in ('plan_auto_approved', 'dispatch'):
        db.writer.execute(scripted(PASSING.get(trigger)).fire,
                          {'actor': who(), 'mission_id': mid, 'trigger': trigger,
                           'reason': 'test'})
    return mid


def add_plan(db, *, mission_id, plan_version=1, cost='medium', tasks=()):
    plan = entities.Plan(id=ids.new_id('plan'), mission_id=mission_id,
                         plan_version=plan_version, estimated_cost=cost, state='PROPOSED')
    write(db, lambda tx: tx.insert(plan, actor=SYSTEM), 'plan.created', ('plan', plan.id))
    for key in tasks:
        task = entities.Task(id=ids.new_id('task'), plan_id=plan.id, mission_id=mission_id,
                             key=key, title=key, kind='code_change',
                             action_classes=('write_repo',), state='PENDING')
        write(db, lambda tx, t=task: tx.insert(t, actor=SYSTEM), 'task.created',
              ('task', task.id))
    return plan


def set_head(db, mission_id, revision=HEAD):
    """The branch head the mission's criteria are verified against (P13 D10)."""
    write(db, lambda tx: tx.update(entities.Mission, mission_id, {'integration_head': revision},
                                   actor=SYSTEM, bump=False),
          'mission.updated', ('mission', mission_id))


def verify(db, mission_id, plan, *, state, criterion=0, revision=HEAD, subject=None):
    """A recorded verdict for one criterion of `plan`, as the guard reads it."""
    v = entities.Verification(id=ids.new_id('verification'),
                              subject=subject or Ref('mission', mission_id), verifier='code',
                              plan_id=plan.id, criterion=criterion, revision=revision, state=state)
    write(db, lambda tx, e=v: tx.insert(e, actor=SYSTEM), 'verification.created',
          ('verification', v.id))
    return v


#: `tokens.token_hash` is unique, so each device of a test gets its own digest
_TOKENS = itertools.count()


def device(db, *, slot=None, token=None, platform='tui'):
    """A device issued by the real command, its credential a sha256 hex digest."""
    if token is None:
        token = hashlib.sha256(str(next(_TOKENS)).encode()).hexdigest()
    return db.writer.execute(commands.register_device, {
        'actor': SYSTEM, 'name': 'shell', 'platform': platform,
        'token_hash': token, 'scopes': ('control',), 'supersede': slot})


# ── the step-up PIN, the device credential and its kind (commands.py:110, :133, :147) ──

@pytest.mark.parametrize('proof', [None, '', 482913, b'482913', ['482913'], 482913.0],
                         ids=['none', 'empty', 'int', 'bytes', 'list', 'float'])
def test_a_proof_that_is_not_a_string_never_matches_the_record(proof):
    """commands.py:110 `isinstance(pin, str) and pin`: without the type test a
    non-string reaches `.encode()` and the step-up check raises instead of refusing."""
    assert commands.pin_matches(PIN_RECORD, proof) is False


@pytest.mark.parametrize('record', [None, ''], ids=['none', 'empty'])
def test_a_client_with_no_pin_record_refuses_every_proof(record):
    """commands.py:110 `record and`: a missing record authenticates nothing."""
    assert commands.pin_matches(record, '482913') is False


@pytest.mark.parametrize('bad', ['', HEX64[:-1], HEX64.upper(), 'z' * 64, HEX64 + '0'],
                         ids=['empty', 'short', 'upper', 'not-hex', 'long'])
def test_a_credential_that_is_not_a_sha256_hex_digest_issues_no_device(db, bad):
    """commands.py:133 `entities._HEX64.fullmatch(token_hash)`: a live credential
    the auth layer can never match (or cannot match uniquely) must not be issuable."""
    with pytest.raises(ValueError):
        device(db, token=bad)
    assert (count(db, 'devices'), count(db, 'tokens'), count(db, 'principals')) == (0, 0, 0)


def test_a_sha256_hex_digest_issues_the_device_it_was_issued_to(db):
    """The other half of commands.py:133: what the check lets through is unchanged."""
    out = device(db)
    assert entity(db, entities.Device, out['device_id']).state == 'ACTIVE'
    assert count(db, 'tokens') == 1


def test_the_client_kind_comes_from_the_platform_that_registered(db):
    """commands.py:147 `client_type or ('cli' if platform == 'tui' else 'spa')`: the
    kind is what a step-up PIN is asked for (p15), so a terminal client recorded as
    a browser is a shell that is never asked for one."""
    assert entity(db, entities.Device, device(db, platform='tui')['device_id']).client_type == 'cli'
    assert entity(db, entities.Device, device(db, platform='web')['device_id']).client_type == 'spa'


# ── the supersede slot (commands.py:137) ─────────────────────────────────────

def test_a_superseding_launch_never_revokes_a_client_that_is_already_revoked(db):
    """commands.py:137 `and r.entity.state == 'ACTIVE'`: `revoke` is legal only out
    of ACTIVE (states.py), so a slot that counts a REVOKED row raises and takes the
    new client's credential down with it."""
    first, second = device(db, slot='desktop shell'), device(db, slot='desktop shell')
    assert entity(db, entities.Device, first['device_id']).state == 'REVOKED'
    third = device(db, slot='desktop shell')
    assert entity(db, entities.Device, third['device_id']).state == 'ACTIVE'
    assert entity(db, entities.Device, second['device_id']).state == 'REVOKED'


# ── the presence trace (commands.py:169, :172) ───────────────────────────────

def test_a_trace_of_a_client_that_does_not_exist_writes_no_event(db):
    """commands.py:169 `tx.get(entities.Device, device_id) is None`: the trace is
    the durable audit record of presence; one about an unknown client is a forgery."""
    with pytest.raises(lifecycle.NotFound):
        db.writer.execute(commands.record_connection, {
            'actor': who(), 'device_id': ids.new_id('device'),
            'connection_id': 'conn-1', 'opened': True})
    assert count(db, 'events') == 0


def test_only_the_closing_trace_records_why(db):
    """commands.py:172 `if not opened`: the reason is why a stream ended; on the
    opening it is a field no caller fills, and an absent one would read as a fact."""
    did = device(db)['device_id']
    opened = db.writer.execute(commands.record_connection, {
        'actor': who(), 'device_id': did, 'connection_id': 'conn-1',
        'opened': True, 'reason': 'the client asked'})
    closed = db.writer.execute(commands.record_connection, {
        'actor': who(), 'device_id': did, 'connection_id': 'conn-1',
        'opened': False, 'reason': 'client_gone'})
    assert payload(db, opened['seq']) == {'connection_id': 'conn-1'}
    assert payload(db, closed['seq']) == {'connection_id': 'conn-1', 'reason': 'client_gone'}


# ── the snapshot the mission guards are judged on
# (commands.py:188, 196, 211, 212, 213, 216, 229, 230, 231)

def test_the_cost_ceiling_is_medium_until_the_mission_says_otherwise():
    """commands.py:188 `or AUTO_APPROVE_CEILING`: without the default a mission
    that never chose a ceiling has none, and the plan gate reads that as unknown."""
    assert commands.auto_approve_ceiling(mission_row()) == 'medium'
    assert commands.auto_approve_ceiling(mission_row(max_cost_band='high')) == 'high'


def test_a_mission_with_no_active_plan_has_no_tasks_and_no_cost_answer(db):
    """commands.py:216 `if plan is None: return MissionFacts(criteria=criteria)`:
    fail closed — no tasks, no plan version, cost unknown (None, never True)."""
    f = facts_of(db, new_mission(db, criteria=1))
    assert (f.plan_version, f.tasks, f.cost_within_ceiling, f.review) == (None, (), None, None)
    assert [c.verification for c in f.criteria] == [None]


def test_the_active_plan_is_the_highest_version_however_it_was_stored(db):
    """commands.py:196 `max(..., key=lambda r: r.entity.plan_version, default=None)`:
    a replan is a new row, so the plan in force is the highest version, not the first
    row of the table and not an error when the mission has no plan at all."""
    mid = new_mission(db)
    add_plan(db, mission_id=mid, plan_version=1, tasks=('t1',))
    add_plan(db, mission_id=mid, plan_version=3, tasks=('t3',))
    with db.read() as conn:
        assert commands.active_plan(conn, mid).entity.plan_version == 3
        assert commands.active_plan(conn, ids.new_id('mission')) is None


@pytest.mark.parametrize('band, prefs, want', [
    ('medium', None, True),
    ('high', None, False),
    ('high', {'max_cost_band': 'high'}, True),
    ('low', {'max_cost_band': 'medium'}, True),
    ('high', {'max_cost_band': 'low'}, False),
    (None, {'max_cost_band': 'high'}, None),
], ids=['at-ceiling', 'over-ceiling', 'raised-to-band', 'raised-above', 'lowered-under', 'no-band'])
def test_the_cost_band_is_under_the_ceiling_only_up_to_it(db, band, prefs, want):
    """commands.py:230 `None if band is None else COST_BANDS.index(band) <=
    COST_BANDS.index(ceiling)`: `<` instead of `<=` sends a plan exactly at the
    ceiling to a human, and a missing band answered anything but None is a vacuous pass."""
    mid = new_mission(db, criteria=1, prefs=prefs)
    add_plan(db, mission_id=mid, plan_version=1, cost=band, tasks=('t1',))
    assert facts_of(db, mid).cost_within_ceiling is want


def test_the_latest_verification_of_a_criterion_is_the_one_that_counts(db):
    """commands.py:213 `checked[v.entity.criterion] = v.entity.state` over rows read
    oldest first: a criterion is its latest verification, so a PASSED that a later
    FAILED overturned must not be what the guard reads."""
    mid = new_mission(db, criteria=1)
    plan = add_plan(db, mission_id=mid, plan_version=1, tasks=('t1',))
    set_head(db, mid)
    for state in ('PASSED', 'FAILED'):
        verify(db, mid, plan, state=state)
    assert [c.verification for c in facts_of(db, mid).criteria] == ['FAILED']


def test_a_verification_of_another_mission_checks_no_criterion(db):
    """commands.py:211 `v.entity.subject == Ref('mission', m.id)`: verdicts of every
    mission are recorded against the same plan rows; only this mission's own verdict
    on a criterion is what its guard reads."""
    mid = new_mission(db, criteria=1)
    other = new_mission(db, criteria=1)
    plan = add_plan(db, mission_id=mid, plan_version=1, tasks=('t1',))
    set_head(db, mid)
    set_head(db, other)
    verify(db, other, plan, state='PASSED')
    assert [c.verification for c in facts_of(db, mid).criteria] == [None]
    verify(db, mid, plan, state='PASSED')
    assert [c.verification for c in facts_of(db, mid).criteria] == ['PASSED']


def test_a_verification_recorded_for_another_revision_checks_no_criterion(db):
    """commands.py:212 `v.entity.revision == m.integration_head`: a criterion was
    checked against a commit of the branch; the same verdict for a commit that is
    not the mission's head says nothing about the code that would be integrated."""
    mid = new_mission(db, criteria=1)
    plan = add_plan(db, mission_id=mid, plan_version=1, tasks=('t1',))
    set_head(db, mid)
    verify(db, mid, plan, state='PASSED', revision='b' * 40)
    assert [c.verification for c in facts_of(db, mid).criteria] == [None]
    verify(db, mid, plan, state='PASSED')
    assert [c.verification for c in facts_of(db, mid).criteria] == ['PASSED']


def test_the_review_the_guard_reads_is_the_latest_one_of_the_plan_in_force(db):
    """commands.py:229 `reviews[-1].entity.state if reviews else None`: the first
    review of a plan is not its verdict once a later one has been recorded."""
    mid = new_mission(db, criteria=1)
    plan = add_plan(db, mission_id=mid, plan_version=1, tasks=('t1',))
    for verdict, state in (('reject', 'REJECTED'), ('accept', 'ACCEPTED')):
        r = entities.Review(id=ids.new_id('review'), mission_id=mid, reviewer='agent',
                            verdict=verdict, plan_id=plan.id, state=state)
        write(db, lambda tx, e=r: tx.insert(e, actor=SYSTEM), 'review.state_changed',
              ('review', r.id))
    assert facts_of(db, mid).review == 'ACCEPTED'


# ── what a move reports (commands.py:269) ────────────────────────────────────

def test_a_move_of_two_events_reports_the_seq_of_the_last_one(db):
    """commands.py:269 `'seq': events[-1].seq if events else None`: a client told
    the seq of the first event of `resume` stops reading before the redispatch and
    acts on a mission it never saw take that step."""
    mid = executing(db, new_mission(db, to='PLANNING'))
    ms = scripted()
    db.writer.execute(ms.pause, {'actor': who(), 'mission_id': mid})
    out = db.writer.execute(ms.resume, {'actor': who(), 'mission_id': mid})
    assert [t['trigger'] for t in out['transitions']] == ['resume', 'redispatch']
    assert out['seq'] == out['transitions'][-1]['seq'] > out['transitions'][0]['seq']
    assert out['changed'] is True


# ── who may declare what (commands.py:318) ───────────────────────────────────

def test_only_an_explicit_request_declares_something(db):
    """commands.py:318 `actor.kind if declared and actor is not None else None`:
    with `declared` ignored the engine's own step declares as much as a user's,
    and with the None test dropped a snapshot taken for nobody raises."""
    mid = new_mission(db)
    ms = Recorder(policy=ports.AllowAllPolicy(), facts=lambda tx, row: MissionFacts())
    caller = who()

    def probe(tx, *, actor, mission_id):
        row = rows.get(tx.conn, entities.Mission, mission_id)
        return (ms.snapshot(tx, row, actor, True).declared_by,
                ms.snapshot(tx, row, actor, False).declared_by,
                ms.snapshot(tx, row, None, True).declared_by)

    asked = db.writer.execute(probe, {'actor': caller, 'mission_id': mid})
    assert list(asked) == [caller.kind, None, None]


def test_the_engine_stepping_a_mission_declares_nothing(db):
    """The same condition through the command: `advance` judges the mission with
    `declared=False`, so nothing it tries may rest on a declaration."""
    mid = executing(db, new_mission(db, to='PLANNING'))
    ms = Recorder(policy=ports.AllowAllPolicy(),
                  facts=lambda tx, row: MissionFacts(
                      plan_version=1,
                      tasks=(TaskFact('t1', 'code_change', 'RUNNING',
                                      action_classes=('write_repo',)),)))
    db.writer.execute(ms.advance, {'actor': who(), 'mission_id': mid})
    assert [s for s in ms.seen if s[0] == 'EXECUTING'] == [('EXECUTING', False, None)]


# ── priority (commands.py:451, :455) ─────────────────────────────────────────

@pytest.mark.parametrize('priority', [True, False, 1.0, '7', None],
                         ids=['true', 'false', 'float', 'digits', 'none'])
def test_a_priority_that_is_not_an_integer_is_refused(db, priority):
    """commands.py:451 `or isinstance(priority, bool)`: `True` is an `int`, so a
    client that sends a flag silently orders its mission at 1."""
    mid = new_mission(db)
    with pytest.raises(ValueError):
        db.writer.execute(scripted().reprioritise, {'actor': who(), 'mission_id': mid,
                                                    'priority': priority})
    assert entity(db, entities.Mission, mid).priority == 0


def test_a_mission_that_has_ended_is_not_reprioritised(db):
    """commands.py:455 `if m.state in states.terminal('mission')`: a finished
    mission has no dispatch to order, and writing it stamps a new version and a
    `mission.updated` event a client is told to follow."""
    mid = new_mission(db)
    db.writer.execute(scripted().cancel, {'actor': who(), 'mission_id': mid})
    before = entity(db, entities.Mission, mid)
    with pytest.raises(lifecycle.IllegalTrigger):
        db.writer.execute(scripted().reprioritise, {'actor': who(), 'mission_id': mid,
                                                    'priority': 5})
    assert entity(db, entities.Mission, mid) == before
    assert count(db, 'events') == 2                     # created and cancelled, nothing more


# ── advance's own optimistic concurrency (commands.py:525) ───────────────────

def test_an_advance_submitted_against_a_version_that_is_gone_is_a_conflict(db):
    """commands.py:525 `expected_version is not None and expected_version != row.version`:
    `advance` gathers its facts against the row it read, so a step submitted against a
    version that has gone must not judge a mission that is no longer at that version."""
    mid = new_mission(db)
    v = version(db, mid)
    db.writer.execute(scripted().fire, {'actor': who(), 'mission_id': mid, 'trigger': 'start',
                                        'reason': 'someone else moved it'})
    with pytest.raises(lifecycle.VersionConflict):
        db.writer.execute(scripted().advance, {'actor': who(), 'mission_id': mid,
                                               'expected_version': v})
    assert entity(db, entities.Mission, mid).state == 'UNDERSTANDING'
