"""T-1404 — claude_sessions/gui_api.py lessons and ctxaudit prune handlers, lines 2609-2674.

Candidate list, refusal first:
 1. 2645-2647  api_lessons_post: unknown action refused, no _set_status or _evict call
 2. 2637-2638  'evict' without body['id'] is a BadRequest through call()
 3. 2632       missing body['enc'] is a BadRequest through call(), nothing loaded
 4. 2639-2644  approve_all touches only pending lessons
 5. 2634-2636  'approve' maps to approved, 'pin' maps to pinned
 6. 2613-2614  lesson sort: pending first, then higher confidence
 7. 2613/2618  fixed: a status-less lesson sorts as non-pending but is reported as pending
 8. 2626-2627  counter defaults to 0, ttl defaults to 30
 9. 2671-2672  api_ctxaudit_prune: None result is refused as not ok
10. 2661-2664  api_ctxaudit_prune_preview: None refused, a result exposes exactly four keys

Seams: gui_api._folder, memory.load_memory, lessons._set_status, lessons._evict,
config.load_settings, claude_md.prune_preview and claude_md.prune_claude_md are
replaced with fakes. No server, no real config dir, no network.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import claude_md, config, gui_api, lessons, memory


@pytest.fixture()
def folder(monkeypatch, tmp_path):
    proj_folder = str(tmp_path / 'folder')
    monkeypatch.setattr(gui_api, '_folder', lambda cfgdir, enc: proj_folder)
    return proj_folder


@pytest.fixture()
def spies(monkeypatch):
    calls = {'set_status': [], 'evict': []}
    monkeypatch.setattr(lessons, '_set_status',
                        lambda *a: calls['set_status'].append(a))
    monkeypatch.setattr(lessons, '_evict', lambda *a: calls['evict'].append(a))
    return calls


def _post(body):
    return gui_api.call(gui_api.api_lessons_post, {}, dict({'enc': 'proj-1', 'path': '/p'}, **body))


# 2645-2647 — unknown action: refused, neither mutator runs
def test_lessons_post_unknown_action_writes_nothing(spies, monkeypatch, folder):
    saved = []
    monkeypatch.setattr(memory, 'save_memory', lambda *a: saved.append(a))
    assert _post({'action': 'delete', 'id': 'l1'}) == {'ok': False, 'error': 'unknown action'}
    assert spies == {'set_status': [], 'evict': []}
    assert saved == []


# 2637-2638 — evict without an id is the caller's fault, not a 500
def test_lessons_post_evict_without_id_is_bad_request(spies, folder):
    with pytest.raises(gui_api.BadRequest, match='missing parameter: id'):
        _post({'action': 'evict'})
    assert spies['evict'] == []


# 2632 — missing enc is refused before any memory is read
def test_lessons_post_missing_enc_is_bad_request_and_loads_nothing(spies, monkeypatch, folder):
    loaded = []
    monkeypatch.setattr(memory, 'load_memory', lambda *a: loaded.append(a) or {})
    with pytest.raises(gui_api.BadRequest, match='missing parameter: enc'):
        gui_api.call(gui_api.api_lessons_post, {}, {'action': 'approve_all', 'path': '/p'})
    assert loaded == []
    assert spies == {'set_status': [], 'evict': []}


# 2639-2644 — approve_all approves only pending lessons
def test_approve_all_touches_only_pending_lessons(spies, monkeypatch, folder):
    mem = {'entities': [
        {'type': 'lesson', 'id': 'p1', 'status': 'pending'},
        {'type': 'lesson', 'id': 'a1', 'status': 'approved'},
        {'type': 'lesson', 'id': 'k1', 'status': 'pinned'},
        {'type': 'person', 'id': 'x1', 'status': 'pending'},
        {'type': 'lesson', 'id': 'p2', 'status': 'pending'},
    ]}
    monkeypatch.setattr(memory, 'load_memory', lambda *a: mem)
    assert _post({'action': 'approve_all'}) == {'ok': True}
    assert spies['set_status'] == [('/p', folder, 'p1', 'approved'),
                                   ('/p', folder, 'p2', 'approved')]


# 2634-2636 — approve and pin map to their own status, not to each other
def test_lessons_post_approve_and_pin_map_to_status(spies, folder):
    assert _post({'action': 'approve', 'id': 'l1'}) == {'ok': True}
    assert _post({'action': 'pin', 'id': 'l2'}) == {'ok': True}
    assert spies['set_status'] == [('/p', folder, 'l1', 'approved'),
                                   ('/p', folder, 'l2', 'pinned')]


# 2609-2614 — pending first, then higher confidence first
def test_lessons_get_orders_pending_then_confidence(monkeypatch, folder):
    mem = {'entities': [
        {'type': 'lesson', 'id': 'a', 'status': 'approved', 'confidence': 0.9},
        {'type': 'lesson', 'id': 'p-low', 'status': 'pending', 'confidence': 0.2},
        {'type': 'lesson', 'id': 'p-high', 'status': 'pending', 'confidence': 0.8},
        {'type': 'person', 'id': 'x', 'status': 'pending', 'confidence': 1.0},
    ]}
    monkeypatch.setattr(memory, 'load_memory', lambda *a: mem)
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    out = gui_api.call(gui_api.api_lessons_get, {'path': '/p', 'enc': 'proj-1',
                                                 'cfgdir': None}, None)
    assert [row['id'] for row in out['lessons']] == ['p-high', 'p-low', 'a']


# 2613/2618 — fixed: a lesson without a status sorts with the pending group,
# the group its row reports it in
def test_lessons_get_status_less_lesson_sorts_as_pending(monkeypatch, folder):
    mem = {'entities': [
        {'type': 'lesson', 'id': 'a', 'status': 'approved', 'confidence': 0.5},
        {'type': 'lesson', 'id': 'p', 'status': 'pending', 'confidence': 0.1},
        {'type': 'lesson', 'id': 'sl', 'confidence': 0.9},
    ]}
    monkeypatch.setattr(memory, 'load_memory', lambda *a: mem)
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    out = gui_api.call(gui_api.api_lessons_get, {'path': '/p', 'enc': 'proj-1',
                                                 'cfgdir': None}, None)
    assert [row['id'] for row in out['lessons']] == ['sl', 'p', 'a']
    assert out['lessons'][0]['status'] == 'pending'


# 2626-2627 — counter and ttl fall back to 0 and 30
def test_lessons_get_counter_and_ttl_defaults(monkeypatch, folder):
    monkeypatch.setattr(memory, 'load_memory', lambda *a: {'entities': []})
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    out = gui_api.call(gui_api.api_lessons_get, {'path': '/p', 'enc': 'proj-1',
                                                 'cfgdir': None}, None)
    assert out == {'lessons': [], 'counter': 0, 'ttl': 30}


# 2671-2672 — no CLAUDE.md (prune returns None) is refused as not ok
def test_ctxaudit_prune_none_is_reported_as_not_ok(monkeypatch, folder):
    monkeypatch.setattr(claude_md, 'prune_claude_md', lambda *a: None)
    out = gui_api.call(gui_api.api_ctxaudit_prune, {}, {'enc': 'proj-1', 'path': '/p'})
    assert out == {'ok': False, 'error': 'no CLAUDE.md in this project'}


# 2661-2664 — preview: None is refused; a result exposes exactly four keys
def test_ctxaudit_prune_preview_shape_and_refusal(monkeypatch, folder):
    monkeypatch.setattr(claude_md, 'prune_preview', lambda *a: None)
    out = gui_api.call(gui_api.api_ctxaudit_prune_preview, {'enc': 'proj-1', 'path': '/p'}, None)
    assert out == {'ok': False, 'error': 'no CLAUDE.md in this project'}

    preview = {'old_tokens': 900, 'new_tokens': 400, 'dropped': ['s1'],
               'changed': True, 'text': 'full body must not leak'}
    monkeypatch.setattr(claude_md, 'prune_preview', lambda *a: preview)
    out = gui_api.call(gui_api.api_ctxaudit_prune_preview, {'enc': 'proj-1', 'path': '/p'}, None)
    assert out == {'ok': True, 'old_tokens': 900, 'new_tokens': 400,
                   'dropped': ['s1'], 'changed': True}
