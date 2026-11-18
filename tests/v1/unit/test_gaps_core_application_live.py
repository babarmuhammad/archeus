"""T-739: the ten highest-risk uncovered branches of
`archeus/core/application/live.py` — the one derivation of the work in flight
(ADR-0043 §2) and the one answer to "why" for an execution (ADR-0047 §9).

Fail-closed and denial paths first (what is never listed as work in flight, what
a client is never told, what an unknown stays unknown), then the boundary values
(the nine live states, the window of an own call, the depth of a hand-off chain),
then the error paths (a record the derivation is pointed at and that has gone).
Every test names, in its docstring, the source branch whose removal or inversion
it catches; the report quotes them.

Same seams as the module's closest unit tests
(tests/v1/unit/test_gaps_core_application_executions.py and
tests/v1/unit/test_gaps_core_application_resources.py): the real SQLite database
on the test's own `ARCHEUS_HOME` (tests/v1/conftest.py), the one writer for every
row, the real event log, every instant fixed by the test. No process, no network,
no sleep, no clock that moves with the machine that runs it, nothing that needs
Windows or the Windows API: a home here is a spelling only, never a directory, and
no OS call is reached (so none is faked).
"""

import json

import pytest

from archeus.core.application import live, resources
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.infra.db import Database, rows

#: every own call is written at this instant and read back at an offset the test
#: states: nothing here moves when the suite runs or on which machine it runs
NOW = resources._epoch('2026-09-16T10:00:00.000Z')
#: a home as `Homes` holds it — a spelling only, never created and never read from
#: the disk, absolute in the one form both platforms agree on, no volume letter
HOME = '/W/Home-One'
#: the live states of state-machines §4 as ADR-0043 §2 reads them, and the ends
LIVE_STATES = ('INTENT', 'STARTING', 'RUNNING', 'AWAITING_APPROVAL', 'PAUSING', 'PAUSED',
               'STOPPING', 'LOST', 'HANDING_OFF')
DEAD_STATES = ('ABANDONED', 'ENDED_OK', 'ENDED_ERROR', 'ENDED_KILLED', 'ENDED_HANDOFF',
               'ENDED_REJECTED')
#: a reported basis (ADR-0047 §2): what `record_progress` stores on the Execution
REPORTED = {'used_tokens': 150000, 'window': 200000, 'window_source': 'offer',
            'usage_source': 'harness_reported', 'at_seq': 4, 'signal': 'none',
            'signal_seq': None}


