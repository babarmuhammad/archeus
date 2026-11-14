"""T-1422: claude_sessions/recall.py memory preview logic, lines 529-584.

Ranked candidate branches, the preview-must-not-reinforce rule first:
1. _try_prompt 564-565        a preview calls retrieve with log=False: hits file untouched
2. memory_status_line 573-578 estimate error and all-empty both give ''
3. memory_status_line 580-581 hook budget 0 still prints (is not None, not falsy)
4. _try_prompt 561-563        empty or cancelled input: no retrieve, no pager
5. _try_prompt 566-568        empty result shows the no-injection sentinel; text shows its lines
6. _try_prompt 564            settings without memory_budget use 600
7. preview_screen 551-556     't' reopens the prompt, any other key returns
8. preview_screen 541-547     rule rows with and without glob, and the empty marker
9. preview_screen 548-550     PER PROMPT header: off with None, ON with a budget
10. preview_screen 537-538    no entities: '(no memory yet)' and the header still shows tokens

Not written: strict xfails. Nothing here contradicts the source.
"""

import os

import pytest

from claude_sessions import config, memory, recall, ui


@pytest.fixture(autouse=True)
def no_worklog(monkeypatch):
    from claude_sessions import worklog
    monkeypatch.setattr(worklog, 'load_worklog', lambda project_path: [])


@pytest.fixture
def hits(tmp_path, monkeypatch):
    p = str(tmp_path / 'hits.log')
    monkeypatch.setattr(recall, 'hits_log_path', lambda project_path, proj_folder: p)
    return p


def _entity():
    return {'name': 'token refresh', 'type': 'concept', 'repo': 'p', 'module': 'auth',
            'summary': 'refresh the authentication token when it expires',
            'source_files': ['auth/tok.py'], 'valid': True, 'hits': 0,
            'created_at': 1, 'confirmed_at': 1}


@pytest.fixture
def mem(monkeypatch):
    m = {'entities': [_entity()], 'relations': [], 'summaries': {}}
    monkeypatch.setattr(memory, 'load_memory', lambda project_path, proj_folder: m)
    return m


@pytest.fixture
def prompt_ui(monkeypatch):
    calls = {'pager': [], 'text': []}
    state = {'text': 'what about the token?'}

    def text_input(label):
        calls['text'].append(label)
        return state['text']

    def pager(title, lines, **kw):
        calls['pager'].append((title, list(lines)))
        return None

    monkeypatch.setattr(ui, 'text_input', text_input)
    monkeypatch.setattr(ui, 'pager', pager)
    return calls, state


def test_try_prompt_preview_never_logs_hits(hits, mem, prompt_ui):
    calls, _ = prompt_ui
    recall._try_prompt('/proj', None, 'proj', {'memory_budget': 600})
    assert len(calls['pager']) == 1
    assert calls['pager'][0][1] != ['(nothing relevant — no injection)']
    assert not os.path.exists(hits)


def test_try_prompt_real_retrieve_logs_when_asked(hits, mem):
    out = recall.retrieve('/proj', None, 'refresh the authentication token', 600, log=True)
    assert out['items']
    assert os.path.exists(hits)


def test_status_line_empty_when_estimate_raises(monkeypatch):
    def boom(*a):
        raise RuntimeError('estimate failed')

    monkeypatch.setattr(recall, 'estimate_surfaces', boom)
    assert recall.memory_status_line('/p', None, {}) == ''


def test_status_line_empty_when_all_surfaces_empty(monkeypatch):
    monkeypatch.setattr(recall, 'estimate_surfaces', lambda *a: {
        'digest_tokens': 0, 'rules': [], 'hook_budget': None})
    assert recall.memory_status_line('/p', None, {}) == ''


def test_status_line_shows_zero_budget(monkeypatch):
    monkeypatch.setattr(recall, 'estimate_surfaces', lambda *a: {
        'digest_tokens': 5, 'rules': [], 'hook_budget': 0})
    assert recall.memory_status_line('/p', None, {}) == 'memory: ~5 tok always · hook <=0/prompt'


def test_try_prompt_empty_input_does_nothing(monkeypatch, prompt_ui):
    calls, state = prompt_ui
    retrieved = []
    monkeypatch.setattr(recall, 'retrieve', lambda *a, **k: retrieved.append(a) or {})
    for answer in ('', None):
        state['text'] = answer
        recall._try_prompt('/proj', None, 'proj', {})
    assert retrieved == []
    assert calls['pager'] == []


