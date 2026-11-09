"""H1 and R1 (testing-strategy §6, now §2) — over two fake session harnesses,
so "a new harness needs no new entity" is what they prove (ADR-0023).

R1: a session resumes on its own harness's configuration — the resume argv
carries the model and effort it recorded, in that harness's vocabulary, and
never another harness's. H1: a hand-off to the other harness is a new Session
with `handoff_from_session_id`, the artifact reaches the target through its
adapter, the source is unchanged, `session.handed_off` is recorded."""

import os

import pytest

from .support import SESSION_HARNESSES

VOCAB = {h: (models, efforts) for h, models, efforts in SESSION_HARNESSES}
PAIRS = [('fake_a', 'fake_b'), ('fake_b', 'fake_a')]


@pytest.mark.parametrize('harness', sorted(VOCAB))
def test_R1_a_session_resumes_on_its_own_configuration(client, rig, tmp_path, harness):
    models, efforts = VOCAB[harness]
    ref = rig.provider_session(harness, [('user', 'hi')])
    s = client.register_session(harness_id=harness, cwd=str(tmp_path), provider_session_ref=ref,
                                model=models[-1], effort=efforts[-1])
    client.resume_session(s['id'], request_id='r1')
    argv = rig.launches()[-1]['argv']
    assert argv[argv.index('--ref') + 1] == ref
    assert argv[argv.index('--model') + 1] == models[-1]
    assert argv[argv.index('--effort') + 1] == efforts[-1]
    other = [v for h, (m, e) in VOCAB.items() if h != harness for v in m + e]
    assert not set(argv) & set(other)


@pytest.mark.parametrize('src,dst', PAIRS)
def test_H1_a_session_hands_off_to_the_other_harness(client, rig, tmp_path, src, dst):
    ref = rig.provider_session(src, [('user', 'design the schema'),
                                     ('assistant', 'three tables: a, b, c')])
    s = client.register_session(harness_id=src, cwd=str(tmp_path), provider_session_ref=ref,
                                model=VOCAB[src][0][0])
    before = {k: v for k, v in client.get_session(s['id']).items() if k != 'targets'}
    t = client.handoff_session(s['id'], request_id='h1', harness_id=dst)
    assert (t['harness_id'], t['handoff_from_session_id'], t['model']) == (dst, s['id'], None)
    path = os.path.join(str(tmp_path), '.archeus', 'sessions', '%s.md' % t['id'])
    assert 'three tables: a, b, c' in open(path, encoding='utf-8').read()
    assert path in rig.launches()[-1]['argv'][-1]            # the opening message points at it
    assert {k: v for k, v in client.get_session(s['id']).items() if k != 'targets'} == before
    assert [e['payload']['to'] for e in client.events()
            if e['type'] == 'session.handed_off'] == [t['id']]
