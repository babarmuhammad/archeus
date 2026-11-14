"""T-1409 · test gaps in claude_sessions/lessons.py background scan, scan loop,
status and evict writers (199-246 and 306-318: start_background_scan,
scan_sessions, _set_status, _evict).

Branches, ranked (refusal and status first, then persist order and swallowed
errors, then empty-input boundaries):

 1. 315-318  PREMISE: _evict deletes any id with no type check. Strict xfail.
 2. 306-310  PREMISE: approve on a pinned lesson drops it to 'approved'. Strict xfail.
 3. 306-312  an unknown id saves the unchanged graph and returns None.
 4. 199-205  empty sids start no thread and return None.
 5. 206-207  a live scan lock refuses a second worker.
 6. 209-215  the worker sets the silent flag; a scan failure is logged and swallowed.
 7. 225-226  sids == [] is respected: no pending lookup, no save.
 8. 228-237  each sid is saved before the next; a later failure keeps completed sids.
 9. 241-245  a failing convention sync is swallowed; the counts are still returned.
10. 238-240  decay runs once after the loop, following the per-sid saves.
"""

import copy
import threading

import pytest

from claude_sessions import config, conventions, lessons, memory

NOW = '2026-11-14T00:00:00+00:00'


class _Log:
    def __init__(self):
        self.calls = []

    def exception(self, msg, *a, **k):
        self.calls.append(msg)


@pytest.fixture
def graph(monkeypatch):
    state = {'graph': {'entities': [], 'session_counter': 0, 'lessons_scanned': {}},
             'saves': [], 'charges': []}
    monkeypatch.setattr(memory, 'load_memory',
                        lambda p, f=None: copy.deepcopy(state['graph']))

    def _save(p, f, m):
        state['graph'] = copy.deepcopy(m)
        state['saves'].append(copy.deepcopy(m))
    monkeypatch.setattr(memory, 'save_memory', _save)
    monkeypatch.setattr(memory, 'charge', lambda mem: state['charges'].append(1))
    monkeypatch.setattr(memory, '_report_progress', lambda *a, **k: None)
    monkeypatch.setattr(memory, '_iso', lambda: NOW)
    monkeypatch.setattr(memory, 'scan_lock_status', lambda p: None)
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(conventions, 'sync_to_global', lambda cfgdir=None: None)
    return state