class World:
    """One test's real database, seeded through the one writer with exactly the
    rows `live.py` reads. Only the clock is decided here, never the storage."""

    def __init__(self):
        self.db = Database.open()
        self.user = Ref('user_device', ids.new_id('principal'))
        self.system = Ref('system', ids.new_id('principal'))
        self._attempts = {}          # (task, attempt) is unique: one dispatch, one attempt
        self._plans = {}             # a replan is a new row: plan_version counts per mission

    def close(self):
        self.db.close()

    def do(self, command, *, idempotency_key=None, **kw):
        return self.db.writer.execute(command, dict(kw), idempotency_key=idempotency_key)

    def read(self, fn, *a, **kw):
        with self.db.read() as conn:
            return fn(conn, *a, **kw)

    def counts(self):
        """How much the database holds: the proof that a read read."""
        def go(conn):
            return tuple(conn.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
                         for t in ('executions', 'tasks', 'events', 'route_decisions',
                                   'checkpoints')) + (
                conn.execute('SELECT COALESCE(SUM(version), 0) FROM executions').fetchone()[0],)
        return self.read(go)

    # ── the rows live.py reads ───────────────────────────────────────────────

    def mission(self, *, project_id=None, title='Ship it'):
        mid = ids.new_id('mission')

        def cmd(tx, actor):
            tx.insert(entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE,
                                       title=title, objective='ship it', state='EXECUTING',
                                       project_id=project_id), actor=actor)
            tx.append(new_event('mission.created', Ref('mission', mid), actor, payload={}))
        self.do(cmd, actor=self.user)
        return mid

    def task(self, mid, *, key='t1', title='The first step', state='RUNNING'):
        tid, pid = ids.new_id('task'), ids.new_id('plan')
        self._plans[mid] = version = self._plans.get(mid, 0) + 1

        def cmd(tx, actor):
            tx.insert(entities.Plan(id=pid, mission_id=mid, plan_version=version,
                                    state='APPROVED'), actor=actor)
            tx.insert(entities.Task(id=tid, plan_id=pid, mission_id=mid, key=key, title=title,
                                    kind='code_change', state=state, max_attempts=3),
                      actor=actor)
            tx.append(new_event('task.created', Ref('task', tid), actor, payload={}))
        self.do(cmd, actor=self.user)
        return tid

    def execution(self, mid, tid, *, state='RUNNING', attempt=None, **fields):
        """One execution row written in *state* (what `live_work` selects on), with
        *fields* set on the insert: a hand-off link, a decision, a basis."""
        eid = ids.new_id('execution')
        if attempt is None:
            self._attempts[tid] = attempt = self._attempts.get(tid, 0) + 1

        def cmd(tx, actor):
            tx.insert(entities.Execution(id=eid, task_id=tid, mission_id=mid, state=state,
                                         attempt=attempt, **fields), actor=actor)
            tx.append(new_event('execution.intent', Ref('execution', eid), actor, payload={}))
        self.do(cmd, actor=self.user)
        return eid

    def moved(self, eid, *, frm='RUNNING', to='HANDING_OFF', reason='context pressure 0.80',
              type_='execution.state_changed', subject='execution'):
        """One recorded transition, in the shape `Tx.transition` gives it (what
        `transitions` reads). *type_* and *subject* exist for the hostile case: a
        record that only looks like one."""

        def cmd(tx, actor):
            tx.append(new_event(type_, Ref(subject, eid), actor,
                                payload={'from': frm, 'to': to, 'reason': reason}))
        self.do(cmd, actor=self.system)
        return eid

    def misfiled(self, eid, *, reason='a state change filed under another kind'):
        """A row the log should never have held: an `execution.state_changed`
        payload filed under a *task* subject. `Tx.append` stores what a command
        hands it (only `new_event` checks the kind against the type), and reading
        such a row back raises — so `transitions` must never decode it."""
        ev = new_event('execution.state_changed', Ref('execution', eid), self.system,
                       payload={'from': 'RUNNING', 'to': 'HANDING_OFF', 'reason': reason})

        def cmd(tx):
            tx.conn.execute(
                'INSERT INTO events (id, type, at, actor_kind, actor_id, cause_chain, '
                'subject_kind, subject_id, workspace_id, project_id, visibility, payload) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (ev.id, ev.type, ev.at, ev.actor.kind, ev.actor.id, '[]', 'task', eid,
                 ev.workspace, ev.project, ev.visibility, json.dumps(ev.payload)))
        self.do(cmd)

    def checkpoint(self, eid, mid, tid, *, trigger='pressure', steps=2, files=1, problems=1):
        cpid = ids.new_id('checkpoint')

        def cmd(tx, actor):
            tx.insert(entities.Checkpoint(
                id=cpid, execution_id=eid, mission_id=mid, task_id=tid, trigger=trigger,
                objective='ship it', completed_steps=tuple('step %d' % i for i in range(steps)),
                files_changed=tuple('file %d' % i for i in range(files)),
                open_problems=tuple('problem %d' % i for i in range(problems))), actor=actor)
            tx.append(new_event('checkpoint.created', Ref('checkpoint', cpid), actor,
                                payload={'execution': eid, 'trigger': trigger,
                                        'task_id': tid}))
        self.do(cmd, actor=self.system)
        return cpid

    def decision(self, *, explanation='the account had the room', result='selected',
                 created_at=NOW, requirements=None, **fields):
        """One recorded route decision: what `explain` reads through an
        execution's `route_decision_id`, and (as an `archeus_call`) what
        `own_calls` scans for the own calls in flight."""
        rid = ids.new_id('route_decision')
        at = resources._iso(created_at)
        fields.setdefault('subject', Ref('task', ids.new_id('task')))
        fields.setdefault('decided_by', 'router')
        if requirements is None:
            requirements = {'max_run_s': None}

        def cmd(tx, actor):
            tx.insert(entities.RouteDecision(
                id=rid, explanation=explanation, result=result,
                requirements=requirements, input_snapshot={'now': at}, **fields),
                actor=actor)
            tx.conn.execute('UPDATE route_decisions SET created_at = ?, updated_at = ? '
                            'WHERE id = ?', (at, at, rid))
            tx.append(new_event('route.decided', Ref('route_decision', rid), actor,
                                payload={'result': result}))
        self.do(cmd, actor=self.system)
        return rid

    def own_call(self, *, purpose='planner', result='selected', outcome=None, max_run_s=None,
                 created_at=NOW, project_id=None, account_id=None, source=None):
        """An own call as ADR-0048 D-25.4 states it, its `created_at` written here
        and not by the writer's clock — the shape `own_call_live` reads: result,
        outcome, and `requirements['max_run_s']`."""
        return self.decision(subject=Ref('archeus_call', 'brain'), purpose=purpose,
                             result=result, outcome=outcome, project_id=project_id,
                             account_id=account_id, harness_id='fake', explanation='',
                             source=None if source is None else Ref(*source),
                             created_at=created_at,
                             requirements={'subject': 'archeus_call', 'purpose': purpose,
                                           'max_run_s': max_run_s})

    # ── the reads under test ─────────────────────────────────────────────────

    def work(self, project_id=None, homes=None, now=NOW):
        return self.read(live.live_work, project_id, homes, now)

    def ids(self, project_id=None, **kw):
        return [x['id'] for x in self.work(project_id=project_id, **kw)]

    def handoff(self, eid, homes=None):
        """`live.handoff_of` of one execution, read directly — the shape a finished
        execution carries too, which `live_work` does not list."""
        def go(conn):
            return live.handoff_of(conn, rows.get(conn, entities.Execution, eid).entity, homes)
        return self.read(go)

    def item(self, eid, **kw):
        got = [x for x in self.work(**kw) if x['id'] == eid]
        assert len(got) == 1, 'exactly one entry for %s, got %r' % (eid, got)
        return got[0]

    def entity(self, cls, id_):
        return self.read(lambda c: rows.get(c, cls, id_)).entity

    def why(self, eid, homes=None):
        def go(conn):
            return live.explain(conn, rows.get(conn, entities.Execution, eid).entity, homes)
        return self.read(go)

    def chain(self, eid):
        def go(conn):
            e = rows.get(conn, entities.Execution, eid).entity
            return [x.id for x in live.chain(conn, e)]
        return self.read(go)

    def transitions(self, eid):
        return self.read(live.transitions, eid)


