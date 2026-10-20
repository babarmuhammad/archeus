"""P21 slice C (p21-design-gate D3, D14; R13-03, R13-05): a mission's trace read
from what Core already records, the digest's message rows folded into one, and
a bare `why` in a mission's thread answered about that mission."""

import json
import os

from archeus.api import schemas
from archeus.core.application import trace
from archeus.core.domain import entities, ids
from archeus.harnesses.claude_code import adapter
from archeus.harnesses.fake import FakeHarness
from archeus.infra.paths import ExecPaths
from v1.integration.test_intent import make  # noqa: F401 (a fixture)
from v1.integration.test_ui_seams import _mission, _plan, _task, _tx


class _Registry:
    def __init__(self, **adapters):
        self._a = adapters

    def ids(self):
        return list(self._a)

    def get(self, hid):
        return self._a[hid]


def _calls(lane=None):
    return [{'type': 'assistant', 'text': 'look', 'lane': lane},
            {'type': 'tool', 'name': 'Task', 'input': {}, 'id': 'tu_1', 'lane': lane}]


def test_a_call_is_paired_with_its_result_inside_its_sidechain_lane():
    events = [*_calls(),
              {'type': 'tool', 'name': 'Read', 'input': {}, 'id': 'tu_2', 'lane': 'tu_1'},
              {'type': 'usage', 'usage': {}},
              {'type': 'tool_result', 'is_error': True, 'tool_use_id': 'tu_2', 'lane': 'tu_1'},
              {'type': 'tool', 'name': 'Grep', 'input': {}, 'id': 'tu_3', 'lane': 'tu_1'},
              {'type': 'tool_result', 'is_error': False, 'tool_use_id': 'tu_1'},
              {'type': 'result', 'summary': 'done'}]
    main, side = trace.lanes(events)
    assert (main['lane'], main['from'], side['lane'], side['from']) == ('main', None, 'tu_1', 1)
    task = main['steps'][1]
    assert (task['name'], task['result'], main['steps'][2]['call']) == ('Task', 6, 1)
    read, err, grep = side['steps']
    assert (read['result'], err['call'], err['is_error']) == (4, 2, True)
    assert 'result' not in grep                                 # still running: no result
    assert all('input' not in s for lane in (main, side) for s in lane['steps'])


def test_the_claude_stream_carries_the_call_ids_and_the_sidechain():
    raw = [{'type': 'assistant', 'parent_tool_use_id': 'tu_1', 'message': {'content': [
               {'type': 'tool_use', 'id': 'tu_2', 'name': 'Read', 'input': {'file_path': 'a'}}]}},
           {'type': 'user', 'parent_tool_use_id': 'tu_1', 'message': {'content': [
               {'type': 'tool_result', 'tool_use_id': 'tu_2', 'is_error': False}]}}]
    call, res = [e for r in raw for e in adapter.normalise(r)]
    assert (call['id'], call['lane'], res['tool_use_id'], res['lane']) == (
        'tu_2', 'tu_1', 'tu_2', 'tu_1')
    (lane,) = trace.lanes([call, res])
    assert (lane['lane'], lane['steps'][0]['result']) == ('tu_1', 1)


def test_the_trace_reads_the_missions_events_decisions_and_lanes(db, actor):
    mine, other = _mission(db, actor, 'mine'), _mission(db, actor, 'other')
    pid = _plan(db, actor, mine)
    tid = _task(db, actor, mine, pid)
    exe = ids.new_id('execution')
    _tx(db, lambda tx: tx.insert(entities.Execution(
        id=exe, task_id=tid, mission_id=mine, harness_id='fake', pid=os.getpid(),
        create_time=1.0), actor=actor))
    from archeus.core.domain.events import new_event
    from archeus.core.domain.values import Ref
    _tx(db, lambda tx: tx.append(new_event('mission.updated', Ref('mission', mine), actor,
                                           payload={}, workspace=ids.GLOBAL_WORKSPACE)))
    p = ExecPaths(exe)
    os.makedirs(p.dir, exist_ok=True)
    secret = 'dev_' + 'x' * 30
    with open(p.stream, 'w', encoding='utf-8') as f:
        for e in [*_calls(), {'type': 'assistant', 'text': 'key %s' % secret, 'lane': 'tu_1'},
                  {'type': 'tool_result', 'tool_use_id': 'tu_1', 'is_error': False}]:
            f.write(json.dumps(e) + '\n')
    with db.read() as conn:
        t = trace.trace(conn, mine, _Registry(fake=FakeHarness()))
    schemas.validate(t, schemas.TYPES['Trace'])
    seqs = [e['seq'] for e in t['events']]
    assert len(seqs) >= 2 and seqs == sorted(seqs) and t['truncated'] is False  # oldest first
    assert ('mission', mine) in {(e['subject']['kind'], e['subject']['id'])
                                 for e in t['events']}
    assert other not in json.dumps(t['events'])
    (x,) = t['executions']
    assert (x['id'], x['available'], [ln['lane'] for ln in x['lanes']]) == (
        exe, True, ['main', 'tu_1'])
    assert x['lanes'][0]['steps'][1]['result'] == 3
    assert secret not in json.dumps(t)                                  # the redacted read


