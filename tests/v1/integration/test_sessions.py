"""P12 sessions on the real database (p12-design-gate §7, §9, §10.2, §14,
§17): registration, resume, hand-off, lineage, the brief, freshness, duplicate
requests, restart — over two fake session harnesses and a recording terminal,
so nothing is ever launched."""

import json
import os

import pytest

from archeus.core.application import authorization, lifecycle, sessions as S
from archeus.core.domain import entities
from archeus.core.sessions import service as SV
from archeus.harnesses.sessions import FakeSessions
from archeus.infra.artifacts import store as artifacts

from v1.integration.test_execution import Rig, _running, ended
from v1.integration.test_policy import task


class Terminal:
    """The node's terminal opener, recorded instead of opened."""

    def __init__(self, fail=None):
        self.opened, self.fail = [], fail

    def open_terminal(self, argv, *, cwd, env, title=''):
        self.opened.append({'argv': list(argv), 'cwd': cwd, 'env': dict(env)})
        return (None, self.fail) if self.fail else (object(), None)


class SRig(Rig):
    def __init__(self, db, **kw):
        super().__init__(db, **kw)
        self.fa, self.fb = FakeSessions('fake_a'), FakeSessions('fake_b', models=('b-small',
                                                                                  'b-large'),
                                                              efforts=('min', 'max'))
        self.term = Terminal()
        self.sessions = SV.SessionService(db, system=self.system, adapters=[self.fa, self.fb],
                                          node=self.term)

    def session(self, harness='fake_a', turns=(('user', 'fix the login'),
                                               ('assistant', 'I will look at auth.py')),
                mission=None, project=None, model='fake-model', effort='low'):
        """A session the user started themselves and registers now."""
        ref = 'ref-%d' % len(self.all(entities.Session))
        adapter = self.fa if harness == 'fake_a' else self.fb
        adapter.write(ref, turns)
        return self.sessions.register(self.user, harness_id=harness, cwd=str(self.cwd),
                                      provider_session_ref=ref, mission_id=mission,
                                      project_id=project, model=model, effort=effort)

    def s(self, sid):
        return self.one(entities.Session, id=sid)


@pytest.fixture
def x(db, tmp_path):
    rig = SRig(db)
    rig.cwd = tmp_path / 'work'
    rig.cwd.mkdir()
    yield rig
    rig.cleanup()


# ── registration and the machine ─────────────────────────────────────────────

def test_T01_a_registered_session_is_open_and_has_seen_nothing_before_now(x):
    head = x.head()
    s = x.session()
    row = x.s(s['id'])
    assert (row.state, row.mode, row.last_seen_seq) == ('OPEN', 'manual', head)
    assert 'transcript_path' not in s                     # stays inside Core


def test_T02_only_a_user_device_changes_a_session(x):
    s = x.session()
    for who in (x.system, x.brain):
        with pytest.raises(authorization.NotPermitted):
            x.do(S.close, who=who, session_id=s['id'])
    with pytest.raises(authorization.NotPermitted):
        x.do(S.vanished, who=x.user, session_id=s['id'], reason='no')


def test_T03_close_reopen_vanish_reappear(x):
    s = x.session()
    x.do(S.close, who=x.user, session_id=s['id'])
    x.do(S.reopen, who=x.user, session_id=s['id'])
    x.do(S.vanished, who=x.system, session_id=s['id'], reason='gone')
    x.do(S.reappeared, who=x.system, session_id=s['id'])
    moves = [(e['payload']['from'], e['payload']['to'])
             for e in x.events('session.state_changed')]
    assert moves == [('OPEN', 'CLOSED'), ('CLOSED', 'OPEN'), ('OPEN', 'LOST'), ('LOST', 'OPEN')]


def test_T04_a_session_continues_only_a_mission_of_its_own_scope(x):
    mid = x.mission()
    s = x.session()
    x.do(S.link, who=x.user, session_id=s['id'], mission_id=mid)
    assert x.s(s['id']).mission_id == mid
    other = x.do(__import__('archeus.core.application.commands', fromlist=['x']).create_mission,
                 who=x.user, title='elsewhere', objective='o', workspace_id=
                 __import__('archeus.core.domain.ids', fromlist=['x']).new_id('workspace'))
    with pytest.raises(authorization.NotPermitted):
        x.do(S.link, who=x.user, session_id=s['id'], mission_id=other['id'])


# ── resume ───────────────────────────────────────────────────────────────────

def test_T10_resume_reopens_the_same_provider_session_on_its_own_configuration(x):
    s = x.session(model='fake-model', effort='high')
    out = x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    (spec,) = x.fa.launched
    assert (spec.resume_ref, spec.model, spec.effort) == (x.s(s['id']).provider_session_ref,
                                                          'fake-model', 'high')
    assert out['launch']['launched'] and x.s(s['id']).launched_seq == 1
    assert x.fb.launched == []                      # never another harness's