@pytest.fixture
def w():
    world = World()
    yield world
    world.close()


@pytest.fixture
def one(w):
    """One live RUNNING execution on its own mission and task."""
    mid = w.mission(project_id=ids.new_id('project'))
    tid = w.task(mid)
    return mid, tid, w.execution(mid, tid)


# ── 1. live.py:68-69 — the live states are the whole list: nothing else is work ─

def test_live_work_lists_every_execution_in_a_live_state_and_not_one_that_has_ended(w):
    """live.py:68-69 — `'SELECT * FROM executions WHERE state IN (%s)' % ','.join(
    '?' * len(LIVE))`, with `LIVE` (executions.py:43). Take one state out of that
    tuple and the work in flight silently loses it here — and `/v1/status.live`,
    the `status` verb and every account's `running` count with it; put an ended
    state in and an execution that has finished is reported as work forever."""
    mid = w.mission()
    tid = w.task(mid)
    live_ids = [w.execution(mid, tid, state=s) for s in LIVE_STATES]
    dead_ids = [w.execution(mid, tid, state=s) for s in DEAD_STATES]
    assert w.ids() == live_ids                                    # oldest first, none missing
    assert [x['state'] for x in w.work()] == list(LIVE_STATES)
    assert all(x['kind'] == 'execution' for x in w.work())
    for one_dead in dead_ids:
        assert one_dead not in w.ids()
    assert w.ids() == live_ids                    # a second read of the same world: the same answer


# ── 2. live.py:73-74, 95 — a project never sees another project's work ─────────

def test_a_project_filter_lists_nothing_that_is_not_that_projects(w):
    """live.py:73-74 (`if project_id is not None and m.project_id != project_id:
    continue`) and its own-call twin at live.py:95. Drop the comparison and
    `/v1/status.live?project=…` answers with the work of every other project —
    the one read scoped by project; invert it and it answers with nothing at all.
    Listing nothing for a project that does not exist is the fail-closed half:
    an unknown handle is never answered with the whole world."""
    a = w.mission(project_id=ids.new_id('project'), title='Here')
    ta = w.task(a, key='t1')
    ea = w.execution(a, ta)
    b = w.mission(project_id=ids.new_id('project'), title='Elsewhere')
    tb = w.task(b, key='t1')
    eb = w.execution(b, tb)
    pa = w.entity(entities.Mission, a).project_id
    pb = w.entity(entities.Mission, b).project_id
    loose = w.own_call()                                   # an own call with no project at all
    mine = w.own_call(purpose='brain', project_id=pb)
    assert w.ids() == [ea, eb, loose, mine]                        # unfiltered: all four, in order
    assert w.ids(pa) == [ea]                                       # not the other mission or its call
    assert w.ids(pb) == [eb, mine]                                 # both halves of the same project
    assert w.ids(ids.new_id('project')) == []                      # unknown project: nothing, not all
    assert w.work() == w.work()                              # and the unfiltered read does not drift


# ── 3. live.py:76-80 — what one waits on is said for the two states that wait ──

@pytest.mark.parametrize('state,wants', [
    ('AWAITING_APPROVAL', 'approval'),
    ('PAUSED', 'resume'),
    ('RUNNING', None), ('INTENT', None), ('HANDING_OFF', None), ('LOST', None)],
    ids=['approval', 'resume', 'running', 'intent', 'handing-off', 'lost'])
def test_waits_on_names_the_two_states_that_wait_and_nothing_else(w, one, state, wants):
    """live.py:76-80 — the `waits_on` ladder (`if e.state == 'AWAITING_APPROVAL':
    waits = 'approval'` / `elif e.state == 'PAUSED': waits = 'resume'`). Swap the
    two words and the operator is sent for the wrong one; drop the state tests
    and a running execution claims to wait for a human while a paused one says it
    runs freely; with the default not None, an execution that waits on nobody
    invents a demand on the user."""
    mid, tid, _eid = one
    eid = w.execution(mid, tid, state=state)
    assert w.item(eid)['waits_on'] == wants
    assert w.item(eid)['state'] == state                           # the state itself, unlabelled


# ── 4. live.py:88 — the checkpoints counted are the ones that task wrote ───────

