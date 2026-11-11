"""T-759: the highest-risk uncovered branches of
`archeus/core/application/trace.py`. Denial and fail-closed paths first (an
unknown mission refused, an unregistered harness given no adapter, a missing
process reading as no output, another mission's decisions never appearing, the
homes threading that scrubs before lanes are cut), then the boundary values
(the newest-execution window and its flag, the event cap and its flag, the
500-char text cut, the global index a step carries), then the error paths
(orphan results, calls with no id, a duplicated call id, a zero cap).

Style and the `_Registry`/stream fixtures are copied from
tests/v1/integration/test_trace.py (the existing tests of this module, found by
grep over tests/v1); the `Database.open()` world, the `_world` seeding and the
`finally: db.close()` shape are the ones tests/v1/unit/
test_gaps_core_application_executions.py uses. Nothing here needs Windows, a
real process or the network; the stream files are written under the test's own
ARCHEUS_HOME (tests/v1/conftest.py) with explicit newlines, and the only OS
seam the trace could reach — the homes matcher's short-name probe — is faked
through the `shorts=` seam the existing homes tests use.
"""

import json
import os

import pytest

from archeus.api import schemas
from archeus.core.application import trace
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.harnesses.fake import FakeHarness
from archeus.infra.db import Database
from archeus.infra.db.writer import NotFound
from archeus.infra.paths import ExecPaths

#: a registered home used only as data: it is never created, probed or asserted
#: to be absolute on any platform (the Homes matcher is fed it as a string).
GHOST = '/home/tester/ghosthome'


class _Registry:
    """The trace's registry seam, copied from tests/v1/integration/test_trace.py."""

    def __init__(self, **adapters):
        self._a = adapters

    def ids(self):
        return list(self._a)

    def get(self, hid):
        return self._a[hid]


class _NoRegistry(_Registry):
    """A registry that refuses to be asked: a trace reading an execution whose
    harness is not registered must never reach `get`."""

    def ids(self):
        return []

    def get(self, hid):
        raise AssertionError('the trace asked the registry for %r' % hid)


@pytest.fixture
def db_world():
    """A real database under the test's own ARCHEUS_HOME plus one user principal,
    closed after the test (no loose writer thread, no debris beyond tmp_path's)."""
    db = Database.open()
    try:
        yield db, Ref('user_device', ids.new_id('principal'))
    finally:
        db.close()


def _mission(db, who, *, executions=(), events=1):
    """One EXECUTING mission with an approved plan and a RUNNING task, *executions*
    (kwargs dicts for Execution, inserted in the given order) under it, and
    *events* `mission.updated` events tagged 1..n."""
    mid, pid, tid = (ids.new_id(k) for k in ('mission', 'plan', 'task'))

    def run(tx, **_):
        tx.insert(entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                   objective='o', state='EXECUTING'), actor=who)
        tx.insert(entities.Plan(id=pid, mission_id=mid, state='APPROVED'), actor=who)
        tx.insert(entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                                kind='code_change', state='RUNNING', max_attempts=2),
                  actor=who)
        for kw in executions:
            tx.insert(entities.Execution(id=kw.pop('id'), task_id=tid, mission_id=mid,
                                         plan_id=pid, **kw), actor=who)
        for n in range(events):
            tx.append(new_event('mission.updated', Ref('mission', mid), who,
                               payload={'tag': n + 1}, workspace=ids.GLOBAL_WORKSPACE))
        tx.append(_witness(who))
    db.writer.execute(run, {})
    return {'mid': mid, 'pid': pid, 'tid': tid}


def _stream(eid, events):
    """The stream file of *eid* as a harness would have left it: bytes written
    here, with explicit newlines, never the platform's."""
    p = ExecPaths(eid)
    os.makedirs(p.dir, exist_ok=True)
    with open(p.stream, 'w', encoding='utf-8') as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')


