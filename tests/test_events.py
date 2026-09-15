"""The event log — the only record of what archeus did when it failed.

Every assertion here is written against a mutation that would silently return
the old behaviour: a logger that writes to nothing, a file that grows forever,
a reader that materialises a 100 MB file, or a writer that raises on the error
path it was added to describe.
"""

import ast
import glob
import inspect
import json
import os

import pytest

from claude_sessions import config as _c
from claude_sessions import events


@pytest.fixture(autouse=True)
def _log_in_tmp(monkeypatch, tmp_path):
    p = tmp_path / 'archeus-events.jsonl'
    monkeypatch.setattr(events, 'path', lambda: str(p))
    events._recent.clear()
    return p


def test_a_failure_lands_in_the_log(_log_in_tmp):
    """The whole feature. ~38 `log.exception` sites reach the log through ONE
    handler; without it every one of them writes to a NullHandler and the user
    is told nothing at all."""
    try:
        raise ValueError('boom')
    except ValueError:
        _c.log.exception('gui job failed: %s', 'memory build')

    rows = events.read()
    assert len(rows) == 1
    assert rows[0]['lvl'] == 'error'
    assert 'memory build' in rows[0]['msg']
    assert 'ValueError' in rows[0]['detail'], 'the traceback did not survive'


def test_a_warning_is_recorded_as_a_warning_and_info_is_not_recorded(_log_in_tmp):
    _c.log.warning('failover: upstream said 429')
    _c.log.info('this is chatter')
    rows = events.read()
    assert [r['lvl'] for r in rows] == ['warn']


def test_the_event_log_stops_growing(_log_in_tmp):
    """Unbounded growth is what made every other log in this project need a
    cap; this one is written from a proxy that warns per failed request."""
    p = _log_in_tmp
    line = json.dumps({'ts': 1, 'lvl': 'error', 'src': 's',
                       'msg': 'x' * 180, 'detail': '', 'proj': ''})
    with open(p, 'w', encoding='utf-8') as f:
        for i in range(4000):
            f.write(line.replace('"ts": 1', '"ts": %d' % i) + '\n')
    assert p.stat().st_size > events.MAX_BYTES
    events._rotate(str(p))
    assert p.stat().st_size <= events.MAX_BYTES
    lines = p.read_text(encoding='utf-8').splitlines()
    assert json.loads(lines[-1])['ts'] == 3999, 'rotation kept the wrong end'
    json.loads(lines[0])                       # a half-line did not survive


def test_the_reader_streams(_log_in_tmp):
    """One reader per format, and it streams. A `readlines()` here is the same
    bug transcripts.py exists to have fixed."""
    src = inspect.getsource(events.read)
    assert 'transcripts.iter_json' in src
    assert 'readlines' not in src and '.read()' not in src

    with open(_log_in_tmp, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'ts': 1, 'lvl': 'info', 'src': 'a', 'msg': 'first'}) + '\n')
        f.write('{ this line is truncated\n')
        f.write(json.dumps({'ts': 2, 'lvl': 'info', 'src': 'a', 'msg': 'second'}) + '\n')
    assert [r['msg'] for r in events.read()] == ['second', 'first']


def test_recording_never_raises(monkeypatch, tmp_path):
    """It sits on the error path. A writer that can fail is a second bug on
    top of the one being reported."""
    monkeypatch.setattr(events, 'path',
                        lambda: str(tmp_path / 'nope' / '\0bad' / 'x.jsonl'))
    assert events.record('t', 'still fine') is False


def test_the_writer_never_logs():
    """`config.log` routes INTO record(); a record() that logs would recurse
    through the handler that called it."""
    src = inspect.getsource(events.record)
    assert 'log.' not in src and '_c.log' not in src


def test_the_dedupe_window_collapses_a_retry_storm(_log_in_tmp):
    """failover warns once per failed upstream request — an outage would
    otherwise churn the whole cap and push every other event out."""
    for _ in range(500):
        events.record('failover', 'upstream 429')
    assert len(events.read()) == 1
    events.record('failover', 'a different thing')
    assert len(events.read()) == 2


def test_a_long_detail_is_truncated_at_the_writer(_log_in_tmp):
    events.record('t', 'm', detail='x' * 5000, proj='p' * 200)
    row = events.read()[0]
    assert len(row['detail']) <= 1000 and len(row['proj']) <= 80


def test_an_absent_file_is_an_empty_state_not_an_error(_log_in_tmp):
    assert events.read() == []


def test_no_hook_writes_an_event():
    """Everything on a per-turn path pays its cost forever. Every writer is a
    archeus-owned process; a hook runs once per prompt."""
    pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'claude_sessions')
    offenders = []
    for path in glob.glob(os.path.join(pkg, '*_hook.py')):
        tree = ast.parse(open(path, encoding='utf-8').read(), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ''] + [a.name for a in node.names]
            if any(n and n.split('.')[-1] == 'events' for n in names):
                offenders.append(os.path.basename(path))
    assert not offenders, 'a hook writes to the event log: %s' % offenders