def test_the_checkpoints_counted_are_the_ones_recorded_for_that_task(w, one):
    """live.py:88 — `len(rows.where(conn, entities.Checkpoint, task_id=t.id))`.
    Drop the `task_id=` argument and every checkpoint in the database counts for
    every live row; key it on another column and none ever count; and an
    execution that has produced nothing reads a real 0, never None — the
    difference between "nothing yet" and "I did not look"."""
    mid, tid, eid = one
    sibling = w.execution(mid, tid, state='ENDED_OK')                    # the same task, ended
    late = w.execution(mid, tid, state='ENDED_OK')                       # its third attempt
    second_task = w.task(mid, key='t2', title='The second step')
    other = w.execution(mid, second_task, state='RUNNING')
    assert w.item(eid)['checkpoints'] == 0                                 # nothing written: a 0
    w.checkpoint(sibling, mid, tid)
    assert w.item(eid)['checkpoints'] == 1                                 # the task's history
    w.checkpoint(late, mid, tid)                                  # a second one of the same task
    w.checkpoint(other, mid, second_task)
    assert w.item(eid)['checkpoints'] == 2                       # this task's two, not all three
    assert w.item(other)['checkpoints'] == 1                     # and not this execution's own
    assert w.item(eid)['task_id'] == tid


# ── 5. live.py:90 + 39-42 — only a HANDING_OFF one says why it was asked ───────

def test_only_a_handing_off_execution_reports_why_it_was_asked_and_its_last_saying(w, one):
    """live.py:90 (`'handing_off': _clean(_asked(conn, e.id), homes) if e.state ==
    'HANDING_OFF' else None`) with live.py:39-42 (`_asked`: `got[-1] if got else
    None`). Report it for another state and the client sees a hand-off nobody
    asked for; read the FIRST reason instead of the last and a run asked to hand
    off twice is explained by its first excuse; and with no asking recorded at
    all the field stays None — never '' and never the word 'None'."""
    mid, tid, _eid = one
    asked = w.execution(mid, tid, state='HANDING_OFF')
    silent = w.execution(mid, tid, state='HANDING_OFF')
    running = w.execution(mid, tid, state='RUNNING')
    stale = w.execution(mid, tid, state='RUNNING')          # asked, and never moved on
    w.moved(asked, to='HANDING_OFF', reason='context pressure 0.80')
    w.moved(asked, frm='HANDING_OFF', to='HANDING_OFF',
           reason='the user asked for a fresh session')
    w.moved(running, to='RUNNING', reason='its process exists')               # never an asking
    w.moved(stale, to='HANDING_OFF', reason='it was asked, and the record went no further')
    assert w.item(asked)['handing_off'] == 'the user asked for a fresh session'
    assert w.item(silent)['handing_off'] is None                               # nothing recorded
    assert w.item(running)['handing_off'] is None                              # not handing off
    assert w.item(stale)['handing_off'] is None                                # its state says so


# ── 6. live.py:28-31 — transitions reads one subject kind, one type, in seq ────

def test_transitions_reads_only_that_executions_own_state_changes_in_the_order_written(w, one):
    """live.py:28-31 — the three SQL conditions (`subject_kind = 'execution'`,
    `subject_id = ?`, `type = 'execution.state_changed'`) and `ORDER BY seq`.
    Drop the type and an `execution.hook` record — whose payload a hook writes —
    becomes a state change; drop the subject kind and any record that carries this
    id, a task or a checkpoint, speaks for this execution; drop the order and
    `_asked` answers with the oldest saying instead of the newest, so a re-asked
    hand-off is explained by the first demand."""
    mid, tid, _eid = one
    eid = w.execution(mid, tid, state='HANDING_OFF')
    sibling = w.execution(mid, tid, state='RUNNING')                         # same task, another one
    w.moved(eid, to='RUNNING', reason='its process exists')
    w.moved(eid, to='HANDING_OFF', reason='the real asking')
    w.moved(sibling, to='HANDING_OFF', reason='another executions asking')   # another subject_id
    w.moved(eid, to='HANDING_OFF', reason='not a state change', type_='execution.hook')
    # a record of another kind that carries this very id as its subject
    w.moved(eid, to='HANDING_OFF', reason='not about an execution', subject='task',
            type_='task.state_changed')
    w.misfiled(eid, reason='filed under the wrong subject kind')                # a corrupt record
    assert w.transitions(eid) == [('RUNNING', 'RUNNING', 'its process exists'),
                                  ('RUNNING', 'HANDING_OFF', 'the real asking')]
    assert w.item(eid)['handing_off'] == 'the real asking'                    # the only one it may read


# ── 7. live.py:92-96 — an own call is work only inside its own window ──────────

@pytest.mark.parametrize('case,now,listed', [
    ('flying', NOW, True),
    ('flying', NOW + 600, True),          # its maximum run: the boundary is inclusive (:206)
    ('flying', NOW + 601, False),         # one second past: a Core that died holds no slot
    ('fallback', NOW, True),              # a fallback that ran is work like any other
    ('asked', NOW, False),                # nothing was chosen: nothing is running
    ('blocked', NOW, False),              # ditto, the other refusal
    ('answered', NOW, False),             # it answered: the slot is released
    ('unbounded', NOW + 3600, True),      # no maximum recorded: live until its outcome
    ('stale', NOW + 86401, False),        # a day past: `own_calls` does not even scan it
], ids=('at-start', 'at-its-maximum-run', 'one-second-late', 'fallback-ran', 'asked-nothing',
        'blocked', 'already-answered', 'no-maximum-a-hour-later', 'a-day-and-a-second-late'))
