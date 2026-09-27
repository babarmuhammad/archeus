"""C3, C9, C10, C12, C14 — a session handed to another harness is a new, linked
session given only what Core renders (p12-design-gate §10.2–§10.5, §12, §17,
§18, D10, D11)."""

import json
import os

import pytest

from v1.judge.client import CoreClientError

SECRET = 'ghp_' + 'q' * 36


def _source(client, rig, tmp_path, turns=None):
    ref = rig.provider_session('fake_a', turns or [
        ('user', 'migrate the billing tables'), ('assistant', 'the orders table is done'),
        ('user', 'and the invoices?')])
    return client.register_session(harness_id='fake_a', cwd=str(tmp_path),
                                   provider_session_ref=ref, model='fake-model')


def _delivered(tmp_path, session_id):
    with open(os.path.join(str(tmp_path), '.archeus', 'sessions', '%s.md' % session_id),
              encoding='utf-8') as f:
        return f.read()


def test_C3_a_cross_harness_handoff_carries_what_matters_and_nothing_private(client, rig,
                                                                             tmp_path):
    src = _source(client, rig, tmp_path)
    t = client.handoff_session(src['id'], request_id='c3', harness_id='fake_b',
                               reason='continue on the other harness')
    assert (t['harness_id'], t['handoff_from_session_id']) == ('fake_b', src['id'])
    text = _delivered(tmp_path, t['id'])
    assert 'the orders table is done' in text and 'and the invoices?' in text
    (launch,) = rig.launches()
    assert src['provider_session_ref'] not in json.dumps(launch)     # no provider state
    assert any('.archeus' in a and t['id'] in a for a in launch['argv'])


def test_C9_lineage_is_explicit_and_the_source_is_never_written(client, rig, tmp_path):
    src = _source(client, rig, tmp_path)
    before = {k: v for k, v in client.get_session(src['id']).items() if k != 'targets'}
    b = client.handoff_session(src['id'], request_id='c9a', harness_id='fake_b')
    rig.provider_session('fake_b', [('user', 'carry on')], ref=client.get_session(
        b['id'])['provider_session_ref'])
    c = client.handoff_session(b['id'], request_id='c9b', harness_id='fake_a')
    assert client.get_session(c['id'])['lineage'] == [b['id'], src['id']]
    after = client.get_session(src['id'])
    assert {k: v for k, v in after.items() if k != 'targets'} == before
    assert after['targets'] == [b['id']]
    assert [(e['payload']['from'], e['payload']['to'])
            for e in client.events() if e['type'] == 'session.handed_off'] == [
        (src['id'], b['id']), (b['id'], c['id'])]


def test_C10_no_secret_reaches_a_session_an_event_or_an_artifact(client, rig, tmp_path):
    src = _source(client, rig, tmp_path, turns=[('user', 'use token %s please' % SECRET),
                                                ('assistant', 'noted')])
    t = client.handoff_session(src['id'], request_id='c10', harness_id='fake_b')
    client.resume_session(src['id'], request_id='c10r')
    blobs = [_delivered(tmp_path, t['id']), json.dumps(client.events()),
             json.dumps(client.list_sessions()), json.dumps(rig.launches())]
    assert not [b for b in blobs if SECRET in b]
    assert '[redacted]' in blobs[0]


def test_C12_the_same_handoff_request_makes_one_target(client, rig, tmp_path):
    src = _source(client, rig, tmp_path)
    a = client.handoff_session(src['id'], request_id='c12', harness_id='fake_b')
    b = client.handoff_session(src['id'], request_id='c12', harness_id='fake_b')
    assert a['id'] == b['id'] and b['duplicate']
    assert len(client.list_sessions()) == 2 and len(rig.launches()) == 1


def test_C14_missing_context_is_reported_never_invented(client, rig, tmp_path):
    src = _source(client, rig, tmp_path)
    # a session scoped to no mission and no project has no package, and says so
    brief = client.resume_session(src['id'], request_id='c14')['brief']
    assert brief['context']['package_id'] is None and brief['mission'] is None
    # with its transcript gone there is nothing to hand over: refused, nothing made
    rig.drop_provider_session('fake_a', src['provider_session_ref'])
    with pytest.raises(CoreClientError) as e:
        client.handoff_session(src['id'], request_id='c14b', harness_id='fake_b')
    assert e.value.status in (409, 422)
    assert len(client.list_sessions()) == 1