def test_try_prompt_empty_result_shows_no_injection_sentinel(monkeypatch, prompt_ui):
    calls, _ = prompt_ui
    monkeypatch.setattr(recall, 'retrieve', lambda *a, **k: {'text': '', 'tokens': 0,
                                                             'items': [], 'empty': True})
    recall._try_prompt('/proj', None, 'proj', {})
    assert calls['pager'][0][1] == ['(nothing relevant — no injection)']


def test_try_prompt_text_result_shows_its_lines(monkeypatch, prompt_ui):
    calls, _ = prompt_ui
    monkeypatch.setattr(recall, 'retrieve', lambda *a, **k: {'text': 'alpha\nbeta', 'tokens': 3,
                                                             'items': [], 'empty': False})
    recall._try_prompt('/proj', None, 'proj', {})
    title, body = calls['pager'][0]
    assert body == ['alpha', 'beta']
    assert title[2] == 'HOOK WOULD INJECT (~3 tok)'


def test_try_prompt_defaults_budget_to_600(monkeypatch, prompt_ui):
    seen = []

    def fake(pp, pf, q, budget, log=True):
        seen.append((budget, log))
        return {'text': '', 'tokens': 0, 'items': [], 'empty': True}

    monkeypatch.setattr(recall, 'retrieve', fake)
    recall._try_prompt('/proj', None, 'proj', {})
    assert seen == [(600, False)]


def _preview(monkeypatch, est, mem_entities=None):
    """Runs preview_screen once (ESC at once); returns the lines it showed."""
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(recall, 'estimate_surfaces', lambda *a: est)
    entities = [_entity()] if mem_entities is None else mem_entities
    monkeypatch.setattr(memory, 'load_memory', lambda pp, pf: {'entities': entities})
    monkeypatch.setattr(memory, 'build_digest_micro', lambda mem: 'digest line')
    shown = []

    def pager(title, lines, **kw):
        if 'MEMORY PREVIEW' in title[2]:
            shown.append(list(lines))
        return None

    monkeypatch.setattr(ui, 'pager', pager)
    monkeypatch.setattr(ui, 'text_input', lambda label: '')
    recall.preview_screen('/proj', None, 'proj')
    return shown[0]


def test_preview_loop_reopens_on_t_and_exits_on_other_key(monkeypatch, prompt_ui):
    calls, state = prompt_ui
    state['text'] = 'q'
    monkeypatch.setattr(recall, 'retrieve', lambda *a, **k: {'text': '', 'tokens': 0,
                                                             'items': [], 'empty': True})
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(recall, 'estimate_surfaces', lambda *a: {
        'digest_tokens': 1, 'rules': [], 'hook_budget': None})
    monkeypatch.setattr(memory, 'load_memory', lambda pp, pf: {'entities': []})
    seq = iter(['t', 't', None])
    count = []

    def pager(title, lines, **kw):
        if 'MEMORY PREVIEW' in title[2]:
            count.append(1)
            return next(seq)
        return None

    monkeypatch.setattr(ui, 'pager', pager)
    recall.preview_screen('/proj', None, 'proj')
    assert len(count) == 3
    assert len(calls['text']) == 2


def test_preview_rule_rows_and_empty_marker(monkeypatch):
    est = {'digest_tokens': 4, 'hook_budget': None, 'rules': [
        {'file': 'archeus-mem-a.md', 'tokens': 12, 'glob': 'x/**'},
        {'file': 'archeus-mem-b.md', 'tokens': 7, 'glob': ''},
    ]}
    lines = _preview(monkeypatch, est)
    assert '  archeus-mem-a.md  (~12 tok)  x/**' in lines
    assert '  archeus-mem-b.md  (~7 tok)' in lines

    est['rules'] = []
    assert '  (none generated yet)' in _preview(monkeypatch, est)


@pytest.mark.parametrize('budget, header', [
    (None, 'PER PROMPT — recall hook (off)'),
    (600, 'PER PROMPT — recall hook (ON, budget 600 tok)'),
])
def test_preview_hook_header_on_and_off(monkeypatch, budget, header):
    est = {'digest_tokens': 4, 'hook_budget': budget, 'rules': []}
    assert header in _preview(monkeypatch, est)


def test_preview_empty_memory_still_renders_header(monkeypatch):
    est = {'digest_tokens': 9, 'hook_budget': None, 'rules': []}
    lines = _preview(monkeypatch, est, mem_entities=[])
    assert lines[0] == 'ALWAYS LOADED — CLAUDE.md memory block  (~9 tok)'
    assert '  (no memory yet)' in lines
