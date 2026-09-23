"""SK — the walking skeleton (plan §31.1 P3.5).

create mission (a command: no intent parsing, no brain) -> stub brain plan ->
stub policy auto-approves -> task -> fake execution subprocess (JSONL stream)
-> stub verification and review -> COMPLETED, every transition observed on the
event stream. It is NOT S1: S1 needs the real brain, policy, router,
verification and review.
"""

import pytest

from .support import events_of, mission_states, wait_state


@pytest.mark.xfail(strict=True, reason="phase:P3.5")
def test_a_mission_runs_to_completed_on_stubs_and_the_fake_harness(client):
    m = client.create_mission(title='Skeleton', objective='Prove the vertical slice')
    assert m['state'] == 'CREATED'
    done = wait_state(client, m['id'], 'COMPLETED')
    assert done['id'] == m['id']
    started = events_of(client, 'execution.started')
    ended = events_of(client, 'execution.ended')
    assert started and ended, 'the task never ran as a fake execution subprocess'
    assert all(e['payload'].get('pid') for e in started)


@pytest.mark.xfail(strict=True, reason="phase:P3.5")
def test_every_transition_is_observed_on_the_event_stream(client):
    m = client.create_mission(title='Skeleton', objective='Observe it')
    wait_state(client, m['id'], 'COMPLETED')
    seen = mission_states(client, m['id'])
    assert seen[-1] == 'COMPLETED'
    assert 'EXECUTING' in seen and 'VERIFYING' in seen and 'REVIEWING' in seen
    seqs = [e['seq'] for e in client.events(0)]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert all(e['actor']['kind'] for e in client.events(0))