def test_an_own_call_is_work_in_flight_only_between_its_decision_and_its_outcome(
        w, one, case, now, listed):
    """live.py:92 (`now = time.time() if now is None else now`) and live.py:93-96
    (`for r in own_calls(conn, now)` then `if not own_call_live(r, now) or …:
    continue`). Invert either test and a call that chose nothing, or one that
    already answered, is listed as work in flight — and counted against its
    account's concurrency ceiling — while a call really running is not."""
    mid, tid, eid = one
    made = {'flying': lambda: w.own_call(max_run_s=600),
            'fallback': lambda: w.own_call(result='fallback', max_run_s=600),
            'asked': lambda: w.own_call(result='ask'),
            'blocked': lambda: w.own_call(result='blocked'),
            'answered': lambda: w.own_call(outcome={'state': 'ok'}),
            'unbounded': lambda: w.own_call(max_run_s=None),
            'stale': lambda: w.own_call(max_run_s=None, created_at=NOW - 86401)}
    rid = made[case]()
    assert eid in w.ids(now=now)                              # the execution is listed whatever
    assert (rid in w.ids(now=now)) is listed


# ── 8. live.py:97-103 — an own call names only a mission that exists ───────────

def test_the_source_of_an_own_call_names_only_a_mission_that_actually_exists(w, one):
    """live.py:97-103 — `src = rd.source`, then `m = src is not None and
    src.kind == 'mission' and rows.get(conn, entities.Mission, src.id)` and the
    three `if m else None` reads that follow. Drop the kind test and a source of
    another kind is looked up in the missions table and given a mission's title;
    drop the `if m else None` and an own call whose mission has gone raises,
    taking the whole `/v1/status.live` read down with it, instead of saying that
    it belongs to no mission it can name."""
    mid, tid, eid = one
    from_mission = w.own_call(source=('mission', mid))
    foreign = w.own_call(purpose='brain', source=('task', tid))            # not a mission at all
    # the hostile half: a source whose recorded kind and id disagree — a task kind carrying
    # a mission id. The kind is what the read trusts, so it names no mission for it
    lying = w.own_call(purpose='generation', source=('task', mid))
    gone = w.own_call(purpose='lesson', source=('mission', ids.new_id('mission')))
    bare = w.own_call(purpose='review')                                    # no source recorded
    assert w.item(from_mission)['source'] == {'kind': 'mission', 'id': mid}
    assert (w.item(from_mission)['mission_id'], w.item(from_mission)['mission_title']) == (
        mid, 'Ship it')
    assert w.item(foreign)['source'] == {'kind': 'task', 'id': tid}         # said as it was recorded
    assert (w.item(foreign)['mission_id'], w.item(foreign)['mission_title']) == (None, None)
    assert w.item(lying)['source'] == {'kind': 'task', 'id': mid}
    assert (w.item(lying)['mission_id'], w.item(lying)['mission_title']) == (None, None)
    assert w.item(gone)['source'] == {'kind': 'mission',
                                       'id': w.item(gone)['source']['id']}
    assert (w.item(gone)['mission_id'], w.item(gone)['mission_title']) == (None, None)
    assert (w.item(bare)['source'], w.item(bare)['mission_id'],
            w.item(bare)['mission_title']) == (None, None, None)
    # and nothing animates an own call (G8): no state, no task, no context, no hand-off
    for rid in (from_mission, foreign, lying, gone, bare):
        assert (w.item(rid)['kind'], w.item(rid)['state'], w.item(rid)['task_id'],
                w.item(rid)['attempt'], w.item(rid)['context'], w.item(rid)['handoff'],
                w.item(rid)['route_decision_id']) == (
            'own_call', None, None, None, None, None, rid)
    assert eid in w.ids()                                        # the execution still reads too


# ── 9. live.py:45-59 — the chain is counted nearest first, and the reason is ───
# ── the predecessor's own last asking; an execution that continues none has zero ─

def test_a_handoff_counts_its_chain_nearest_first_and_says_why_its_predecessor_stopped(w, one):
    """live.py:45-52 (`chain`: `while cur is not None: … cur = prev.handoff_from`)
    with live.py:55-59 (`handoff_of`: `'count': len(before)` and `'reason':
    _clean(_asked(conn, e.handoff_from), homes) if e.handoff_from else None`).
    Append in the farthest-first order, or count `len(before) + 1`, and the client
    is told the wrong place in the chain; read the reason from *this* execution
    instead of the one it continues and a hand-off is explained by its own demand
    rather than the one that ended the session before it; and an execution that
    continues nothing reports `{'from': None, 'count': 0, 'reason': None}`, never
    a missing key and never a crash on `None.handoff_from`."""
    mid, tid, _eid = one
    first = w.execution(mid, tid, state='ENDED_HANDOFF')
    second = w.execution(mid, tid, state='ENDED_HANDOFF', handoff_from=first)
    third = w.execution(mid, tid, state='RUNNING', handoff_from=second)
    w.moved(first, to='HANDING_OFF', reason='the account ran out of room')
    w.moved(second, to='HANDING_OFF', reason='context pressure 0.80')
    w.moved(second, to='ENDED_HANDOFF', reason='its checkpoint was written')
    assert w.chain(third) == [second, first]                     # nearest first, both of them
    assert w.chain(second) == [first]
    assert w.chain(first) == []                                  # continues nothing: no walk
    assert w.item(third)['handoff'] == {
        'from': second, 'count': 2, 'reason': 'context pressure 0.80'}    # ITS PREDECESSOR's asking
    assert w.handoff(second) == {
        'from': first, 'count': 1, 'reason': 'the account ran out of room'}
    assert w.handoff(first) == {'from': None, 'count': 0, 'reason': None}
    # the asking of its own is not the reason it continues: that is `handing_off`, and only
    # while it is in that state
    assert w.item(third)['handing_off'] is None