def _read(db, mid, registry, **kw):
    with db.read() as conn:
        return trace.trace(conn, mid, registry, **kw)


def _calls(lane=None):
    return [{'type': 'assistant', 'text': 'look', 'lane': lane},
            {'type': 'tool', 'name': 'Task', 'input': {}, 'id': 'tu_1', 'lane': lane}]


def _witness(who):
    """The event every mutating tx must record (writer.py:443, UnrecordedMutation):
    one about a fresh principal, so it is about none of the mission's rows and
    the timeline (attention.py:132-138) never shows it."""
    return new_event('principal.created', Ref('principal', ids.new_id('principal')), who,
                     payload={})


def test_lessons_stops_reading_once_the_cap_is_passed(db_world):
    db, who = db_world
    mid = _mission(db, who)['mid']
    kept = sorted(ids.new_id('knowledge_item') for _ in range(10000))

    def seed(tx, **_):
        for kid in reversed(kept):
            tx.insert(entities.Relation(
                id=ids.new_id('relation'), src_kind='knowledge_item', src_id=kid,
                rel='learned_from', dst_kind='mission', dst_id=mid), actor=who)
        tx.append(_witness(who))

    db.writer.execute(seed, {})
    yielded = []

    class Cursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def __iter__(self):
            for row in self.cursor:
                yielded.append(row)
                yield row

        def fetchall(self):
            pytest.fail('lessons read every row at once')

    class Read:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, params):
            return Cursor(self.conn.execute(sql, params))

    with db.read() as conn:
        lessons, more = trace.lessons(Read(conn), mid)
    assert len(yielded) == 201
    assert lessons == kept[:200]
    assert more is True


# ── lanes: the type filter, the text cap, the pairing guards ────────────────

def test_events_that_are_neither_call_nor_result_never_reach_a_lane():
    """trace.py:34-35 — `if t not in ('assistant', 'tool', 'tool_result'):
    continue`. Inverted or dropped, a `usage`, a `result` or a typeless event
    would become a step, and the schema's step-type enum would stop the read."""
    assert trace.lanes([]) == []
    junk = [{'type': 'usage', 'usage': {}}, {'type': 'result', 'summary': 'done'},
            {'type': None}, {}]
    assert trace.lanes(junk) == []


def test_an_assistant_text_defaults_to_empty_and_is_cut_at_the_cap():
    """trace.py:37-38 — `step['text'] = (e.get('text') or '')[:_TEXT]`. Without
    the `or ''` a missing/None text raises TypeError on the slice; without the
    slice a 501-char transcript line is carried whole."""
    evs = [{'type': 'assistant'}, {'type': 'assistant', 'text': None},
           {'type': 'assistant', 'text': ''}, {'type': 'assistant', 'text': 'x' * 500},
           {'type': 'assistant', 'text': 'y' * 501}]
    (lane,) = trace.lanes(evs)
    assert lane['lane'] == 'main'
    assert [s['text'] for s in lane['steps']] == ['', '', '', 'x' * 500, 'y' * 500]


def test_a_result_pairs_only_with_a_call_the_trace_actually_recorded():
    """trace.py:41 (`if e.get('id'): calls[e['id']] = step` — a call without an
    id is never registered) and trace.py:45-47 (`call = calls.get(...)`; the
    pairing only `if call is not None`). Drop the guard and an orphan result
    KeyErrors the whole read; drop the id test and `calls[None]` pairs every
    id-less call with every id-less result."""
    evs = [{'type': 'tool_result', 'tool_use_id': 'never'},
           {'type': 'tool_result'},
           {'type': 'tool', 'name': 'Read'},
           {'type': 'tool_result', 'tool_use_id': None},
           {'type': 'tool', 'name': 'Grep', 'id': ''},
           {'type': 'tool_result', 'tool_use_id': ''}]
    (lane,) = trace.lanes(evs)
    assert [s['i'] for s in lane['steps']] == [0, 1, 2, 3, 4, 5]
    assert all('call' not in s for s in lane['steps'])
    assert all('result' not in s for s in lane['steps'])


