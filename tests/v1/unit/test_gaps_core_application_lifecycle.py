"""T-750: the highest-risk uncovered branches of
`archeus/core/application/lifecycle.py` — denial and fail-closed paths first
(illegal trigger, machine-ending trigger, guard refusal, audit-trail and
stateless-class refusals, optimistic-concurrency conflict), then the boundary
values of `expected_version`, then the idempotency/replay of one fire command.
The style and the seeded-database fixture are copied from
tests/v1/unit/test_gaps_core_application_executions.py and
tests/v1/unit/test_gaps_core_domain_guards.py. Pure functions and the real
writer only: no OS calls, no processes, no network, nothing Windows-specific.
"""

import pytest

from archeus.core.application import lifecycle, queries
from archeus.core.domain import entities, ids, states
from archeus.core.domain.events import new_event
from archeus.core.domain.guards import IntegrationFacts, MissionFacts
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

Z = '2026-01-01T00:00:00.000Z'


def _user():
    return Ref('user_device', ids.new_id('principal'))


def _mission(state='CREATED', **kw):
    return entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                            title='M', objective='o', state=state, **kw)


def _task(state='SUCCEEDED', integration_state='PENDING', **kw):
    return entities.Task(id=ids.new_id('task'), plan_id=ids.new_id('plan'),
                         mission_id=ids.new_id('mission'), key='t', title='T',
                         kind='code_change', state=state,
                         integration_state=integration_state, **kw)


def _row(entity, version=1):
    """A Row as P2 hands it to `check`/`fire`, without a database: the version
    is the row's optimistic-concurrency version, not any entity field."""
    return rows.Row(entity, version, Z, Z, ids.new_id('principal'),
                    ids.new_id('principal'))


class _Tx:
    """The two seams of the writer's Tx that `fire` touches, recorded."""

    def __init__(self, row):
        self.row = row
        self.transitions = []

    def get(self, cls, entity_id):
        return self.row if entity_id == self.row.entity.id else None

    def transition(self, cls, entity_id, to, **kw):
        self.transitions.append((cls, entity_id, to, kw))
        return ('ROW', 'EVENT')