# ── 10. live.py:34-36 — a home is scrubbed only when the reader brought homes ──

def test_a_recorded_reason_is_scrubbed_only_when_the_reader_brought_homes(w, one):
    """live.py:34-36 (`_clean`: `return text if homes is None else scrub_text(
    text, homes)`) as its four callers use it — live.py:59 (the hand-off reason),
    live.py:90 (`handing_off`) and live.py:141 (`explain` as a whole). Never
    scrub, and an account's home reaches a client from the status read; scrub
    when homes is None and the read that has no homes (the `why` of the
    conversation verb) loses text it was owed; and a reason that was never
    recorded, or was never a string, passes `_clean` through instead of raising
    inside the read."""
    homes = Homes([HOME], shorts=lambda _: None)
    mid, tid, _eid = one
    asked = w.execution(mid, tid, state='HANDING_OFF')
    child = w.execution(mid, tid, state='RUNNING', handoff_from=asked)
    odd = w.execution(mid, tid, state='HANDING_OFF')
    silent = w.execution(mid, tid, state='HANDING_OFF')
    w.moved(asked, to='HANDING_OFF', reason='read %s/settings.json' % HOME)
    w.moved(odd, to='HANDING_OFF', reason=42)                     # not text at all
    assert w.item(asked, homes=homes)['handing_off'] == 'read its home/settings.json'
    assert HOME in w.item(asked)['handing_off']           # the control: no homes, no scrub
    assert w.item(child, homes=homes)['handoff']['reason'] == 'read its home/settings.json'
    assert HOME in w.item(child)['handoff']['reason']
    assert HOME not in w.why(asked, homes=homes)
    assert 'its home/settings.json' in w.why(asked, homes=homes)
    assert HOME in w.why(asked)                                   # and the words are still owed
    assert w.item(odd, homes=homes)['handing_off'] == 42           # a reason that is not text
    assert w.item(silent, homes=homes)['handing_off'] is None       # None survives the scrub


# ── 11. live.py:114-117 — the routing words come from the record or not at all ──

def test_explain_says_the_routing_only_from_a_decision_that_says_something(w, one):
    """live.py:114-117 — `if e.route_decision_id is not None:` and then `if rd is
    not None and rd.entity.explanation:`. Drop the second test and an execution
    whose decision recorded no words is given the line `Routing: `, a client
    reading a decision that was never made; drop the `rd is not None` and an
    execution pointed at a decision that has gone raises inside `why` and the
    execution view instead of saying nothing about routing; drop the first and
    every execution that was never routed is asked to explain a routing."""
    mid, tid, _eid = one
    routed = w.execution(mid, tid, route_decision_id=w.decision(
        explanation='the account had the room and the lowest priority'))
    silent = w.execution(mid, tid, route_decision_id=w.decision(explanation=''))
    gone = w.execution(mid, tid, route_decision_id=ids.new_id('route_decision'))
    never = w.execution(mid, tid)
    assert w.why(routed).startswith(
        'Routing: the account had the room and the lowest priority')
    for eid in (silent, gone, never):
        assert 'Routing:' not in w.why(eid)                              # no words, no line
        assert 'Context (' in w.why(eid)                                 # the rest stands


# ── 12. live.py:118-119 — the context is always said, an unknown stays one ─────

def test_explain_always_says_the_context_and_never_makes_a_missing_reading_a_number(
        w, one):
    """live.py:118-119 (`ctx = pressure.view(e)` then `parts.append('Context (%s):
    %s.' % (ctx['quality'], ctx['summary']))`): the one part of the answer that is
    never conditional. Drop it and `why` answers "why" without the pressure a
    hand-off was taken on; and the fail-closed half is what an unmeasured basis is
    said as — `unavailable` and "not measured by this harness", never 0 tokens,
    never 0 %, never a number Core invented (ADR-0047 §2)."""
    mid, tid, _eid = one
    blind = w.execution(mid, tid)
    measured = w.execution(mid, tid, pressure=0.75, stream_offset=4, context=dict(REPORTED))
    behind = w.execution(mid, tid, pressure=0.10, stream_offset=9, context=dict(REPORTED))
    assert w.why(blind) == 'Context (unavailable): context not measured by this harness.'
    assert w.why(measured).startswith(
        'Context (reported): the harness reported 150,000 of 200,000 tokens; '
        'window from the offer')
    assert 'Context (stale):' in w.why(behind)             # its reading is behind the stream
    assert '%' not in w.why(blind)                          # a missing reading is never a number


# ── 13. live.py:120-127 — the two "because" sentences come from records only ───