def test_a_pair_counts_every_event_including_the_filtered_ones():
    """trace.py:44-47 — the indices a pairing writes (`call['result'],
    step['call'] = i, call['i']`) are indices in the FULL event list, and
    `is_error` is normalised with bool(). Without bool(), a stream's `1` or `0`
    survives into the answer where the schema demands a boolean."""
    evs = [{'type': 'assistant', 'text': 'a'},
           {'type': 'tool', 'name': 'Bash', 'id': 'tu_1'},
           {'type': 'usage', 'usage': {}},
           {'type': 'tool_result', 'tool_use_id': 'tu_1', 'is_error': 1},
           {'type': 'tool_result', 'tool_use_id': 'orphan'}]
    (lane,) = trace.lanes(evs)
    call, res, orphan = lane['steps'][1], lane['steps'][2], lane['steps'][3]
    assert (call['i'], call['result'], res['i'], res['call']) == (1, 3, 3, 1)
    assert res['is_error'] is True
    assert orphan['is_error'] is False


def test_lanes_are_bucketed_on_first_appearance_with_a_missing_lane_as_main():
    """trace.py:48 — `out.setdefault(e.get('lane') or MAIN, [])`: a lane that is
    absent, None or the empty string is `main`, and the answer's order is first
    appearance (the dict's insertion order at trace.py:49-50)."""
    evs = [{'type': 'assistant', 'text': 'a'},
           {'type': 'tool', 'name': 'B', 'id': 'b1', 'lane': ''},
           {'type': 'assistant', 'text': 'z', 'lane': None},
           {'type': 'assistant', 'text': 'B1', 'lane': 'B'},
           {'type': 'assistant', 'text': 'A1', 'lane': 'A'},
           {'type': 'assistant', 'text': 'B2', 'lane': 'B'}]
    lanes = trace.lanes(evs)
    assert [ln['lane'] for ln in lanes] == ['main', 'B', 'A']
    assert [s['i'] for s in lanes[0]['steps']] == [0, 1, 2]
    assert [s['i'] for s in lanes[1]['steps']] == [3, 5]


def test_a_lane_is_born_from_the_call_that_spawned_it_or_says_none():
    """trace.py:49-50 — `'from': None if k == MAIN else (calls[k]['i'] if k in
    calls else None)`. Without the MAIN arm, the main lane reports the index of
    the tool call that happens to be named 'main' (seeded hostile here); with
    the membership test dropped, a lane whose spawning call was not read
    KeyErrors the read instead of saying None."""
    evs = [*_calls(),
           {'type': 'tool', 'name': 'Read', 'id': 'tu_2', 'lane': 'tu_1'},
           {'type': 'assistant', 'text': 'x', 'lane': 'ghost_lane'},
           {'type': 'tool', 'name': 'Grep', 'lane': 'no_id'},
           {'type': 'tool', 'name': 'M', 'id': 'main'}]
    main, side, ghost, no_id = trace.lanes(evs)
    assert (main['lane'], main['from']) == ('main', None)
    assert (side['lane'], side['from']) == ('tu_1', 1)
    assert (ghost['lane'], ghost['from']) == ('ghost_lane', None)
    assert (no_id['lane'], no_id['from']) == ('no_id', None)


def test_a_duplicated_call_id_pairs_with_the_last_call_only():
    """trace.py:41-42 — `calls[e['id']] = step`: the dict write overwrites, so a
    stream that reuses an id pairs (and spawns, trace.py:49) with the LAST call
    of that id. With `setdefault` (first wins) instead, the result would be
    paired to a call the harness did not run last."""
    evs = [{'type': 'tool', 'name': 'A', 'id': 'dup'},
           {'type': 'tool', 'name': 'B', 'id': 'dup'},
           {'type': 'tool_result', 'tool_use_id': 'dup'},
           {'type': 'assistant', 'text': 'x', 'lane': 'dup'}]
    main, dup = trace.lanes(evs)
    a, b, res = main['steps'][0], main['steps'][1], main['steps'][2]
    assert 'result' not in a and b.get('result') == 2
    assert res['call'] == 1
    assert (dup['lane'], dup['from']) == ('dup', 1)


