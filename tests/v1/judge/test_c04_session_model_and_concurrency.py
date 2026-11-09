"""C4, C5, C6, C7 — a model switch keeps the session and its mission; two
sessions on one mission each see what the other changed; a stale context
package is rebuilt, a fresh one reused; a session holds no authorisation
(p12-design-gate §9, §11.2, §13.2, §15, §16)."""

import pytest

from v1.judge.client import CoreClientError

from .support import events_of, wait_for, wait_state


def _session(client, rig, tmp_path, mission_id=None, harness='fake_a', model='fake-model'):
    ref = rig.provider_session(harness, [('user', 'hello')])
    return client.register_session(harness_id=harness, cwd=str(tmp_path), mission_id=mission_id,
                                   provider_session_ref=ref, model=model)


def test_C4_a_model_switch_keeps_the_session_and_the_mission(client, rig, tmp_path):
    m = client.create_mission(title='Model', objective='One task')
    s = _session(client, rig, tmp_path, mission_id=m['id'])
    out = client.resume_session(s['id'], request_id='c4', model='fake-large')
    assert (out['id'], out['model'], out['mission_id']) == (s['id'], 'fake-large', m['id'])
    assert '--model' in rig.launches()[-1]['argv'] and 'fake-large' in rig.launches()[-1]['argv']
    with pytest.raises(CoreClientError) as e:            # another harness's vocabulary
        client.resume_session(s['id'], request_id='c4b', model='b-large')
    assert e.value.status == 400


def test_C5_two_sessions_on_one_mission_see_each_others_changes(client, rig, tmp_path):
    m = client.create_mission(title='Shared', objective='One task')
    wait_state(client, m['id'], 'COMPLETED')
    a = _session(client, rig, tmp_path, mission_id=m['id'])
    b = _session(client, rig, tmp_path, mission_id=m['id'], harness='fake_b', model='b-small')
    client.resume_session(a['id'], request_id='c5a')        # A has seen everything so far
    # B's user continues the mission: a durable change, through the mission's own command
    client.submit_message('Note for the Shared mission: the chart needs a legend')
    brief = client.resume_session(a['id'], request_id='c5b')['brief']
    assert brief['as_of_seq'] > client.get_session(b['id'])['last_seen_seq']
    assert brief['mission']['state'] == client.get_mission(m['id'])['state']


def test_C6_a_stale_package_is_rebuilt_and_a_fresh_one_reused(client, rig, tmp_path):
    rig.script_harness('t1', [{'emit': {'type': 'working'}}, {'sleep': 30}])
    m = client.create_mission(title='Fresh', objective='One task')
    # a quiet world: the execution has settled into RUNNING, and nothing in the
    # mission's scope moves until the pause below
    wait_for(lambda: [e for e in events_of(client, 'execution.state_changed')
                      if e['payload']['to'] == 'RUNNING'])
    s = _session(client, rig, tmp_path, mission_id=m['id'])
    first = client.resume_session(s['id'], request_id='c6a')['brief']['context']
    again = client.resume_session(s['id'], request_id='c6b')['brief']['context']
    assert again['package_id'] == first['package_id'] and not again['rebuilt']
    client.pause(m['id'])                                    # the mission moved
    third = client.resume_session(s['id'], request_id='c6c')['brief']['context']
    assert third['rebuilt'] and third['package_id'] != first['package_id']
    client.stop('all')


def test_C7_a_session_grants_nothing_and_a_continuation_meets_current_policy(client, rig,
                                                                             tmp_path):
    s = _session(client, rig, tmp_path)
    before = len(events_of(client, 'policy_decision.created'))
    client.resume_session(s['id'], request_id='c7')
    assert len(events_of(client, 'policy_decision.created')) == before
    # an execution that hands off after the user's policy changed gets no
    # continuation until P9 is satisfied now: its authorisation was the old one
    rig.script_harness('t1', [{'emit': {'type': 'working'}}, {'sleep': 0.8},
                              {'emit': {'type': 'usage', 'usage': {'input_tokens': 190000}},
                               'fresh_only': True},
                              {'emit': {'type': 'tool', 'name': 'Read',
                                        'input': {'file_path': 'a'}}}])
    m = client.create_mission(title='Policy', objective='One task')
    wait_for(lambda: events_of(client, 'execution.started'))
    client.set_policy_rule(scope_level='USER', action_class='write_repo', decision='ASK')
    wait_for(lambda: [e for e in events_of(client, 'execution.ended')
                      if e['payload']['exit_reason'] == 'handoff'], timeout=30)
    wait_state(client, m['id'], 'BLOCKED', timeout=30)
    assert events_of(client, 'approval.requested')           # P9 asks, now
    assert not [e for e in events_of(client, 'execution.intent')
                if e['payload'].get('handoff_from')]