def test_explain_says_the_handoff_and_the_asking_only_from_what_was_recorded(w, one):
    """live.py:120-124 (`if e.handoff_from is not None:` … `'It continues execution
    %s in a fresh session (hand-off %d of its chain)%s.'` with the reason appended
    only `if h['reason']`) and live.py:125-127 (`asked = _asked(conn, e.id)`,
    `if asked:`). Say the hand-off sentence for an execution that continues nothing
    and `why` invents a lineage; leave the `if h['reason']` out and a hand-off with
    no recorded reason ends the sentence on a bare colon; drop `if asked` and every
    execution claims it was asked to hand off."""
    mid, tid, _eid = one
    first = w.execution(mid, tid, state='ENDED_HANDOFF')
    w.moved(first, to='HANDING_OFF', reason='the account ran out of room')
    w.moved(first, to='ENDED_HANDOFF', reason='its checkpoint was written')
    child = w.execution(mid, tid, state='RUNNING', handoff_from=first)
    w.moved(child, to='HANDING_OFF', reason='the user asked for a fresh session')
    plain = w.execution(mid, tid, state='RUNNING', handoff_from=child)          # child was asked
    lone = w.execution(mid, tid, state='ENDED_HANDOFF')                          # no events at all
    never_asked = w.execution(mid, tid, state='RUNNING', handoff_from=lone)      # its source never was
    assert ('It continues execution %s in a fresh session (hand-off 1 of its chain): '
            'the account ran out of room.' % first in w.why(child))
    assert 'It was asked to hand off: the user asked for a fresh session.' in w.why(child)
    assert 'It continues execution' not in w.why(first)                          # no lineage
    assert 'asked to hand off' not in w.why(plain)                               # it never was
    assert ('It continues execution %s in a fresh session (hand-off 1 of its chain).' % lone
            in w.why(never_asked))                              # no reason: the sentence just closes
    assert '):.' not in w.why(never_asked)                        # never on a bare colon


# ── 14. live.py:128-134 — only an ENDED_HANDOFF says how it ended, and who ─────
# ── continues it; the charged word is the record's, never an assumption ────────

@pytest.mark.parametrize('charged,says', [
    (True, 'It ended: its checkpoint was written (charged).'),
    (False, 'It ended: its checkpoint was written.'),
    (None, 'It ended: its checkpoint was written.')],
    ids=['charged', 'uncharged', 'unknown'])
def test_only_an_ended_handoff_says_how_it_ended_and_which_execution_continues_it(
        w, one, charged, says):
    """live.py:128-134 — `ended = [why for _f, to, why in transitions(conn, e.id)
    if to == e.state]`, `if e.state == 'ENDED_HANDOFF' and ended:`, the
    `' (charged)'` suffix read off `e.charged`, and `parts.append('Continued by
    execution %s.' % nxt[0] if nxt else 'No continuation was created.')`. Say it
    for any state and an execution the e-stop killed claims a hand-off; drop the
    `to == e.state` filter and the reason of some other move is read as its
    ending; assume charged and a stop the user owned spends an attempt it was
    owed; drop the `else` and a chain that ended with no continuation claims one."""
    mid, tid, _eid = one
    ended = w.execution(mid, tid, state='ENDED_HANDOFF', charged=charged)
    w.moved(ended, to='RUNNING', reason='its process exists')                    # not its ending
    w.moved(ended, to='ENDED_HANDOFF', reason='its checkpoint was written')
    # and a move recorded AFTER it, to another state: only a move that reached the
    # state it is in now may be read as how it ended
    w.moved(ended, frm='ENDED_HANDOFF', to='LOST', reason='the supervisor stopped answering')
    assert w.why(ended).count('It ended:') == 1
    assert says in w.why(ended)
    assert 'the supervisor stopped answering' not in w.why(ended)
    # another line of the same task, written FIRST: a continuation is the execution
    # that says it continues this one, not any execution of the task that continues
    # somebody
    rival = w.execution(mid, tid, state='ENDED_HANDOFF')
    elsewhere = w.execution(mid, tid, state='RUNNING', handoff_from=rival)
    assert 'Continued by execution' not in w.why(ended)
    assert 'No continuation was created.' in w.why(ended)
    after = w.execution(mid, tid, state='RUNNING', handoff_from=ended)
    assert 'Continued by execution %s.' % after in w.why(ended)
    assert 'No continuation was created.' not in w.why(ended)
    assert 'Continued by execution %s.' % elsewhere not in w.why(ended)
    assert w.why(ended).count('Continued by execution') == 1
    quiet = w.execution(mid, tid, state='ENDED_HANDOFF')                      # nothing recorded
    assert 'It ended:' not in w.why(quiet)                       # an ending nobody recorded
    killed = w.execution(mid, tid, state='ENDED_KILLED', charged=False, stop_reason='estop')
    w.moved(killed, to='ENDED_KILLED', reason='the process is gone')
    assert 'It ended:' not in w.why(killed)                       # not a hand-off: it says nothing


# ── 15. live.py:135-140 — what was preserved is that execution's checkpoint ────