def _world(*objs):
    """A real database with *objs* inserted (one command, one event to record
    them, exactly like the executions gap tests). Referenced rows a foreign
    key needs (a task's mission and plan, a device's principal) are seeded
    alongside, in insert order."""
    extra, seen = [], {o.id for o in objs}
    for o in objs:
        if isinstance(o, entities.Task):
            for ref in (entities.Mission(id=o.mission_id,
                                         workspace_id=ids.GLOBAL_WORKSPACE,
                                         title='M', objective='o', state='EXECUTING'),
                        entities.Plan(id=o.plan_id, mission_id=o.mission_id,
                                      state='APPROVED')):
                if ref.id not in seen:
                    seen.add(ref.id)
                    extra.append(ref)
        elif isinstance(o, entities.Device) and o.principal_id not in seen:
            seen.add(o.principal_id)
            extra.append(entities.Principal(id=o.principal_id, kind='user_device'))
    db = Database.open()
    user = _user()
    mid = next((o.id for o in objs if isinstance(o, entities.Mission)),
               ids.new_id('mission'))

    def run(tx, **_):
        for o in extra + list(objs):
            tx.insert(o, actor=user)
        tx.append(new_event('mission.updated', Ref('mission', mid), user, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return db, user


def _current(db, cls, id_):
    with db.read() as r:
        return rows.get(r, cls, id_)


def _events(db, type_, subject_id=None):
    with db.read() as r:
        return [ev for ev in queries.events(r)
                if ev['type'] == type_
                and (subject_id is None or ev['subject']['id'] == subject_id)]


def _fire(tx, cls, entity_id, trigger, actor, **kw):
    return lifecycle.fire(tx, cls, entity_id, trigger, actor=actor, **kw)


# ── resolve: only a real edge of the machine is an answer ────────────────────

def test_resolve_answers_with_the_edge_and_the_guard_it_names():
    """lifecycle.py:64 (`return to, g`): the pair the whole transition is
    built from. Dropping the `g` (always None) would hand every guarded edge
    to the primitive unproven — which the primitive refuses — and dropping
    the edge match would make the legal moves illegal."""
    assert lifecycle.resolve('mission', 'CREATED', 'start') == ('UNDERSTANDING', None)
    assert lifecycle.resolve('mission', 'APPROVAL_REQUIRED', 'approve') == ('APPROVED',
                                                                            'approve')
    assert lifecycle.resolve('plan', 'DRAFT', 'ready') == ('PROPOSED', 'ready')
    assert lifecycle.resolve('integration', 'PENDING', 'task_verified') == ('MERGING',
                                                                             'task_verified')


@pytest.mark.parametrize('machine, frm, trigger', [
    ('device', 'PAIRING', 'code_expired'),        # the one END edge with a trigger
    ('mission', 'COMPLETED', None),               # the unlabelled `--> [*]`
], ids=['device-expired', 'terminal-none'])
def test_resolve_refuses_a_trigger_that_ends_the_machine(machine, frm, trigger):
    """lifecycle.py:60-63: an edge to END removes the row; taking it as a
    state change (removal of this branch would resolve it to `to='[*]'` and
    `fire` would try to write the pseudo-state into a real column)."""
    with pytest.raises(lifecycle.IllegalTrigger) as e:
        lifecycle.resolve(machine, frm, trigger)
    assert 'ends the machine' in str(e.value)
    assert e.value.trigger == trigger


@pytest.mark.parametrize('trigger', [None, '', 'Start', 'nope', 42],
                         ids=['none', 'empty', 'wrongcase', 'unknown', 'number'])
def test_resolve_refuses_what_is_not_a_trigger_at_all(trigger):
    """lifecycle.py:65 (the fall-through raise): a hostile or mis-cased value
    is an IllegalTrigger naming the machine's refusal, never a TypeError and
    never an accidental match (`'Start'` must not match 'start' — that would
    fire the edge on a case-insensitive platform)."""
    with pytest.raises(lifecycle.IllegalTrigger) as e:
        lifecycle.resolve('mission', 'CREATED', trigger)
    assert str(e.value) == 'mission: CREATED -> None: no %r edge from CREATED' % trigger
    assert e.value.trigger == trigger


# ── IllegalTrigger: what it may and may not claim about `to` ─────────────────

def test_illegal_trigger_names_the_single_place_the_trigger_leads():
    """lifecycle.py:39 (the len(dests)==1 side): the 422 tells the caller
    where the trigger does live (PAUSED) so the UI can offer the right state;
    a lost `== 1` or a mis-set `to` sends it pointing nowhere."""
    e = lifecycle.IllegalTrigger('mission', 'CREATED', 'pause')
    assert (e.machine, e.frm, e.to, e.trigger) == ('mission', 'CREATED', 'PAUSED', 'pause')
    assert str(e) == "mission: CREATED -> PAUSED: no 'pause' edge from CREATED"


def test_illegal_trigger_claims_nothing_for_an_unknown_trigger_or_machine():
    """lifecycle.py:38-39: the `machine in states.MACHINES` guard — dropped,
    a machine that has no edge table (harness is a STATE_SETS entry) would
    crash the refusal itself with KeyError; and a trigger no edge carries has
    no single destination to name."""
    e = lifecycle.IllegalTrigger('harness', 'AVAILABLE', 'break')     # must not raise
    assert (e.to, e.trigger) == (None, 'break')
    assert lifecycle.IllegalTrigger('mission', 'CREATED', 'nope').to is None


def test_illegal_trigger_stays_silent_when_the_trigger_leads_several_places(monkeypatch):
    """lifecycle.py:39 (the multi-destination side): with two destinations
    `to` must be None — turning `== 1` into `>= 1` would report an arbitrary
    one of them as if the machine had promised it."""
    monkeypatch.setattr(states, 'MACHINES', states.MACHINES + ('fakemachine',))
    monkeypatch.setitem(states._EDGES, 'fakemachine',
                        (('A', 'B', 'go'), ('A', 'C', 'go'), ('A', 'D', 'solo')))
    monkeypatch.setattr(states, 'TABLE', states.TABLE + (
        ('fakemachine', 'A', 'B', 'go', None), ('fakemachine', 'A', 'C', 'go', None),
        ('fakemachine', 'A', 'D', 'solo', None)))
    assert lifecycle.IllegalTrigger('fakemachine', 'A', 'go').to is None
    assert lifecycle.IllegalTrigger('fakemachine', 'A', 'solo').to == 'D'


# ── load: no row, no transition, and nothing before it ───────────────────────

def test_fire_refuses_a_class_that_has_no_state_machine_before_anything_else():
    """lifecycle.py:98-99, checked BEFORE the reason check at 100: a class
    with no `_STATE` (PauseBatch) is a programming error (TypeError), and
    even an empty reason must not pre-empt it — swapping the two lines turns
    every such call into a misleading ValueError about the audit trail."""
    with pytest.raises(TypeError, match='has no state machine'):
        lifecycle.fire(None, entities.PauseBatch, ids.new_id('pause_batch'), 'start',
                       actor=_user(), reason='')


@pytest.mark.parametrize('reason', [None, '', '   ', 1],
                         ids=['none', 'empty', 'blank', 'number'])
def test_fire_never_moves_a_row_without_a_reason(reason):
    """lifecycle.py:100-101 (`isinstance(reason, str) and reason.strip()`),
    checked before the row is even loaded: an unrecorded reason is an audit
    hole; dropping the isinstance half would let a non-str reason into the
    event payload, and moving this after `load` changes which error a caller
    with BOTH a missing row and a missing reason gets (ValueError, here)."""
    with pytest.raises(ValueError, match='needs a reason'):
        lifecycle.fire(None, entities.Mission, ids.new_id('mission'), 'start',
                       actor=_user(), reason=reason)


def test_fire_and_load_refuse_an_id_that_is_not_there_and_write_nothing():
    """lifecycle.py:70-71 (`if row is None: raise NotFound`) — including the
    empty-string id (a hostile API body) and the missing row reached through
    `fire` before any guard or version is looked at (lifecycle.py:103 runs
    before 104: the row's absence outranks a stale expected_version)."""
    db, user = _world(_mission())
    try:
        gone = ids.new_id('mission')
        with pytest.raises(lifecycle.NotFound):
            db.writer.execute(lambda tx: lifecycle.load(tx, entities.Mission, gone), {})
        with pytest.raises(lifecycle.NotFound):
            db.writer.execute(lambda tx: lifecycle.load(tx, entities.Mission, ''), {})
        with pytest.raises(lifecycle.NotFound) as e:
            db.writer.execute(lambda tx: _fire(tx, entities.Mission, gone, 'start', user,
                                               reason='go', expected_version=99), {})
        assert e.value.args[0] == gone                         # NotFound names the row
        assert _events(db, 'mission.state_changed') == []
    finally:
        db.close()


# ── the version gate: the numbers it refuses, boundaries first ───────────────

@pytest.mark.parametrize('expected', [0, 2, 99], ids=['zero', 'next', 'far'])
def test_fire_refuses_a_version_that_is_not_the_row_s(expected):
    """lifecycle.py:104-105: `expected_version is not None and !=` — the
    `is not None` half means 0 is a real expectation, not "no expectation"
    (a truthiness test would fire on 0); a lost `!=` (or whole branch) lets a
    stale writer overwrite a move nobody saw. The row and the event trail
    must be untouched by the refusal."""
    m = _mission()
    db, user = _world(m)
    try:
        with pytest.raises(lifecycle.VersionConflict) as e:
            db.writer.execute(lambda tx: _fire(tx, entities.Mission, m.id, 'start', user,
                                               reason='go',
                                               expected_version=expected), {})
        assert (e.value.entity_id, e.value.expected, e.value.current) == (m.id, expected, 1)
        row = _current(db, entities.Mission, m.id)
        assert (row.entity.state, row.version) == ('CREATED', 1)
        assert _events(db, 'mission.state_changed') == []
    finally:
        db.close()


# ── check: the guard is judged on THIS row, at THIS version ─────────────────

def test_check_never_gathers_a_snapshot_the_edge_cannot_read():
    """lifecycle.py:82-83 (`if g is None: return to, None`) and the laziness
    contract at 84-85: an unguarded edge, and an illegal one, must not run
    the facts callable at all (a snapshot is gathered only for a guard to
    read — firing it otherwise costs a full read-set per legal no-op)."""
    def boom(row):
        raise AssertionError('facts gathered for an edge with no guard')
    assert lifecycle.check('mission', _row(_mission()), 'start', boom) == ('UNDERSTANDING',
                                                                            None)
    with pytest.raises(lifecycle.IllegalTrigger):
        lifecycle.check('mission', _row(_mission()), 'approve', boom)


def test_check_gathers_the_facts_once_from_the_row_and_binds_the_verdict():
    """lifecycle.py:84-86: `if callable(facts): facts = facts(row)` — called
    once, with THAT row — and `version=row.version` inside evaluate: a
    GuardResult not bound to the row's version could later author a proof
    for a different read of the row (the primitive re-checks exactly this
    binding). Passing the row itself instead of calling would AttributeError
    on the MissionFacts fields; a `version=None` slip fails the result bind."""
    m = _mission('APPROVAL_REQUIRED')
    row = _row(m, version=3)
    seen = []

    def facts(r):
        seen.append(r)
        return MissionFacts(plan_version=1, plan_approval='APPROVED')
    to, result = lifecycle.check('mission', row, 'approve', facts)
    assert to == 'APPROVED'
    assert seen == [row]
    assert (result.guard, result.passed, result.entity_id, result.version) == (
        'approve', True, m.id, 3)


def test_check_refuses_when_the_guard_refuses_and_binds_the_whole_refusal():
    """lifecycle.py:87-88 (the `not result.passed` raise) and GuardFailed's
    __init__ at 47-51: machine, frm, to, trigger and the GuardResult must
    survive to the 422 — dropping the raise would let a refused guard build
    a proof anyway, and dropping `result.passed` (always True) would refuse
    every edge."""
    m = _mission('APPROVAL_REQUIRED')
    row = _row(m, version=7)
    with pytest.raises(lifecycle.GuardFailed) as e:
        lifecycle.check('mission', row, 'approve', MissionFacts(plan_version=1))
    g = e.value
    assert (g.machine, g.frm, g.to, g.trigger) == ('mission', 'APPROVAL_REQUIRED',
                                                   'APPROVED', 'approve')
    assert (g.result.passed, g.result.version) == (False, 7)
    assert str(g) == ('mission: APPROVAL_REQUIRED -> APPROVED: guard approve refused: '
                      'no approval of plan v1 is APPROVED (none requested)')


def test_check_moves_the_secondary_machine_of_the_row_not_the_main_one():
    """lifecycle.py:79-80 (`row.entity.machine_field(machine)[0]`): with
    machine='integration' the state read and written is `integration_state`
    — hard-wiring the main field would fire the integration edge against the
    task's main state (PENDING here) and merge unverified work or fail 500."""
    task = _task(state='SUCCEEDED', integration_state='MERGING')
    good = IntegrationFacts(task_state='SUCCEEDED', plan_in_force=True,
                            verified_revision='rev-a', revision='rev-a')
    assert lifecycle.check('integration', _row(task), 'fast_forward_or_clean',
                           lambda row: pytest.fail('unguarded')) == ('MERGED', None)
    to, result = lifecycle.check('integration', _row(_task()), 'task_verified', good)
    assert (to, result.passed, result.guard) == ('MERGING', True, 'task_verified')


# ── fire: the proof, and what the primitive is handed ────────────────────────

def test_fire_binds_the_proof_to_the_row_and_hands_the_primitive_its_version():
    """lifecycle.py:107-114: the TransitionProof (entity, version, frm, to,
    trigger, guard) and `expected_version=row.version` — NOT the caller's.
    Leaking the caller's value (or None) would let the primitive skip its
    half of the check; a `guard=None` slip on a guarded edge makes the
    primitive refuse a move whose guard just passed."""
    m = _mission('APPROVAL_REQUIRED')
    tx = _Tx(_row(m, version=4))
    out = _fire(tx, entities.Mission, m.id, 'approve', _user(), reason='ok',
                facts=MissionFacts(plan_version=1, plan_approval='APPROVED'),
                fields={'priority': 3})
    assert out == ('ROW', 'EVENT') and len(tx.transitions) == 1
    cls, eid, to, kw = tx.transitions[0]
    assert (cls, eid, to) == (entities.Mission, m.id, 'APPROVED')
    p = kw['proof']
    assert (p.entity_id, p.version, p.frm, p.to, p.trigger) == (
        m.id, 4, 'APPROVAL_REQUIRED', 'APPROVED', 'approve')
    assert (p.guard, p.guard_reason) == ('approve', 'plan v1 approved by a user device')
    assert kw['expected_version'] == 4 and kw['machine'] == 'mission'
    assert kw['fields'] == {'priority': 3}                     # a dict rides through whole


def test_fire_builds_the_written_fields_from_the_row_and_the_target_state():
    """lifecycle.py:110-111 (`fields = fields(row, to)`): the callable is
    given the row and the edge's DESTINATION — swapping in `frm`, or passing
    the callable to the primitive un-called, writes the wrong fields or
    crashes the transaction."""
    m = _mission()
    db, user = _world(m)
    try:
        seen = []

        def fields(row, to):
            seen.append((row.entity.id, to))
            return {'desired_outcome': 'to %s' % to}
        db.writer.execute(lambda tx: _fire(tx, entities.Mission, m.id, 'start', user,
                                           reason='go', fields=fields), {})
        assert seen == [(m.id, 'UNDERSTANDING')]
        row = _current(db, entities.Mission, m.id)
        assert (row.entity.state, row.entity.desired_outcome, row.version) == (
            'UNDERSTANDING', 'to UNDERSTANDING', 2)
    finally:
        db.close()


def test_a_guarded_fire_writes_the_move_with_the_guard_that_let_it_through():
    """lifecycle.py:106-114 end to end: the guarded `approve` edge commits
    only because check's passing GuardResult became a proof whose guard the
    primitive recognises — the event carries the guard name and its reason
    (`writer.py` payload['guard'] requires proof.guard_reason, so dropping
    the proof halves fails the move or loses the trail)."""
    m = _mission('APPROVAL_REQUIRED')
    db, user = _world(m)
    try:
        db.writer.execute(lambda tx: _fire(
            tx, entities.Mission, m.id, 'approve', user, reason='by the book',
            facts=MissionFacts(plan_version=1, plan_approval='APPROVED')), {})
        row = _current(db, entities.Mission, m.id)
        assert (row.entity.state, row.version) == ('APPROVED', 2)
        evs = _events(db, 'mission.state_changed', m.id)
        assert len(evs) == 1
        assert evs[0]['payload']['from'] == 'APPROVAL_REQUIRED'
        assert evs[0]['payload']['to'] == 'APPROVED'
        assert evs[0]['payload']['trigger'] == 'approve'
        assert evs[0]['payload']['guard'] == {
            'name': 'approve', 'reason': 'plan v1 approved by a user device'}
    finally:
        db.close()


def test_a_refused_fire_writes_nothing_whether_denied_by_the_machine_or_the_guard():
    """The module's promise (docstring: `a refusal writes nothing`) enforced
    through the real writer for both refusals: IllegalTrigger from resolve
    (lifecycle.py:65) and GuardFailed from check (lifecycle.py:88) — and the
    facts callable must not even run for the illegal trigger (lifecycle.py:81
    resolves before 84). A partial write here would leave a moved row with no
    event, which P2 would then roll back with UnrecordedMutation anyway —
    after the guard work."""
    m = _mission('APPROVAL_REQUIRED')
    db, user = _world(m)
    try:
        with pytest.raises(lifecycle.GuardFailed):
            db.writer.execute(lambda tx: _fire(
                tx, entities.Mission, m.id, 'approve', user, reason='not yet',
                facts=MissionFacts(plan_version=1)), {})

        def boom(row):
            raise AssertionError('facts gathered for an illegal trigger')
        with pytest.raises(lifecycle.IllegalTrigger):
            db.writer.execute(lambda tx: _fire(
                tx, entities.Mission, m.id, 'start', user, reason='x', facts=boom), {})
        row = _current(db, entities.Mission, m.id)
        assert (row.entity.state, row.version) == ('APPROVAL_REQUIRED', 1)
        assert _events(db, 'mission.state_changed') == []
    finally:
        db.close()


@pytest.mark.parametrize('trigger', ['code_expired', 'revoke?'],
                         ids=['ends-machine', 'no-such-edge'])
def test_fire_refuses_what_is_not_a_state_change_and_leaves_the_row_whole(trigger):
    """resolve's END branch (lifecycle.py:60-63) and its fall-through (65)
    seen through fire on a live row: `code_expired` ends the device (it
    removes the row; it is not a state change) and a stray id-shaped trigger
    is simply not an edge. Were either removed, the device would take a
    forbidden move or the pseudo-state `[*]` into a real column."""
    dev = entities.Device(id=ids.new_id('device'), principal_id=ids.new_id('principal'),
                          name='laptop', platform='desktop', state='PAIRING')
    db, user = _world(dev)
    try:
        with pytest.raises(lifecycle.IllegalTrigger) as e:
            db.writer.execute(lambda tx: _fire(tx, entities.Device, dev.id, trigger, user,
                                               reason='x'), {})
        assert ('ends the machine' if trigger == 'code_expired'
                else 'no %r edge' % trigger) in str(e.value)
        row = _current(db, entities.Device, dev.id)
        assert (row.entity.state, row.version) == ('PAIRING', 1)
        assert _events(db, 'device.state_changed') == []
    finally:
        db.close()


def test_fire_on_a_secondary_machine_moves_only_that_machine():
    """lifecycle.py:102 and 112-114 (`field, machine = cls.machine_field(machine)`
    ... `machine=machine`): the integration edge is taken on `integration_state`
    under the integration machine; dropping `machine=` would look the trigger
    up in the task machine and 500 — or worse, with a colliding name, move the
    wrong state field. The task's main state must not budge."""
    task = _task(state='SUCCEEDED', integration_state='PENDING')
    good = IntegrationFacts(task_state='SUCCEEDED', plan_in_force=True,
                            verified_revision='rev-a', revision='rev-a')
    db, user = _world(task)
    try:
        db.writer.execute(lambda tx: _fire(
            tx, entities.Task, task.id, 'task_verified', user, reason='merge it',
            facts=good, machine='integration'), {})
        row = _current(db, entities.Task, task.id)
        assert (row.entity.integration_state, row.entity.state, row.version) == (
            'MERGING', 'SUCCEEDED', 2)
        evs = _events(db, 'integration.state_changed', task.id)
        assert len(evs) == 1
        assert evs[0]['payload'] == {'from': 'PENDING', 'to': 'MERGING',
                                     'trigger': 'task_verified', 'reason': 'merge it',
                                     'guard': {'name': 'task_verified',
                                               'reason': 'merging the verified revision '
                                                         'rev-a'}}
        assert _events(db, 'task.state_changed') == []
    finally:
        db.close()


@pytest.mark.parametrize('over, exc', [
    ({'machine': 'nope'}, LookupError),          # not a machine of the entity at all
    ({'integration_state': None}, lifecycle.IllegalTrigger),   # never started: fail closed
], ids=['unknown-machine', 'never-started'])
def test_fire_of_a_secondary_machine_fails_closed_on_what_has_no_edge(over, exc):
    """lifecycle.py:102 (cls.machine_field raises for a machine the entity
    does not hold) and resolve's fall-through on a state the row has never
    had (`integration_state` None): both refuse before any write. Removing
    the _MACHINES lookup (KeyError -> silent main machine) or letting None
    resolve would merge an integration that never started."""
    task = _task(**{'integration_state': over.get('integration_state', 'PENDING')})
    db, user = _world(task)
    try:
        with pytest.raises(exc):
            db.writer.execute(lambda tx: _fire(
                tx, entities.Task, task.id, 'task_verified', user, reason='x',
                facts=IntegrationFacts(task_state='SUCCEEDED', plan_in_force=True,
                                       verified_revision='rev-a', revision='rev-a'),
                machine=over.get('machine', 'integration')), {})
        row = _current(db, entities.Task, task.id)
        assert (row.entity.integration_state, row.version) == (
            'PENDING' if exc is LookupError else None, 1)
        assert _events(db, 'integration.state_changed') == []
    finally:
        db.close()


# ── the same request twice: a fire is taken once ────────────────────────────

def fire_start(tx, *, mission_id, actor, reason='go', expected_version=None):
    """A command wrapper of the shape P3 uses, for the writer's replay."""
    row, event = lifecycle.fire(tx, entities.Mission, mission_id, 'start',
                                actor=actor, reason=reason,
                                expected_version=expected_version)
    return {'state': row.entity.state, 'version': row.version, 'event': event.id}


def test_the_same_fired_request_replays_without_taking_the_edge_again():
    """Replay of one request (the module runs inside the caller's idempotent
    writer transaction, writer.py `_recall`): the second submit of the same
    command under the same key must run NOTHING — a second `transition`
    would double the version and append a phantom second state_changed with
    nobody having asked for it."""
    m = _mission()
    db, user = _world(m)
    try:
        kw = {'mission_id': m.id, 'actor': user}
        first = db.writer.execute(fire_start, kw, idempotency_key='req-1')
        second = db.writer.execute(fire_start, kw, idempotency_key='req-1')
        assert (first['state'], first['version']) == ('UNDERSTANDING', 2)
        assert isinstance(first['event'], str)
        assert second == first                      # the stored response, run nothing
        assert second['event'] == first['event']    # not a phantom second event id
        row = _current(db, entities.Mission, m.id)
        assert (row.entity.state, row.version) == ('UNDERSTANDING', 2)
        assert len(_events(db, 'mission.state_changed', m.id)) == 1
    finally:
        db.close()


def test_a_refusal_under_an_idempotency_key_burns_neither_the_key_nor_the_row():
    """`a refusal writes nothing` meets replay: a fire that dies on the
    version gate (lifecycle.py:104-105) leaves no stored response — the same
    refused request a second time must raise again, not replay a cached
    answer — and the later good fire still runs. Dropping the rollback of
    the key row would make the first failure permanent and hide the retry."""
    m = _mission()
    db, user = _world(m)
    try:
        for _ in range(2):                                  # refused twice: never cached
            with pytest.raises(lifecycle.VersionConflict):
                db.writer.execute(fire_start, {'mission_id': m.id, 'actor': user,
                                               'expected_version': 99},
                                  idempotency_key='req-bad')
        assert _current(db, entities.Mission, m.id).version == 1
        assert _events(db, 'mission.state_changed') == []
        out = db.writer.execute(fire_start, {'mission_id': m.id, 'actor': user},
                                idempotency_key='req-good')
        assert (out['state'], out['version']) == ('UNDERSTANDING', 2)
    finally:
        db.close()