def test_T11_the_same_resume_request_twice_changes_nothing(x):
    s = x.session()
    x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    head = x.head()
    again = x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    assert again['duplicate'] and x.head() == head
    assert len(x.term.opened) == 1 and len(x.events('session.resumed')) == 1


def test_T12_a_model_switch_keeps_the_session_and_its_mission(x):
    mid = x.mission()
    s = x.session(mission=mid)
    x.sessions.resume(x.user, session_id=s['id'], request_id='r1', model='fake-large')
    row = x.s(s['id'])
    assert (row.model, row.mission_id, row.id) == ('fake-large', mid, s['id'])
    assert x.fa.launched[-1].model == 'fake-large'
    with pytest.raises(ValueError, match='does not offer'):
        x.sessions.resume(x.user, session_id=s['id'], request_id='r2', model='b-large')


def test_T13_a_gone_provider_session_is_lost_and_not_resumed(x):
    s = x.session()
    os.remove(x.fa.path(x.s(s['id']).provider_session_ref))
    with pytest.raises(SV.Refused, match='gone'):
        x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    assert x.s(s['id']).state == 'LOST' and x.term.opened == []


def test_T14_the_brief_is_current_state_and_the_changes_since_its_own_cursor(x):
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 30}]
    mid = x.ready(task('t1', 'write_repo'))
    s = x.session(mission=mid)
    e = _running(x, mid)
    x.do(__import__('archeus.core.application.executions', fromlist=['x']).Executions(
        missions=x.missions).stop_execution, who=x.user, execution_id=e.id)
    x.drive(mid, ended(x, e.id))
    out = x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    b = out['brief']
    (t,) = b['mission']['tasks']
    assert t['execution']['state'] == 'ENDED_KILLED'            # what the rows say now
    assert b['mission']['state'] == x.m(mid).state
    assert any(g['ref'] == {'kind': 'mission', 'id': mid} for g in b['changes']['groups'])
    assert b['context']['package_id'] and b['context']['rebuilt']
    text = artifacts.get(out['artifact_sha']).decode('utf-8')
    assert 'Since you left' in text and 'ENDED_KILLED' in text


def test_T15_a_fresh_package_is_reused_and_a_stale_one_rebuilt(x):
    mid = x.mission()
    s = x.session(mission=mid)
    first = x.sessions.resume(x.user, session_id=s['id'], request_id='r1')['brief']['context']
    again = x.sessions.resume(x.user, session_id=s['id'], request_id='r2')['brief']['context']
    assert again == dict(first, rebuilt=False)                   # nothing changed: reused
    x.propose(mid, task('t1', 'write_repo'))                     # the mission moved on
    third = x.sessions.resume(x.user, session_id=s['id'], request_id='r3')['brief']['context']
    assert third['rebuilt'] and third['package_id'] != first['package_id']


def test_T16_a_session_resume_grants_nothing(x):
    s = x.session()
    before = len(x.all(entities.PolicyDecision)), len(x.all(entities.Approval))
    x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    assert (len(x.all(entities.PolicyDecision)), len(x.all(entities.Approval))) == before


# ── hand-off ─────────────────────────────────────────────────────────────────

def test_T20_a_handoff_is_a_new_linked_session_and_the_source_is_untouched(x):
    s = x.session()
    with x.db.read() as r:
        from archeus.infra.db import rows
        before = rows.get(r, entities.Session, s['id'])
    out = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                             harness_id='fake_b', model='b-large', reason='try pi')
    t = x.s(out['id'])
    assert (t.handoff_from_session_id, t.harness_id, t.model, t.mode) == (
        s['id'], 'fake_b', 'b-large', 'interactive_attached')
    with x.db.read() as r:
        assert rows.get(r, entities.Session, s['id']) == before
    (ev,) = x.events('session.handed_off')
    assert ev['payload']['from'] == s['id'] and ev['payload']['to'] == t.id


def test_T21_the_target_gets_the_rendered_artifact_and_none_of_the_source_s_own_state(x):
    s = x.session(turns=[('user', 'fix the login'), ('assistant', 'token sk-' + 'a' * 20),
                         ('assistant', 'done with step one')])
    src = x.s(s['id'])
    out = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                             harness_id='fake_b')
    (spec,) = x.fb.launched
    assert spec.resume_ref is None and src.provider_session_ref not in json.dumps(
        x.term.opened)
    path = SV.delivery_path(str(x.cwd), out['id'])
    text = open(path, encoding='utf-8').read()
    assert 'fix the login' in text and 'done with step one' in text
    assert 'sk-aaaa' not in text and '[redacted]' in text
    assert path in spec.opening


