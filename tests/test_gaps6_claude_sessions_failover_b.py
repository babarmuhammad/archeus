"""T-1283: claude_sessions/failover.py:373-452 (fallback budget, retry commitment and
safe diagnostics); candidate gaps, not coverage.

Ranked final probes (denial/fail-closed first, then boundaries, then error paths):
1  :392 test_budget_exceeded_before_second_attempt_stops
   :392 test_budget_exactly_at_limit_still_opens_next           (equality control)
2  :381 test_malformed_or_non_object_body_passes_through_unchanged
3  :385 test_zero_or_one_candidate_passes_through_without_attempt_count
4  :396 test_each_retry_changes_only_the_model_field
5  :407 test_nonfinal_error_drained_at_most_4096_and_closed_despite_faults
6  :429 test_first_committed_response_relayed_once_then_no_retry
7  :428 test_last_http_error_relayed_as_error_never_converted
8  :403 test_exception_text_not_in_attempts_json                 (strict xfail)
   :403 test_timeout_labelled_and_error_text_bounded             (passing sibling)
9  :438 test_all_open_failures_return_one_failover_exhausted_502
10 :447 test_brief_bounded_without_traceback

Seams: object.__new__(_Handler) with _profile, _open, _relay, _passthrough, _json,
_note and _learn replaced by recorders; scripted fake responses and connections; a
synthetic clock replaces only failover.time. No sockets, subprocesses or home reads.
"""

import email.message
import io
import json
from types import SimpleNamespace

import pytest

from claude_sessions import config as _c
from claude_sessions import failover


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))


class _Resp:
    def __init__(self, status, chunks=(), read_error=None):
        self.status = status
        self._chunks = list(chunks)
        self._read_error = read_error
        self.read_calls = []

    def read(self, n=-1):
        self.read_calls.append(n)
        if self._read_error is not None:
            raise self._read_error
        return self._chunks.pop(0) if self._chunks else b''


class _Conn:
    def __init__(self, model, close_error=None):
        self.model = model
        self.closed = 0
        self._close_error = close_error

    def close(self):
        self.closed += 1
        if self._close_error is not None:
            raise self._close_error


def _handler(profile):
    h = object.__new__(failover._Handler)
    h.command = 'POST'
    h.path = '/v1/messages'
    h.headers = email.message.Message()
    h.rfile = io.BytesIO(b'')
    h.wfile = io.BytesIO()
    h.close_connection = False
    h.opened = []
    h.notes = []
    h.learned = []
    h.relayed = []
    h.jsons = []
    h.passed = []
    h._profile = lambda: profile
    h._note = lambda *a: h.notes.append(a)
    h._learn = lambda model, ok, detail: h.learned.append((model, ok, detail))
    h._relay = lambda resp, conn, extra: h.relayed.append((resp, conn, extra))
    h._json = lambda code, payload: h.jsons.append((code, payload))
    h._passthrough = lambda body: h.passed.append(body)
    return h


def _script(h, steps, close_errors=None):
    """steps: model -> exception to raise, a _Resp, or a callable returning either."""
    close_errors = close_errors or {}

    def _open(prof, body, timeout=None):
        model = json.loads(body)['model']
        h.opened.append((model, body))
        step = steps[model]
        if callable(step):
            step = step()
        if isinstance(step, BaseException):
            raise step
        return _Conn(model, close_errors.get(model)), step

    h._open = _open
    return h


def _body(model):
    return json.dumps({'model': model, 'max_tokens': 7, 'stream': True,
                       'messages': [{'role': 'user', 'content': 'hi'}],
                       'metadata': {'user_id': 'u1'}}).encode('utf-8')


def _prof(*models):
    return {'id': 'p', 'failover_models': list(models)}


def _clock(monkeypatch):
    clock = {'t': 0.0}
    monkeypatch.setattr(failover, 'time', SimpleNamespace(monotonic=lambda: clock['t']))
    return clock


def test_budget_exceeded_before_second_attempt_stops(monkeypatch):
    clock = _clock(monkeypatch)

    def first_fails_late():
        clock['t'] = failover._TOTAL_BUDGET + 0.5
        return OSError('refused')

    h = _script(_handler(_prof('b', 'c')), {
        'a': first_fails_late, 'b': _Resp(200), 'c': _Resp(200),
    })

    h._failover(_body('a'))

    assert [m for m, _ in h.opened] == ['a']
    assert h.relayed == []
    code, payload = h.jsons[0]
    assert code == 502
    assert payload['error']['attempts'] == [
        {'model': 'a', 'error': 'refused'},
        {'model': 'b', 'error': 'skipped: budget exhausted'},
    ]


def test_budget_exactly_at_limit_still_opens_next(monkeypatch):
    clock = _clock(monkeypatch)

    def first_fails_at_limit():
        clock['t'] = float(failover._TOTAL_BUDGET)
        return OSError('refused')

    h = _script(_handler(_prof('b')), {'a': first_fails_at_limit, 'b': _Resp(200)})

    h._failover(_body('a'))

    assert [m for m, _ in h.opened] == ['a', 'b']
    assert h.jsons == []
    assert h.relayed[0][2]['X-Archeus-Model'] == 'b'


@pytest.mark.parametrize('body', [
    b'not json',
    b'[1, 2]',
    b'"just a string"',
    b'{"messages": []}',
])
def test_malformed_or_non_object_body_passes_through_unchanged(body):
    h = _script(_handler(_prof('b')), {})

    h._failover(body)

    assert h.passed == [body]
    assert h.opened == []
    assert h.relayed == [] and h.jsons == []


