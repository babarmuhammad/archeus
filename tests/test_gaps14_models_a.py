"""Gap tests for models.fetch and the row helpers: the fresh-cache and
auto-update gates, the no-token and request-failure contracts, the empty
catalogue refusal, row shaping (effort order, label), the id and family rules,
and the newest-first save. urlopen, the token, the settings and the cache path
are all faked; no request leaves the process."""

import io
import json
import os
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import models as m


@pytest.fixture
def env(monkeypatch, tmp_path):
    cache = str(tmp_path / 'archeus-models.json')
    settings = {}
    calls = []
    body = {'value': b'{"data": []}'}
    failure = {'value': None}

    monkeypatch.setattr(m, '_cache_path', lambda: cache)
    monkeypatch.setattr(m, '_token', lambda: 'tok-fake')
    monkeypatch.setattr(m._c, 'load_settings', lambda: dict(settings))

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=0):
        calls.append(req.full_url)
        if failure['value'] is not None:
            raise failure['value']
        return _Resp(body['value'])

    monkeypatch.setattr(m.urllib.request, 'urlopen', fake)

    class E:
        pass

    e = E()
    e.cache, e.settings, e.calls, e.body, e.failure = cache, settings, calls, body, failure
    return e


def _doc(*rows):
    return json.dumps({'data': list(rows)}).encode()


def _row_json(mid, created, **extra):
    d = {'id': mid, 'display_name': mid, 'created_at': created,
         'max_input_tokens': 200000, 'max_tokens': 64000,
         'capabilities': {'effort': {'low': {'supported': True}}}}
    d.update(extra)
    return d


def _seed(env, models, fetched):
    with open(env.cache, 'w', encoding='utf-8') as f:
        json.dump({'models': models, 'fetched': fetched}, f)


_KEPT = [{'id': 'claude-kept-1', 'label': 'kept-1', 'created': '2025-01-01'}]


def test_fresh_cache_is_served_without_a_request_and_refresh_forces_one(env):
    _seed(env, _KEPT, time.time())
    out = m.fetch()
    assert out == {'models': _KEPT, 'fetched': out['fetched'], 'error': ''}
    assert env.calls == []
    env.body['value'] = _doc(_row_json('claude-new-2', '2026-01-01T00:00:00Z'))
    out = m.fetch(refresh=True)
    assert env.calls and out['error'] == ''
    assert [r['id'] for r in out['models']] == ['claude-new-2']


def test_auto_update_off_makes_no_request_but_empty_means_notify(env):
    _seed(env, _KEPT, 0)
    env.settings['auto_update'] = 'off'
    out = m.fetch(refresh=True)
    assert out['models'] == _KEPT and out['error'] == ''
    assert env.calls == []
    env.settings['auto_update'] = ''
    env.body['value'] = _doc(_row_json('claude-new-2', '2026-01-01T00:00:00Z'))
    m.fetch(refresh=True)
    assert len(env.calls) == 1


def test_no_token_keeps_the_cache_and_says_why(env, monkeypatch):
    _seed(env, _KEPT, 0)
    monkeypatch.setattr(m, '_token', lambda: '')
    out = m.fetch(refresh=True)
    assert out['models'] == _KEPT
    assert out['error'] == 'not logged in — run `claude login`'
    assert env.calls == []


def test_request_failure_keeps_cache_and_truncates_the_error(env):
    _seed(env, _KEPT, 0)
    env.failure['value'] = urllib.error.URLError('x' * 300)
    out = m.fetch(refresh=True)
    assert out['models'] == _KEPT
    assert out['error'] == str(env.failure['value'])[:200]
    assert len(out['error']) == 200


def test_undecodable_body_keeps_cache_and_reports_it(env):
    _seed(env, _KEPT, 0)
    env.body['value'] = b'<html>not json</html>'
    out = m.fetch(refresh=True)
    assert out['models'] == _KEPT
    assert out['error'] != ''


def test_an_empty_catalogue_is_refused_and_the_cache_file_is_untouched(env):
    _seed(env, _KEPT, 0)
    before = open(env.cache, encoding='utf-8').read()
    env.body['value'] = _doc({'display_name': 'no id here'})
    out = m.fetch(refresh=True)
    assert out['models'] == _KEPT
    assert out['error'] == 'the catalogue came back empty'
    assert open(env.cache, encoding='utf-8').read() == before


def test_success_is_sorted_newest_first_and_saved(env):
    env.body['value'] = _doc(
        _row_json('claude-old-1', '2025-01-01T00:00:00Z'),
        _row_json('claude-new-3', '2026-03-01T00:00:00Z'),
        _row_json('claude-mid-2', '2025-09-01T00:00:00Z'))
    out = m.fetch(refresh=True)
    assert [r['id'] for r in out['models']] == ['claude-new-3', 'claude-mid-2', 'claude-old-1']
    with open(env.cache, encoding='utf-8') as f:
        saved = json.load(f)
    assert isinstance(saved['fetched'], float)
    assert [r['id'] for r in saved['models']] == [r['id'] for r in out['models']]
    assert m.catalogue()['models'] == out['models']


def test_catalogue_is_empty_without_a_cache_and_the_models_with_one(env):
    assert m.catalogue() == {}
    _seed(env, _KEPT, 0)
    assert m.catalogue() == {'models': _KEPT, 'fetched': 0}


def test_row_keeps_supported_efforts_in_order_and_drops_the_claude_prefix():
    row = m._row({
        'id': 'claude-opus-4-6-20260101', 'display_name': 'Opus', 'created_at': 'c',
        'max_input_tokens': 1000, 'max_tokens': 500,
        'capabilities': {'effort': {
            'max': {'supported': True}, 'low': {'supported': True},
            'medium': {'supported': False}, 'xhigh': {'supported': True}}}})
    assert row['id'] == 'claude-opus-4-6'
    assert row['label'] == 'opus-4-6'
    assert row['snapshot'] == 'claude-opus-4-6-20260101'
    assert row['efforts'] == ['low', 'xhigh', 'max']
    assert row['context'] == 1000 and row['max_out'] == 500
    assert m._row({'id': 'gpt-x'})['label'] == 'gpt-x'


def test_alias_and_family_edges():
    assert m.alias('claude-haiku-4-5-20251001') == 'claude-haiku-4-5'
    assert m.alias('claude-sonnet-5') == 'claude-sonnet-5'
    assert m.alias(None) == ''
    assert m.family('claude-opus-4-5') == 'opus'
    assert m.family('claude-foo') == 'foo'
    assert m.family('') == ''