# ── trace: refusals and fail-closed reads first ─────────────────────────────

def test_a_mission_that_is_not_there_is_refused_before_anything_is_read(db_world):
    """attention.py:130-131 (reached through trace.py:56) — `if rows.get(conn,
    entities.Mission, mission_id) is None: raise NotFound(mission_id)`. Without
    the guard, the empty timeline's `[]` would answer 200 for a mission that
    does not exist: the API's 404 and every client's "no such mission" are
    exactly this raise."""
    db, who = db_world
    k = _mission(db, who, executions=[{'id': ids.new_id('execution'), 'state': 'RUNNING'}])
    other = _mission(db, who, events=0)
    with db.read() as conn:
        eid = conn.execute('SELECT id FROM executions').fetchone()[0]
    for bad in (ids.new_id('mission'), '', eid, other['pid'], other['tid']):
        with pytest.raises(NotFound):
            _read(db, bad, _Registry())


def test_an_execution_whose_harness_is_unknown_gets_no_adapter_and_no_output(db_world):
    """trace.py:61 — `adapter = registry.get(e.harness_id) if e.harness_id in
    registry.ids() else None`. Dropped, an execution of an unregistered (or
    nameless) harness asks the registry for an adapter it must not have and
    reads a stream through it; here the very registry raises if consulted, and
    the stream file is on disk to be read were the read not refused."""
    db, who = db_world
    e1, e2 = ids.new_id('execution'), ids.new_id('execution')
    events = [*_calls(), {'type': 'tool_result', 'tool_use_id': 'tu_1', 'is_error': False}]
    _stream(e1, events)
    _stream(e2, events)
    k = _mission(db, who, events=0, executions=[
        {'id': e1, 'harness_id': 'ghost', 'pid': 4242, 'create_time': 1.0, 'attempt': 1,
         'state': 'RUNNING'},
        {'id': e2, 'harness_id': None, 'pid': 4242, 'create_time': 1.0, 'attempt': 2,
         'state': 'RUNNING'}])
    t = _read(db, k['mid'], _NoRegistry())
    assert [(x['id'], x['available'], x['truncated'], x['lanes']) for x in t['executions']] \
        == [(e1, False, False, []), (e2, False, False, [])]


def test_no_process_means_no_output_even_though_a_stream_file_lies_there(db_world):
    """output.py:23-24 (through trace.py:62) — `if execution.pid is None or
    adapter is None: return out`: the empty `available: false` answer. With the
    pid guard dropped, a row whose process never started (or died before its
    pid was recorded) reads a stale stream file as if the execution had run."""
    db, who = db_world
    quiet, loud = ids.new_id('execution'), ids.new_id('execution')
    events = [*_calls(), {'type': 'tool_result', 'tool_use_id': 'tu_1', 'is_error': False}]
    _stream(quiet, events)
    _stream(loud, events)
    k = _mission(db, who, events=0, executions=[
        {'id': quiet, 'harness_id': 'fake', 'pid': None, 'attempt': 1, 'state': 'RUNNING'},
        {'id': loud, 'harness_id': 'fake', 'pid': 4242, 'create_time': 1.0, 'attempt': 2,
         'state': 'RUNNING'}])
    t = _read(db, k['mid'], _Registry(fake=FakeHarness()))
    q, l = t['executions']
    assert (q['available'], q['truncated'], q['lanes']) == (False, False, [])
    assert l['available'] is True
    assert [ln['lane'] for ln in l['lanes']] == ['main']
    assert l['lanes'][0]['steps'][1]['result'] == 2