def test_the_trace_reads_only_the_newest_executions_and_says_so(db, actor, monkeypatch):
    mine = _mission(db, actor, 'mine')
    tid = _task(db, actor, mine, _plan(db, actor, mine))
    made = []
    for n in range(1, 4):
        made.append(ids.new_id('execution'))
        _tx(db, lambda tx, x=made[-1], n=n: tx.insert(entities.Execution(
            id=x, task_id=tid, mission_id=mine, harness_id='fake', attempt=n), actor=actor))
    read = []
    monkeypatch.setattr(trace.output, 'read', lambda e, a: read.append(e.id) or {
        'available': False, 'truncated': False, 'events': []})
    monkeypatch.setattr(trace, 'MAX_EXECUTIONS', 2)
    with db.read() as conn:
        t = trace.trace(conn, mine, _Registry(fake=FakeHarness()))
    schemas.validate(t, schemas.TYPES['Trace'])
    assert [x['id'] for x in t['executions']] == read == sorted(made)[1:]
    assert t['executions_truncated'] is True
    monkeypatch.setattr(trace, 'MAX_EXECUTIONS', 3)
    with db.read() as conn:
        assert trace.trace(conn, mine, _Registry(fake=FakeHarness()))['executions_truncated'] is False


def test_the_trace_route_answers_and_refuses_an_unknown_mission(tc):
    mid = tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                                'idempotency_key': 'k-trace'}).json()['id']
    r = tc.http('GET', '/v1/missions/%s/trace' % mid)
    assert r.status == 200 and r.json()['mission_id'] == mid and r.json()['executions'] == []
    schemas.validate(r.json(), schemas.TYPES['Trace'])
    assert tc.http('GET', '/v1/missions/%s/trace' % ids.new_id('mission')).status == 404


# ── R13-05: a bare `why` in a mission's thread is about that mission ──

def test_a_bare_why_in_a_thread_says_why_its_mission_exists(make):  # noqa: F811
    from archeus.core.application import commands, queries
    from archeus.core.application.conversation import post_message
    r = make([])
    mid = r.run(commands.create_mission, title='Fix it', objective='fix the parser')['id']
    posted = r.run(post_message, text='why', conversation_id=mid)
    r.settle()
    reply = r.read(queries.reply_to, posted['message_id'])
    assert reply['text'] == ('This mission exists because you asked for it in a conversation: '
                             '"fix the parser".')
    assert [(c['type'], c['ref']) for c in reply['cards']] == [
        ('mission', {'kind': 'mission', 'id': mid})]
    (it,) = r.all(entities.Intent, message_id=posted['message_id'])
    assert (it.via, [t['id'] for t in it.target_refs]) == ('grammar', [mid])
    p = r.run(post_message, text='why')                     # no thread: not the grammar's
    r.settle()
    (it2,) = r.all(entities.Intent, message_id=p['message_id'])
    assert it2.via != 'grammar'


def test_a_declined_reading_names_no_adr():
    import inspect
    from archeus.core.application import conversation
    assert 'ADR-0021' not in inspect.getsource(conversation.Conversations.decline)


# ── R13-03: the digest names no message rows ──

def test_the_digest_folds_messages_into_their_mission_or_one_new_messages_row(make):  # noqa: F811
    from archeus.core.application import commands, queries
    from archeus.core.application.conversation import post_message
    from archeus.core.world import digest
    r = make([])
    mid = r.run(commands.create_mission, title='Fix it', objective='o')['id']
    r.run(post_message, text='status')
    r.run(post_message, text='why', conversation_id=mid)
    r.settle()
    d = r.read(digest.digest)
    kinds = {(g['ref']['kind'], g['headline']) for g in d['groups']}
    assert not any(k == 'message' for k, _ in kinds)
    (conv,) = [g for g in d['groups'] if g['ref']['kind'] == 'conversation']
    primary = r.read(queries.messages, 'primary')
    assert (conv['headline'], conv['count']) == ('new_messages', len(primary)) and len(primary) == 2
    (m,) = [g for g in d['groups'] if g['ref'] == {'kind': 'mission', 'id': mid}]
    assert any(t.startswith('message.') for t in m['types'])   # the thread's turns
    assert d['groups'][-1] is conv                          # the least urgent row, last
