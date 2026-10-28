"""T-144 N-3: the write and worker paths that build `Homes` (resume, hand-off,
checkpoint artifact, context package, planner package, automation render) read
the live adapter registry and callers bound to the writer, so a default home no
stored snapshot knows is scrubbed there too. The binding is outside the command
kwargs: it never enters an idempotency hash."""

import dataclasses
import hashlib
import json

import pytest

from archeus.core import ports
from archeus.core.application import commands, sessions
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.infra.artifacts import store
from archeus.infra.db import rows
from v1.integration.test_automation import rig  # noqa: F401  (fixture)
from v1.integration.test_planning import ONE, fake, make  # noqa: F401  (make is a fixture)
from v1.integration.test_routing import Rig
from v1.integration.test_t144_event_reads import _checkpoint
from v1.integration.test_t144_leak_sweep import HomeCaller


@pytest.fixture(autouse=True)
def no_8dot3_probe(monkeypatch):
    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)


def _live(tmp_path):
    return str(tmp_path / 'Live-Only-Default')


def _bind(db, tmp_path, bound=True):
    live = _live(tmp_path)
    db.writer.live = (None, [HomeCaller(live, 'live-only')]) if bound else (None, ())
    return live


def _session_world(db, tmp_path):
    r = Rig(db)
    live = _live(tmp_path)
    mid = r.ready()
    r.dispatch(mid)
    _checkpoint(r, mid, live, 'k')
    sid = ids.new_id('session')

    def session(tx, *, actor):
        tx.insert(entities.Session(id=sid, harness_id='fake', workspace_id=ids.GLOBAL_WORKSPACE,
                                   cwd=str(tmp_path), mode='interactive_attached',
                                   mission_id=mid), actor=actor)
        tx.append(new_event_created(sid, mid, actor))
    r.do(session)
    return r, live, sid, mid


def new_event_created(sid, mid, actor):
    from archeus.core.domain.events import new_event
    return new_event('session.created', Ref('session', sid), actor, payload={
        'mode': 'interactive_attached', 'harness_id': 'fake', 'account_id': None,
        'mission_id': mid, 'handoff_from': None})


def test_N3_resume_brief_and_artifact_scrub_a_live_only_default(db, tmp_path):
    r, live, sid, _ = _session_world(db, tmp_path)
    _bind(db, tmp_path)
    out = r.do(sessions.resume, who=r.user, session_id=sid, request_id='r1')
    text = store.get(out['artifact_sha']).decode('utf-8')
    assert live not in text and live not in json.dumps(out['brief'])
    assert 'its home/settings.json' in text


def test_N3_without_the_binding_the_live_home_is_still_raw(db, tmp_path):
    r, live, sid, _ = _session_world(db, tmp_path)
    _bind(db, tmp_path, bound=False)
    out = r.do(sessions.resume, who=r.user, session_id=sid, request_id='r1')
    assert live in store.get(out['artifact_sha']).decode('utf-8')


def test_N3_handoff_text_scrubs_a_live_only_default(db, tmp_path):
    r, live, sid, _ = _session_world(db, tmp_path)
    _bind(db, tmp_path)
    t = r.do(sessions.handoff, who=r.user, source_session_id=sid, request_id='h1',
             harness_id='fake')
    text = store.get(t['handoff_artifact_sha']).decode('utf-8')
    assert live not in text and 'its home/settings.json' in text


def test_N3_checkpoint_artifact_scrubs_a_live_only_default_and_the_row_stays_raw(db, tmp_path):
    from archeus.core.execution import checkpoint
    r = Rig(db)
    live = _bind(db, tmp_path)
    mid = r.ready()
    ex = r.one(entities.Execution, id=r.dispatch(mid)['execution_id'])
    r.do(checkpoint.derive, execution=ex, facts={'last_error': 'read ' + live + '/x'})
    cp = r.one(entities.Checkpoint, execution_id=ex.id)
    assert cp.open_problems == ('last error: read ' + live + '/x',)
    text = store.get(cp.artifact_sha).decode('utf-8')
    assert 'last error: read its home/x' in text and live not in text