@pytest.mark.parametrize('model, failover_models', [
    ('', ['x']),
    ('m', []),
    ('m', ['m']),
    ('', []),
])
def test_zero_or_one_candidate_passes_through_without_attempt_count(model, failover_models):
    body = _body(model)
    h = _script(_handler(_prof(*failover_models)), {})

    h._failover(body)

    assert h.passed == [body]
    assert h.opened == []
    assert h.relayed == [] and h.jsons == [] and h.notes == []


def test_each_retry_changes_only_the_model_field():
    body = _body('a')
    original = json.loads(body)
    h = _script(_handler(_prof('b', 'c')), {
        'a': _Resp(500, chunks=[b'{"error":{"message":"bad"}}']),
        'b': _Resp(500, chunks=[b'{"error":{"message":"bad"}}']),
        'c': _Resp(200),
    })

    h._failover(body)

    assert [m for m, _ in h.opened] == ['a', 'b', 'c']
    for model, sent in h.opened:
        parsed = json.loads(sent)
        assert parsed.pop('model') == model
        expected = dict(original)
        expected.pop('model')
        assert parsed == expected
    assert body == _body('a')


def test_nonfinal_error_drained_at_most_4096_and_closed_despite_faults():
    failing = _Resp(500, read_error=OSError('reset mid-body'))
    h = _script(_handler(_prof('b')), {'a': failing, 'b': _Resp(200)},
                close_errors={'a': RuntimeError('close fault')})

    h._failover(_body('a'))

    assert [m for m, _ in h.opened] == ['a', 'b']
    assert failing.read_calls == [4096]
    assert h.relayed[0][2] == {'X-Archeus-Model': 'b', 'X-Archeus-Attempts': '2'}


def test_first_committed_response_relayed_once_then_no_retry():
    h = _script(_handler(_prof('b')), {'a': _Resp(200), 'b': _Resp(200)})

    h._failover(_body('a'))

    assert [m for m, _ in h.opened] == ['a']
    assert len(h.relayed) == 1
    assert h.relayed[0][2] == {'X-Archeus-Model': 'a', 'X-Archeus-Attempts': '1'}
    assert h.jsons == []


def test_relay_fault_after_commit_is_not_retried():
    h = _script(_handler(_prof('b')), {'a': _Resp(200), 'b': _Resp(200)})

    def relay_dies(resp, conn, extra):
        raise ConnectionResetError('client left')

    h._relay = relay_dies

    with pytest.raises(ConnectionResetError):
        h._failover(_body('a'))

    assert [m for m, _ in h.opened] == ['a']


def test_last_http_error_relayed_as_error_never_converted():
    h = _script(_handler(_prof('b')), {
        'a': _Resp(500, chunks=[b'{"error":{"message":"bad"}}']),
        'b': _Resp(503),
    })

    h._failover(_body('a'))

    assert [m for m, _ in h.opened] == ['a', 'b']
    assert len(h.relayed) == 1
    resp, _conn, extra = h.relayed[0]
    assert resp.status == 503
    assert extra == {'X-Archeus-Model': 'b', 'X-Archeus-Attempts': '2'}
    assert ('b', False, 'HTTP 503') in h.learned
    assert h.jsons == []


def test_timeout_labelled_and_error_text_bounded():
    h = _script(_handler(_prof('b')), {
        'a': TimeoutError('the read timed out'),
        'b': OSError('x' * 200),
    })

    h._failover(_body('a'))

    code, payload = h.jsons[0]
    attempts = payload['error']['attempts']
    assert attempts[0] == {'model': 'a', 'error': 'TIMEOUT'}
    assert attempts[1]['error'] == 'x' * 60


def test_exception_text_not_in_attempts_json():
    """Premise: attempts[] is client-visible, so raw exception text (which may carry
    an upstream address, a path or a credential fragment) must not appear in it."""
    h = _script(_handler(_prof('b')), {
        'a': OSError('sk-ant-api03-SYNTHETICKEY123456 at /synthetic/path refused'),
        'b': OSError('sk-ant-api03-SYNTHETICKEY654321 refused'),
    })

    h._failover(_body('a'))

    code, payload = h.jsons[0]
    body = json.dumps(payload)
    assert 'SYNTHETICKEY123456' not in body and 'SYNTHETICKEY654321' not in body
    assert '/synthetic/path' in body


def test_all_open_failures_return_one_failover_exhausted_502():
    h = _script(_handler(_prof('b', 'c')), {
        'a': OSError('refused a'),
        'b': OSError('refused b'),
        'c': OSError('refused c'),
    })

    h._failover(_body('a'))

    assert len(h.jsons) == 1
    code, payload = h.jsons[0]
    assert code == 502
    assert payload['error']['type'] == 'failover_exhausted'
    assert [a['model'] for a in payload['error']['attempts']] == ['a', 'b', 'c']
    assert h.relayed == [] and h.passed == []


@pytest.mark.parametrize('raw, expected', [
    (b'{"error": "plain string"}', '{"error": "plain string"}'),
    (b'[1, 2]', '[1, 2]'),
    (b'7', '7'),
    (b'{"error": {"message": "' + b'm' * 200 + b'"}}', 'm' * 70),
    (b'{"message": "top level"}', 'top level'),
    (b'{"error": 5}', '{"error": 5}'),
    (b'\xff\xfe\x00 garbage', '��\x00 garbage'),
])
def test_brief_bounded_without_traceback(raw, expected):
    got = failover._brief(raw)

    assert isinstance(got, str)
    assert len(got) <= 70
    assert 'Traceback' not in got
    assert got == expected