def test_the_trace_answers_about_its_own_mission_alone(db_world):
    """trace.py:71-72 (the mission argument at queries.py:497 and the about filter
    at queries.py:285-287, `source_id in (r.entity.subject.id, ...)`). Drop the
    mission filter and another mission's decisions — and a decision about no
    mission at all — ride along; drop the `source` clause of the about filter
    and a task's route decision, found only by its mission, disappears."""
    db, who = db_world
    a, b = _mission(db, who, events=0), _mission(db, who, events=0)
    mine, theirs, none = (ids.new_id('policy_decision') for _ in range(3))
    ra, rb, rt, rx = (ids.new_id('route_decision') for _ in range(4))

    def run(tx, **_):
        for pid, mid in ((mine, a['mid']), (theirs, b['mid']), (none, None)):
            tx.insert(entities.PolicyDecision(id=pid, decision='DENY', stage='dispatch',
                                              reason='yours or nobody', mission_id=mid),
                      actor=who)
        tx.insert(entities.RouteDecision(id=ra, subject=Ref('mission', a['mid'])),
                  actor=who)
        tx.insert(entities.RouteDecision(id=rb, subject=Ref('mission', b['mid'])),
                  actor=who)
        tx.insert(entities.RouteDecision(id=rt, subject=Ref('task', a['tid']),
                                         source=Ref('mission', a['mid'])), actor=who)
        tx.insert(entities.RouteDecision(id=rx, subject=Ref('task', b['tid']),
                                         source=Ref('mission', b['mid'])), actor=who)
        tx.append(_witness(who))
    db.writer.execute(run, {})
    t = _read(db, a['mid'], _Registry())
    assert [d['id'] for d in t['policy_decisions']] == [mine]
    assert sorted(d['id'] for d in t['route_decisions']) == sorted([ra, rt])
    assert theirs not in json.dumps(t) and none not in json.dumps(t)
    schemas.validate(t, schemas.TYPES['Trace'])