def test_N3_recorded_context_package_scrubs_a_live_only_default(db, tmp_path):
    from v1.integration.test_world import Harness
    live = _live(tmp_path)
    parent = tmp_path / 'Live-Only-Default' / 'repos'
    parent.mkdir(parents=True)
    h = Harness(db, str(parent))
    pid = h.register('layered-python').project_id
    h.pump()
    mid = h.run(commands.create_mission, title='Dashboard', objective='o', project_id=pid)['id']
    record = {'actor': h.system, 'subject_kind': 'mission', 'subject_id': mid}
    raw = db.writer.execute(commands.record_context_package, record)
    assert json.dumps(live)[1:-1] in json.dumps(raw), 'the fixture must carry the live home unbound'
    _bind(db, tmp_path)
    pkg = db.writer.execute(commands.record_context_package, record)
    with db.read() as conn:
        stored = json.dumps(rows.get(conn, entities.ContextPackage, pkg['id']).entity.to_dict())
    assert json.dumps(live)[1:-1] not in stored and 'its home' in stored


def test_N3_planner_reads_a_reused_package_with_the_live_homes(make, tmp_path, monkeypatch):  # noqa: F811
    from archeus.core.planning import worker as W
    from archeus.infra.eventlog import outbox

    r = make([fake(ONE)], policy='ALLOW')
    live = _bind(r.db, tmp_path)
    mid = r.mission()
    r.to_reasoning(mid)
    seq = [e['seq'] for e in r.events('mission.state_changed')
           if e['payload']['to'] == 'REASONING'][-1]
    pkg_id = ids.new_id('context_package')
    with r.db.read() as conn:
        head = outbox.head(conn)

    def seed(tx, *, actor):
        from archeus.core.domain.events import new_event
        tx.insert(entities.ContextPackage(
            id=pkg_id, workspace_id=ids.GLOBAL_WORKSPACE, subject_kind='mission', subject_id=mid,
            as_of_seq=head, items=({'ref': {'kind': 'event', 'id': 'e'}, 'level': 'L3',
                                    'store': 'history', 'type': 'x', 'reason': 'at ' + live},)),
            actor=actor)
        tx.update(entities.Mission, mid, {'context_package_id': pkg_id}, actor=actor)
        tx.append(new_event('context_package.created', Ref('context_package', pkg_id), actor,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    r.sys(seed)
    seen = []
    real = W.planner.describe
    monkeypatch.setattr(W.planner, 'describe', lambda conn, pkg, m: seen.append(pkg) or real(conn, pkg, m))
    assert r.planner.plan(mid, seq, 'first plan').startswith('plan:')
    assert seen[0]['items'][0]['reason'] == 'at its home'


def test_N3_automation_render_scrubs_a_live_only_default(rig, tmp_path):  # noqa: F811
    live = _bind(rig.db, tmp_path)
    rig.automation(trigger={'type': 'mission.state_changed',
                            'where': {'reason': {'glob': '*Live-Only-Default*'}}},
                   template={'title': 'saw {payload.reason}', 'objective': 'o'})
    mid = rig.seed(title='other')
    rig.raw('mission.state_changed', Ref('mission', mid),
            {'to': 'CREATED', 'reason': 'read ' + live + '/x'})
    rig.pump()
    (made,) = rig.made()
    assert made.title == 'saw read its home/x'


def test_N3_the_binding_never_enters_a_command_identity(db, tmp_path):
    kw = dict(title='T', objective='o')

    def stored_hash():
        with db.read() as conn:
            return [tuple(x) for x in conn.execute(
                'SELECT command, request_hash FROM idempotency_keys')]

    r = Rig(db)
    _bind(db, tmp_path)
    first = db.writer.submit(commands.create_mission, dict(kw, actor=r.user), idempotency_key='k1')
    first.result()
    again = db.writer.submit(commands.create_mission, dict(kw, actor=r.user), idempotency_key='k1')
    assert again.result() == first.result() and again.replayed and not first.replayed
    name = 'archeus.core.application.commands.create_mission'
    blob = json.dumps({'command': name, 'args': dict(kw, actor=dataclasses.asdict(r.user))},
                      sort_keys=True)
    assert (name, hashlib.sha256(blob.encode('utf-8')).hexdigest()) in stored_hash()
    assert len(r.all(entities.Mission)) == 1


def test_N3_the_runtime_binds_its_registry_and_callers_to_the_writer(archeus_home):
    from archeus.core import engine, runtime
    from archeus.core.routing.usage import FakeUsageFeed
    from archeus.harnesses.fake import FakeCaller
    from v1.judge.http import TempCore
    caller = FakeCaller()
    core = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), callers=[caller],
        preference=ports.FixedOwnCallPreference(), usage=FakeUsageFeed())).start()
    try:
        registry, callers = core.core.db.writer.live
        assert registry is core.core.api.resources.registry and callers == [caller]
    finally:
        core.stop()