def test_a_measurement_in_the_message_does_not_defeat_the_dedupe(_log_in_tmp):
    """A dedupe key that contains a number is not a key.

    `gui.py` formats the elapsed time into its slow-handler warning, so
    `slow: 1.55s` and `slow: 1.56s` were distinct messages and the 60-second
    window never fired. Live consequence: 609 of the 674 events in this
    machine's log were slow-warnings differing only in a decimal, and they had
    evicted every real failure past MAX_BYTES.
    """
    for dt in (1.55, 1.56, 1.61, 2.44):
        _c.log.warning('gui api %s %s slow: %.2fs', 'GET', '/api/memory/active', dt)
    rows = events.read()
    assert len(rows) == 1, [r['msg'] for r in rows]
    # …and the one that IS written keeps its real number, unshaped
    assert 'slow: 1.55s' in rows[0]['msg']
    # a genuinely different message is still its own event
    _c.log.warning('gui api %s %s slow: %.2fs', 'GET', '/api/dashboard', 6.18)
    assert len(events.read()) == 2


def test_two_messages_that_differ_only_in_wording_still_dedupe_separately(_log_in_tmp):
    """The collapse must not go so far that unrelated failures share a key."""
    _c.log.warning('claude exited 1: session limit')
    _c.log.warning('claude exited 1: overloaded')
    assert len(events.read()) == 2


def test_an_integer_is_part_of_the_identity_and_must_not_collapse(_log_in_tmp):
    """Collapsing every digit run was over-broad, and the log's own producers
    say why: `failover` writes 'HTTP %s', so a 429 and a 500 from the same
    candidate became one event; `gui_api` writes '... failed for %s', so two
    project paths differing by a digit collapsed and the second project's
    failure was dropped. The measured defect was `slow: %.2fs` — a decimal.
    """
    _c.log.warning('failover: big-pickle -> HTTP 429, next candidate')
    _c.log.warning('failover: big-pickle -> HTTP 500, next candidate')
    _c.log.warning('memory refresh failed for D:/work/app1')
    _c.log.warning('memory refresh failed for D:/work/app2')
    assert len(events.read()) == 4


def test_one_noisy_message_cannot_evict_every_real_error(monkeypatch, tmp_path):
    """Dropping the oldest half is fair by age and useless by content.

    Measured on this machine: the log held 1,589 events of which 1,270 were a
    single slow-endpoint warning, so the kept half was also four-fifths that
    warning — and the 79 real `subprocess` errors it had already pushed out did
    not come back. The dedupe window stops a burst; nothing stopped a steady
    drip over two weeks.
    """
    p = tmp_path / 'ev.jsonl'
    monkeypatch.setattr(events, 'path', lambda: str(p))
    rows = []
    for i in range(400):
        rows.append(json.dumps({'ts': i, 'lvl': 'warn', 'src': 'gui',
                                'msg': 'gui api GET /api/dashboard slow: %d.5s' % i}))
    for i in range(5):
        rows.append(json.dumps({'ts': 500 + i, 'lvl': 'error', 'src': 'subprocess',
                                'msg': 'claude exited 1: session limit %d' % i}))
    kept = events._thin(rows)
    srcs = [json.loads(r)['src'] for r in kept]
    assert srcs.count('subprocess') == 5, 'every real error survives'
    assert srcs.count('gui') == events._SHAPE_KEEP, 'the drip is capped'
    # and what survives keeps its order — this reduces a log, it does not
    # reorder one
    ts = [json.loads(r)['ts'] for r in kept]
    assert ts == sorted(ts)


def test_thinning_is_per_shape_not_per_source(monkeypatch, tmp_path):
    """Two endpoints being slow is two facts. Capping by SOURCE would let a
    noisy one hide a quiet one under the same name."""
    rows = ([json.dumps({'ts': i, 'lvl': 'warn', 'src': 'gui',
                         'msg': 'gui api GET /api/dashboard slow: %d.1s' % i})
             for i in range(200)]
            + [json.dumps({'ts': 900, 'lvl': 'warn', 'src': 'gui',
                           'msg': 'gui api GET /api/sessions slow: 9.9s'})])
    kept = [json.loads(r)['msg'] for r in events._thin(rows)]
    assert any('/api/sessions' in m for m in kept)
    assert sum('/api/dashboard' in m for m in kept) == events._SHAPE_KEEP


def test_rotation_thins_and_stays_readable(monkeypatch, tmp_path):
    p = tmp_path / 'ev.jsonl'
    monkeypatch.setattr(events, 'path', lambda: str(p))
    monkeypatch.setattr(events, '_DEDUPE_SEC', 0)
    events._recent.clear()
    for i in range(4000):
        events.record('gui', 'gui api GET /api/dashboard slow: %d.5s' % i,
                      level='warn')
    events.record('subprocess', 'claude exited 1: the one that matters',
                  level='error')
    got = events.read(limit=5000)
    assert any('the one that matters' in r['msg'] for r in got)
    assert os.path.getsize(p) <= events.MAX_BYTES
