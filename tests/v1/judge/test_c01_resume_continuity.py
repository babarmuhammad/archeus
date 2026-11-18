"""C1, C2, C8, C11, C13 — a returning session is told the world as it is now
(p12-design-gate §9, §11.4, §14, D9, D10, D21).

A user's session is registered on a fake session harness, Core and the work
move on while it is away, and resuming it reconstructs the current state and
what changed since it was last seen — never what it remembered. Nothing here
opens a terminal: the judge's Core records launches instead."""

from .support import events_of, wait_for, wait_state


def _session(client, rig, tmp_path, mission_id=None, **kw):
    ref = rig.provider_session('fake_a', [('user', 'build the report'),
                                          ('assistant', 'starting on the report')])
    return client.register_session(harness_id='fake_a', cwd=str(tmp_path), mission_id=mission_id,
                                   provider_session_ref=ref, model='fake-model', effort='low',
                                   **kw)


def test_C1_resume_after_an_interruption_reconstructs_the_mission_now(client, rig, tmp_path):
    m = client.create_mission(title='Report', objective='One task')
    s = _session(client, rig, tmp_path, mission_id=m['id'])
    wait_state(client, m['id'], 'COMPLETED')
    rig.restart_core()                                   # the interruption
    out = client.resume_session(s['id'], request_id='c1')
    brief = out['brief']
    assert brief['mission']['id'] == m['id']
    assert brief['mission']['state'] == client.get_mission(m['id'])['state'] == 'COMPLETED'
    assert any(g['ref'] == {'kind': 'mission', 'id': m['id']}
               for g in brief['changes']['groups'])
    assert brief['context']['package_id'] and brief['context']['rebuilt']
    assert client.get_session(s['id'])['state'] == 'OPEN'


def test_C2_an_execution_that_moved_while_away_is_shown_as_it_is(client, rig, tmp_path):
    rig.script_harness('t1', [{'emit': {'type': 'working'}}, {'sleep': 0.5},
                              {'emit': {'type': 'result', 'summary': 'done'}}])
    m = client.create_mission(title='Away', objective='One task')
    s = _session(client, rig, tmp_path, mission_id=m['id'])
    wait_for(lambda: events_of(client, 'execution.started'))
    wait_state(client, m['id'], 'COMPLETED')
    (t,) = client.resume_session(s['id'], request_id='c2')['brief']['mission']['tasks']
    assert t['execution']['state'] == 'ENDED_OK' and t['state'] != 'RUNNING'


def test_C13_current_state_wins_over_what_a_checkpoint_recorded(client, rig, tmp_path):
    m = client.create_mission(title='Checkpoint', objective='One task')
    s = _session(client, rig, tmp_path, mission_id=m['id'])
    wait_state(client, m['id'], 'COMPLETED')
    (ended,) = events_of(client, 'execution.ended')
    (cp,) = client.checkpoints(ended['subject']['id'])
    # the checkpoint was derived as the execution ended: its task was RUNNING
    assert any(step.endswith(': RUNNING') for step in cp['completed_steps'])
    (t,) = client.resume_session(s['id'], request_id='c13')['brief']['mission']['tasks']
    assert t['state'] != 'RUNNING'                       # the rows, not the checkpoint


def test_C8_sessions_survive_a_restart_and_no_launch_is_replayed(client, rig, tmp_path):
    s = _session(client, rig, tmp_path)
    client.resume_session(s['id'], request_id='c8')
    before = len(rig.launches())
    rig.restart_core()
    assert client.get_session(s['id'])['id'] == s['id']
    assert [x['id'] for x in client.list_sessions()] == [s['id']]
    assert len(rig.launches()) == before                 # a restarted Core opens nothing


def test_C11_the_same_resume_request_twice_changes_nothing(client, rig, tmp_path):
    s = _session(client, rig, tmp_path)
    client.resume_session(s['id'], request_id='c11')
    again = client.resume_session(s['id'], request_id='c11')
    assert again['duplicate']
    assert len([e for e in events_of(client, 'session.resumed')
                if e['subject']['id'] == s['id']]) == 1
    assert len(rig.launches()) == 1