def test_what_was_preserved_is_that_executions_checkpoint_and_nobody_elses(w, one):
    """live.py:135-140 — `cp = checkpoint.of_execution(conn, e.id)` and the
    `if cp is not None:` sentence naming `cp.id`, its trigger and the three
    counts. Key it on the task (as the `checkpoints` count of live.py:88 is, on
    purpose) and an execution claims another execution's preserved work — the one
    line the next session is built from; drop the `if cp is not None:` and an
    execution that never ran claims a checkpoint; and the three counts are the
    checkpoint's own lists, not what the reader guessed."""
    mid, tid, _eid = one
    ended = w.execution(mid, tid, state='ENDED_HANDOFF')
    ended_cp = w.checkpoint(ended, mid, tid, trigger='pressure', steps=3, files=2, problems=4)
    sibling = w.execution(mid, tid, state='ENDED_OK')
    sibling_cp = w.checkpoint(sibling, mid, tid, trigger='task_boundary', steps=1, files=0,
                              problems=0)
    fresh = w.execution(mid, tid, state='RUNNING')
    assert ('What was preserved: checkpoint %s (pressure), 3 completed step(s), '
            '2 file change(s), 4 open problem(s).' % ended_cp in w.why(ended))
    assert ended_cp not in w.why(sibling)                        # the sibling claims only its own
    assert 'checkpoint %s (task_boundary)' % sibling_cp in w.why(sibling)
    assert 'What was preserved' not in w.why(fresh)               # nothing was preserved yet
    assert w.item(fresh)['checkpoints'] == 2          # while the task's count is the task's, both


# ── 16. live.py:62-141 — the same request twice is the same answer, and a read ─
# ── is a read: nothing is written, and a replayed command is not a second job ───

def test_reading_the_work_in_flight_twice_is_the_same_answer_and_writes_nothing(w, one):
    """`live_work` (live.py:66-108) and `explain` (live.py:112-141) build their
    answer out of the rows and touch nothing: a derivation that wrote — a cached
    row, a repaired state, an event of its own — would make the status read change
    what it reports, twice over once a client retries. The replay half is the
    same request submitted twice under the writer's own idempotency key: one row,
    one event, and the work in flight lists one execution, not two."""
    mid, tid, _eid = one
    eid = w.execution(mid, tid, state='RUNNING')
    homes = Homes([HOME], shorts=lambda _: None)
    before = w.counts()
    assert w.work() == w.work()
    assert w.why(eid) == w.why(eid)
    assert w.work(homes=homes) == w.work()
    assert w.counts() == before                                  # every read above read only

    def spawn(tx, *, actor, mission_id, task_id, execution_id):
        tx.insert(entities.Execution(id=execution_id, task_id=task_id, mission_id=mission_id,
                                      state='RUNNING', attempt=3), actor=actor)
        tx.append(new_event('execution.intent', Ref('execution', execution_id), actor,
                            payload={}))
    again = ids.new_id('execution')
    for _ in range(2):                              # the same dispatch request, delivered twice
        w.do(spawn, idempotency_key='dispatch-t1-attempt-1', actor=w.user, mission_id=mid,
             task_id=tid, execution_id=again)
    assert w.ids().count(again) == 1                              # one execution in flight, not two
    assert w.work() == w.work()
    after = w.counts()
    assert after[:4] == (before[0] + 1, before[1], before[2] + 1, before[3])


# ── 17. live.py:66-141 on an empty world: nothing written is nothing in flight ─

def test_before_anything_is_written_nothing_is_in_flight_and_nothing_is_invented(w):
    """The empty input, every query at once. `live_work` (live.py:66-108) on
    database with no rows at all answers `[]` — the `out = []` it starts from and
    the two loops that never run; `transitions` (live.py:28-31) answers `[]` for an
    id no record speaks of, so `_asked` (live.py:39-42) gives None and `_clean`
    (live.py:34-36) is asked to scrub a None and must hand back a None; `chain`
    (live.py:45-52) walks nothing (`cur is None` before its first step) so
    `handoff_of` (live.py:55-59) says `{'from': None, 'count': 0, 'reason': None}`;
    and `explain` (live.py:112-141) on an execution that has no rows behind it
    says the one sentence it always says, in its `unavailable` form, and invents no
    routing, no lineage, no ending and no checkpoint. A read that raises on an
    empty world is a status page that will not load until something is written."""
    assert w.work() == []                                       # nothing at all in flight
    assert w.work(homes=Homes([HOME], shorts=lambda _: None)) == []
    assert w.transitions('exe_nowhere') == []               # no record speaks of this id
    bare = entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), state='RUNNING', attempt=1)
    def bare_reads(conn):
        assert live.chain(conn, bare) == []                       # no walk: it continues none
        assert live.handoff_of(conn, bare) == {'from': None, 'count': 0, 'reason': None}
        assert live.transitions(conn, 'exe_nowhere') == []
    w.read(bare_reads)
    def bare_why(conn):
        return live.explain(conn, bare, None)
    assert w.read(bare_why) == 'Context (unavailable): context not measured by this harness.'
    assert w.read(lambda c: live.explain(c, bare, Homes([HOME], shorts=lambda _: None))) == (
        'Context (unavailable): context not measured by this harness.')
    assert list(w.read(lambda c: resources.own_calls(c, NOW))) == []   # none chosen, none flying