@pytest.fixture
def threads(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            started.append(self)
            self.target()

    monkeypatch.setattr(threading, 'Thread', FakeThread)
    return started


def _lesson(id_, status='approved', **over):
    e = {'id': id_, 'name': id_, 'type': 'lesson', 'summary': 'summary ' + id_,
         'kind': 'decision', 'confidence': 0.5, 'status': status, 'sid': 's0',
         'sids': ['s0'], 'last_used': 0}
    e.update(over)
    return e


def _lesson_item(title):
    return {'title': title, 'summary': 'fact about ' + title, 'kind': 'decision',
            'confidence': 0.5, 'files': []}


@pytest.mark.xfail(strict=True, reason=(
    "lessons.py:315-318 _evict filters on e.get('id') != lesson_id with no type "
    "check. Call chain: POST /api/lessons action 'evict' -> gui_api.api_lessons_post "
    "(gui_api.py:2637-2638, body['id'] taken as is) -> lessons._evict. A non-lesson "
    "id therefore deletes that entity."))
def test_evict_refuses_non_lesson_id(graph):
    """Expected: evicting an id whose entity is not type 'lesson' is refused and
    the fact survives. Current: the fact is removed and the graph saved."""
    graph['graph']['entities'] = [{'id': 'fact:1', 'type': 'fact', 'name': 'F'},
                                  _lesson('l1')]
    lessons._evict('/p', '/f', 'fact:1')
    assert 'fact:1' in {e['id'] for e in graph['graph']['entities']}


@pytest.mark.xfail(strict=True, reason=(
    "lessons.py:306-310 _set_status overwrites e['status'] unconditionally, so a "
    "pinned lesson is downgraded to 'approved' by the TUI 'a' key (lessons.py:291-292) "
    "or the GUI approve action (gui_api.py:2634-2636). apply_decay (lessons.py:191) "
    "then treats it as evictable after the TTL."))
def test_approve_does_not_unpin(graph):
    """Expected: approving a pinned lesson leaves it pinned. Current: it becomes
    'approved' and is exposed to decay."""
    graph['graph']['entities'] = [_lesson('l1', status='pinned')]
    lessons._set_status('/p', '/f', 'l1', 'approved')
    assert graph['graph']['entities'][0]['status'] == 'pinned'


def test_set_status_unknown_id_saves_unchanged_graph(graph):
    """An id that matches nothing leaves the graph as it was, still writes once,
    and returns None, so the caller cannot tell the id was stale. Catches: the
    save at lessons.py:311 running unconditionally."""
    graph['graph']['entities'] = [_lesson('l1')]
    before = copy.deepcopy(graph['graph'])
    assert lessons._set_status('/p', '/f', 'missing', 'approved') is None
    assert graph['saves'] == [before]


def test_background_scan_empty_sids_starts_nothing(graph, threads):
    """No sids: no thread and None, without even asking about the lock. Catches:
    the 'if not sids' guard at lessons.py:201-202."""
    assert lessons.start_background_scan('/p', '/f', []) is None
    assert threads == []


def test_background_scan_refused_while_locked(graph, threads, monkeypatch):
    """A live worker holds the lock (progress string, possibly empty): no second
    thread, and None is returned. Catches: the lock check at lessons.py:206-207."""
    monkeypatch.setattr(memory, 'scan_lock_status', lambda p: '')
    assert lessons.start_background_scan('/p', '/f', ['s1']) is None
    assert threads == []


def test_background_scan_logs_and_swallows_failure(graph, threads, monkeypatch):
    """The worker marks itself silent, and a scan_sessions failure is logged and
    does not escape the thread. Catches: lessons.py:210 and 212-215."""
    log = _Log()
    monkeypatch.setattr(config, 'log', log)
    monkeypatch.setattr(memory._tls, 'silent', False, raising=False)

    def boom(*a, **k):
        raise RuntimeError('scan blew up')
    monkeypatch.setattr(lessons, 'scan_sessions', boom)

    t = lessons.start_background_scan('/p', '/f', ['s1'])
    assert t is not None and threads == [t]
    assert log.calls == ['lessons: background scan failed']
    assert memory._tls.silent is True


def test_scan_explicit_empty_list_is_not_pending(graph, monkeypatch):
    """sids == [] is an explicit empty list: pending_sids is not consulted, the
    result is (0, 0) and nothing is saved. Catches: the 'is not None' choice at
    lessons.py:225 and the 'if todo' guard at lessons.py:238."""
    def no_pending(*a, **k):
        raise AssertionError('pending_sids consulted for an explicit empty list')
    monkeypatch.setattr(lessons, 'pending_sids', no_pending)
    assert lessons.scan_sessions('/p', '/f', []) == (0, 0)
    assert graph['saves'] == []


def test_scan_keeps_completed_sids_when_later_one_fails(graph, monkeypatch):
    """Each sid is saved as it completes. When the second extract raises, the
    first sid's lesson and its lessons_scanned stamp are already on disk, and the
    second is not stamped. Catches: the per-sid save at lessons.py:235-236."""
    def extract(p, f, sid):
        if sid == 's2':
            raise RuntimeError('model call died')
        return [_lesson_item('first')]
    monkeypatch.setattr(lessons, 'extract_lessons', extract)
    with pytest.raises(RuntimeError):
        lessons.scan_sessions('/p', '/f', ['s1', 's2'])
    got = graph['graph']
    assert [e['name'] for e in got['entities']] == ['first']
    assert 's1' in got['lessons_scanned'] and 's2' not in got['lessons_scanned']


def test_scan_survives_convention_sync_failure(graph, monkeypatch):
    """A failing conventions sync is swallowed and the counts are still returned.
    Catches: the bare except at lessons.py:244-245."""
    monkeypatch.setattr(lessons, 'extract_lessons',
                        lambda p, f, sid: [_lesson_item('one')])

    def broken(cfgdir=None):
        raise OSError('global folder locked')
    monkeypatch.setattr(conventions, 'sync_to_global', broken)
    assert lessons.scan_sessions('/p', '/f', ['s1']) == (1, 1)
    assert len(graph['graph']['entities']) == 1


def test_scan_applies_decay_once_after_loop(graph, monkeypatch):
    """Decay runs after the per-sid saves, not during them: the first save still
    holds the stale lesson, the final save does not, and the decay count is not
    part of the return value. Catches: lessons.py:238-240."""
    graph['graph']['session_counter'] = 100
    graph['graph']['entities'] = [_lesson('old', last_used=0)]
    monkeypatch.setattr(lessons, 'extract_lessons',
                        lambda p, f, sid: [_lesson_item('new-' + sid)])
    assert lessons.scan_sessions('/p', '/f', ['s1', 's2']) == (2, 2)
    assert len(graph['saves']) == 3
    assert 'old' in {e['id'] for e in graph['saves'][0]['entities']}
    assert 'old' not in {e['id'] for e in graph['saves'][-1]['entities']}