def test_T22_the_same_handoff_request_makes_one_target(x):
    s = x.session()
    a = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                           harness_id='fake_b')
    b = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                           harness_id='fake_b')
    assert a['id'] == b['id'] and b['duplicate']
    assert len(x.all(entities.Session)) == 2 and len(x.term.opened) == 1


def test_T23_an_unknown_model_is_refused_and_an_inherited_one_dropped(x):
    s = x.session(model='fake-model', effort='low')
    with pytest.raises(ValueError, match='does not offer'):
        x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                           harness_id='fake_b', model='fake-model')
    out = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h2',
                             harness_id='fake_b')
    assert (x.s(out['id']).model, x.s(out['id']).effort) == (None, None)


def test_T24_a_mission_session_hands_off_current_state_not_the_transcript(x):
    mid = x.mission()
    x.propose(mid, task('t1', 'write_repo'))
    s = x.session(mission=mid, turns=[('user', 'SECRET-TRANSCRIPT-LINE')])
    out = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                             harness_id='fake_b')
    text = artifacts.get(x.s(out['id']).handoff_artifact_sha).decode('utf-8')
    assert 'SECRET-TRANSCRIPT-LINE' not in text and mid in text and 't1' in text
    assert x.s(out['id']).mission_id == mid


def test_T25_lineage_chains(x):
    s = x.session()
    b = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                           harness_id='fake_b')
    x.fb.write(x.s(b['id']).provider_session_ref, [('user', 'carry on in b')])
    c = x.sessions.handoff(x.user, source_session_id=b['id'], request_id='h2',
                           harness_id='fake_a')
    with x.db.read() as r:
        v = S.view(r, c['id'])
        assert v['lineage'] == [b['id'], s['id']]
        assert S.view(r, s['id'])['targets'] == [b['id']]


# ── restart, launches ────────────────────────────────────────────────────────

def test_T30_a_restarted_core_expires_pending_launches_and_opens_nothing(x):
    x.term.fail = 'the terminal would not open'
    s = x.session()
    x.do(S.resume, who=x.user, session_id=s['id'], request_id='r1')   # committed, not launched
    fresh = SV.SessionService(x.db, system=x.system, adapters=[x.fa, x.fb], node=Terminal())
    out = fresh.sweep()
    assert out['expired'] == [s['id']] and fresh.node.opened == []
    assert x.s(s['id']).launch_error == 'launch_expired'


def test_T31_a_failed_launch_is_recorded_and_resuming_retries_it(x):
    x.term.fail = 'no terminal'
    s = x.session()
    out = x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    assert not out['launch']['launched'] and x.s(s['id']).launch_error == 'no terminal'
    x.term.fail = None
    out = x.sessions.resume(x.user, session_id=s['id'], request_id='r2')
    assert out['launch']['launched'] and x.s(s['id']).launch_error is None


def test_T32_the_sweep_marks_a_vanished_provider_session_lost(x):
    s = x.session()
    os.remove(x.fa.path(x.s(s['id']).provider_session_ref))
    assert x.sessions.sweep()['moved'] == [(s['id'], 'LOST')]


def test_T33_nothing_in_a_session_its_events_or_artifacts_carries_a_secret(x):
    s = x.session(turns=[('user', 'export TOKEN=ghp_' + 'z' * 30)])
    out = x.sessions.handoff(x.user, source_session_id=s['id'], request_id='h1',
                             harness_id='fake_b')
    x.sessions.resume(x.user, session_id=s['id'], request_id='r1')
    blobs = [artifacts.get(x.s(out['id']).handoff_artifact_sha).decode('utf-8')]
    blobs += [json.dumps(e) for e in x.events('session.created') + x.events(
        'session.handed_off') + x.events('session.resumed')]
    blobs += [json.dumps(v.to_dict()) for v in x.all(entities.Session)]
    assert not [b for b in blobs if 'ghp_zzz' in b]


def test_T34_a_headless_session_cannot_be_resumed(x):
    x.scenarios['t1'] = [{'emit': {'type': 'result', 'summary': 'done'}}]
    mid = x.ready(task('t1', 'write_repo'))
    e = x.drive(mid, lambda: x.exe(mission_id=mid))
    x.drive(mid, ended(x, e.id))
    x.drive(mid, lambda: x.state(e.id).session_id)
    s = x.s(x.state(e.id).session_id)
    assert (s.mode, s.state, s.execution_id) == ('headless', 'CLOSED', e.id)
    with pytest.raises(lifecycle.IllegalTrigger):
        x.do(S.resume, who=x.user, session_id=s.id, request_id='r1')