def test_homes_reach_every_projection_and_lanes_are_cut_from_the_scrubbed_copy(db_world,
                                                                                monkeypatch):
    """trace.py:55-56 and 62 — `homes = _homes(conn, homes)`, the same homes to
    the timeline, and `o = public_output(output.read(e, adapter), homes)`
    before `lanes(o['events'])` at trace.py:68. Pass a homes built (lazily, once)
    from a callable: if the trace dropped `homes=` anywhere the raw secret
    survives the read, and if lanes were cut from the unprojected read the raw
    secret survives inside a lane step."""
    db, who = db_world
    eid = ids.new_id('execution')
    k = _mission(db, who, events=0, executions=[
        {'id': eid, 'harness_id': 'ghost', 'state': 'RUNNING'}])

    def note(tx, **_):
        tx.append(new_event('mission.updated', Ref('mission', k['mid']), who,
                            payload={'note': 'log %s/note.log' % GHOST},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(note, {})
    raw = [{'type': 'assistant', 'text': 'ran in %s/work' % GHOST},
           {'type': 'tool', 'name': 'Bash', 'id': 'tu_9'}]
    monkeypatch.setattr(trace.output, 'read',
                        lambda e, a: {'available': True, 'truncated': True,
                                      'events': [dict(r) for r in raw]})
    built = []

    def build():
        built.append(1)
        return Homes((GHOST,), (), shorts=lambda p: None, platform='neutral')

    t = _read(db, k['mid'], _Registry(), homes=build)
    assert len(built) == 1                                        # materialised exactly once
    assert t['executions'][0]['available'] is True                  # the read's own answer
    assert t['executions'][0]['truncated'] is True                  # passes through trace.py:67
    step = t['executions'][0]['lanes'][0]['steps'][0]
    assert step['text'] == 'ran in its home/work'                   # scrubbed BEFORE lanes
    assert 'ghosthome' not in json.dumps(t)                         # neither events nor lanes


# ── trace: the bounded read: window, order, flags ───────────────────────────

def _three_execs():
    """Three execution ids (pinned ULIDs, identical on every platform) and the
    id-sorted order: inserted a, b, c, they sort b, a, c."""
    a = ids.new_id('execution', at_ms=2000, entropy=1)
    b = ids.new_id('execution', at_ms=1000, entropy=2)
    c = ids.new_id('execution', at_ms=3000, entropy=3)
    return ([{'id': x, 'state': 'RUNNING', 'attempt': n}
             for n, x in enumerate((a, b, c), start=1)], [b, a, c])


def test_executions_are_read_in_id_order_not_in_written_order(db_world, monkeypatch):
    """trace.py:57-58 — `sorted(rows.where(...), key=lambda r: r.entity.id)`.
    Without the sort the answer (and the newest window below) follows insertion
    (rowid) order, so "the newest executions" would stop being newest for any
    mission whose retries were not written in id order."""
    db, who = db_world
    seeds, wanted = _three_execs()
    k = _mission(db, who, events=0, executions=seeds)
    reads = []
    monkeypatch.setattr(trace.output, 'read',
                        lambda e, a: (reads.append(e.id) or
                                      {'available': False, 'truncated': False, 'events': []}))
    t = _read(db, k['mid'], _Registry())
    assert [x['id'] for x in t['executions']] == wanted == reads
    assert t['executions_truncated'] is False


def test_only_the_newest_executions_are_read_and_the_trace_says_so(db_world, monkeypatch):
    """trace.py:59 (`for r in rs[-MAX_EXECUTIONS:]`) and trace.py:73
    (`'executions_truncated': len(rs) > MAX_EXECUTIONS`). With `>=` the flag
    cries truncation on a full-but-legal read; without the slice every retry
    of a long mission costs an output read and a live inspect."""
    db, who = db_world
    seeds, wanted = _three_execs()
    k = _mission(db, who, events=0, executions=[dict(s) for s in seeds])
    reads = []
    monkeypatch.setattr(trace.output, 'read',
                        lambda e, a: (reads.append(e.id) or
                                      {'available': False, 'truncated': False, 'events': []}))
    monkeypatch.setattr(trace, 'MAX_EXECUTIONS', 2)
    t = _read(db, k['mid'], _Registry())
    assert [x['id'] for x in t['executions']] == reads == wanted[1:]
    assert t['executions_truncated'] is True
    monkeypatch.setattr(trace, 'MAX_EXECUTIONS', 3)
    t = _read(db, k['mid'], _Registry())
    assert len(t['executions']) == 3 and t['executions_truncated'] is False


def test_a_cut_event_window_says_it_was_cut(db_world, monkeypatch):
    """trace.py:69-70 — `t['events'][::-1]` and `'truncated': t['next_before']
    is not None` (set by attention.py:158 only when the read came back full).
    Without the reversal the trace answers its events newest-first; with the
    flag inverted, or with `is not None` replaced by a truthiness test against
    a seq of 0, a client tails forever over the same page."""
    db, who = db_world
    k = _mission(db, who, events=3)
    monkeypatch.setattr(trace, 'MAX_EVENTS', 2)
    t = _read(db, k['mid'], _Registry())
    assert [e['payload']['tag'] for e in t['events']] == [2, 3]      # oldest first, newest two
    assert t['truncated'] is True
    monkeypatch.setattr(trace, 'MAX_EVENTS', 4)
    t = _read(db, k['mid'], _Registry())
    assert [e['payload']['tag'] for e in t['events']] == [1, 2, 3]
    assert t['truncated'] is False


@pytest.mark.xfail(strict=True, reason='trace.py:59: `rs[-MAX_EXECUTIONS:]` is the WHOLE list '
                                       'when MAX_EXECUTIONS is 0 (rs[-0:] is rs[0:]): a zero cap '
                                       'must read nothing (fail closed), not everything, and the '
                                       'bounded-read comment above the constant asks for it')
def test_a_zero_cap_on_executions_reads_none(db_world, monkeypatch):
    db, who = db_world
    seeds, wanted = _three_execs()
    k = _mission(db, who, events=0, executions=seeds)
    monkeypatch.setattr(trace, 'MAX_EXECUTIONS', 0)
    t = _read(db, k['mid'], _Registry())
    assert t['executions'] == []
    assert t['executions_truncated'] is True


# ── trace: the read is the whole answer, twice over ─────────────────────────

def test_a_mission_with_nothing_under_it_is_still_a_full_empty_trace(db_world):
    """the empty-input shapes: trace.py:57-59 (`sorted([])` then `rs[-50:]`),
    trace.py:73 (`len([]) > MAX` False) and attention.py:151-152 (no seqs: the
    early `next_before: None` answer, hence truncated False at trace.py:70). A
    mission with no events and no rows answers the complete empty shape; were
    any of these raise or omit a key, the schema validate below refuses."""
    db, who = db_world
    k = _mission(db, who, events=0)
    t = _read(db, k['mid'], _Registry())
    assert t == {'mission_id': k['mid'], 'events': [], 'truncated': False,
                 'policy_decisions': [], 'route_decisions': [], 'executions': [],
                 'executions_truncated': False, 'lessons': [], 'lessons_more': False}
    schemas.validate(t, schemas.TYPES['Trace'])


def test_the_same_request_replays_identically_and_writes_nothing(db_world):
    """the read-only promise of trace.py:53 (`A read: nothing here writes`) and
    its replay safety: the reversal at trace.py:69, the per-call `lanes` at 68
    and the fresh `homes` at 55 must make a second identical request — even on
    the very same connection — return the identical answer, and the database
    must hold the same rows afterwards. An in-place `t['events'].reverse()` or
    a shared step dict would corrupt the second read; the events count proves
    the reads wrote nothing."""
    db, who = db_world
    eid, cp, rd, pd = (ids.new_id(k) for k in ('execution', 'checkpoint',
                                               'route_decision', 'policy_decision'))
    k = _mission(db, who, events=1, executions=[
        {'id': eid, 'harness_id': 'fake', 'pid': 4242, 'create_time': 1.0,
         'state': 'ENDED_OK', 'route_decision_id': rd, 'policy_decision_id': pd}])
    _stream(eid, [*_calls(),
                  {'type': 'tool_result', 'tool_use_id': 'tu_1', 'is_error': False},
                  {'type': 'assistant', 'text': 'side', 'lane': 'tu_1'}])

    def checkpoint(tx, **_):
        tx.insert(entities.Checkpoint(id=cp, execution_id=eid, mission_id=k['mid'],
                                      task_id=k['tid'], trigger='task_boundary',
                                      objective='ship it'), actor=who)
        tx.append(_witness(who))
    db.writer.execute(checkpoint, {})

    with db.read() as conn:
        before = conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        t1 = trace.trace(conn, k['mid'], _Registry(fake=FakeHarness()))
        t2 = trace.trace(conn, k['mid'], _Registry(fake=FakeHarness()))
    t3 = _read(db, k['mid'], _Registry(fake=FakeHarness()))
    with db.read() as conn:
        after = conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    assert json.dumps(t1, sort_keys=True) == json.dumps(t2, sort_keys=True) \
        == json.dumps(t3, sort_keys=True)
    assert before == after
    schemas.validate(t1, schemas.TYPES['Trace'])
    (x,) = t1['executions']
    assert (x['route_decision_id'], x['policy_decision_id']) == (rd, pd)   # pass-through, 64-65
    assert x['checkpoints'] == [cp]                                        # trace.py:66
    assert [ln['lane'] for ln in x['lanes']] == ['main', 'tu_1']
    assert x['lanes'][0]['steps'][1]['result'] == 2
    assert x['lanes'][1]['from'] == 1
