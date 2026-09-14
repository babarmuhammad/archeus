"""Phase 3 gates: the transcript never lands in memory, and no state file is
rewritten on a per-turn path.

The sizes here are real. A single project directory on the machine this was
written for holds transcripts past 100 MB, and `/api/dashboard` polls every
10 seconds.
"""

import io
import json
import os

import pytest

from claude_sessions import transcript, transcripts


def _fat_transcript(path, n_messages, filler=4000):
    """A transcript whose SIZE is dominated by tool traffic, like a real one."""
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        for i in range(n_messages):
            f.write(json.dumps({
                'message': {'role': 'user' if i % 2 else 'assistant',
                            'content': [{'type': 'text', 'text': 'm%d' % i}]},
                'timestamp': '2026-08-12T00:00:0%dZ' % (i % 10)}) + '\n')
            f.write(json.dumps({          # the bulk: a tool call and its result
                'message': {'role': 'assistant',
                            'content': [{'type': 'tool_use', 'name': 'Read',
                                         'input': {'file_path': 'x', 'pad': 'z' * filler}}]}}) + '\n')
    return path


def test_a_transcript_is_never_materialised(tmp_path):
    """`readlines()` on a 100 MB file is the memory ceiling of the whole app."""
    p = _fat_transcript(str(tmp_path / 's.jsonl'), 400)
    size = os.path.getsize(p)
    assert size > 1_000_000, 'the fixture is not big enough to be evidence'

    import tracemalloc
    tracemalloc.start()
    got = transcript.page(p, 0, 10)
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(got['messages']) == 10
    assert peak < size // 4, (
        'peak %d bytes for a %d byte transcript — it was materialised' % (peak, size))


def test_paging_reports_where_the_next_page_starts(tmp_path):
    p = _fat_transcript(str(tmp_path / 's.jsonl'), 60)
    first = transcript.page(p, 0, 10)
    assert len(first['messages']) == 10 and first['more']
    assert first['next_offset'] > 10, \
        'next_offset must count LINES consumed, not messages returned'

    second = transcript.page(p, first['next_offset'], 10)
    assert second['messages'] and second['messages'] != first['messages']
    assert second['messages'][0]['text'] == 'm10'


def test_the_last_page_says_there_is_no_more(tmp_path):
    p = _fat_transcript(str(tmp_path / 's.jsonl'), 5)
    got = transcript.page(p, 0, 400)
    assert len(got['messages']) == 5 and not got['more']


def test_the_api_caps_the_page_size(monkeypatch, tmp_path):
    """A caller asking for everything must not be able to undo the paging."""
    from claude_sessions import gui_api
    assert gui_api._TRANSCRIPT_PAGE <= 1000


# ── settings round-trip ──────────────────────────────────────

def test_an_unknown_settings_key_survives_a_round_trip(monkeypatch, tmp_path):
    """save_settings writes back what load_settings returned, so dropping the
    keys this version does not know means an older archeus ERASES a newer
    one's settings — and syncing this file between two machines is enough."""
    from claude_sessions import config
    p = tmp_path / 'archeus.json'
    p.write_text(json.dumps({'theme': 'nord', 'a_future_key': {'deep': [1, 2]}}),
                 encoding='utf-8')
    monkeypatch.setattr(config, 'settings_file', str(p))

    s = config.load_settings()
    s['theme'] = 'gruvbox'
    config.save_settings(s)

    back = json.loads(p.read_text(encoding='utf-8'))
    assert back['theme'] == 'gruvbox'
    assert back['a_future_key'] == {'deep': [1, 2]}
    assert '_unknown' not in back, 'the parking key must never reach the file'


# ── per-turn writes ──────────────────────────────────────────

def test_the_recall_hook_does_not_rewrite_the_graph(monkeypatch, tmp_path):
    """It runs on every UserPromptSubmit; memory.save_memory does TWO atomic
    writes."""
    from claude_sessions import memory, recall
    import ast
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'claude_sessions', 'recall.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == 'retrieve')
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'save_memory']
    assert not calls, 'retrieve() writes the graph on the per-prompt path'


def test_the_worklog_hook_is_bound_to_session_end_not_every_turn():
    """Stop fires on EVERY turn and the capture re-streams the whole growing
    transcript; it only needs to run once."""
    from claude_sessions import hooks
    assert 'Stop' not in hooks._WORKLOG_EVENTS
    assert 'SessionEnd' in hooks._WORKLOG_EVENTS


def test_the_bash_log_stops_growing(tmp_path, monkeypatch):
    """It had reached 90 KB unbounded, and it is appended to inside a
    PreToolUse hook — on the turn's critical path."""
    import claude_sessions.logbash_hook as lb
    p = tmp_path / 'bash-log.txt'
    p.write_text('\n'.join('cmd %d' % i for i in range(30000)) + '\n', encoding='utf-8')
    assert p.stat().st_size > lb._MAX_BYTES
    lb._rotate(str(p))
    assert p.stat().st_size <= lb._MAX_BYTES
    lines = p.read_text(encoding='utf-8').splitlines()
    assert lines[-1] == 'cmd 29999', 'rotation kept the wrong end'
    assert lines[0].startswith('cmd '), 'a half-line survived the seek'


def test_the_statusline_does_not_reparse_an_unchanged_graph(monkeypatch, tmp_path):
    """It runs on every conversation turn."""
    from claude_sessions import memory, statusline
    proj = tmp_path / 'proj'
    (proj / memory.MEM_SUBDIR).mkdir(parents=True)
    mem = memory._empty()
    mem['entities'] = [{'name': 'X', 'type': 'component', 'summary': 's'}]
    (proj / memory.MEM_SUBDIR / memory.GRAPH_NAME).write_text(
        json.dumps(mem), encoding='utf-8')

    statusline._graph_cache.clear()
    calls = []
    real = memory.load_memory
    monkeypatch.setattr(memory, 'load_memory',
                        lambda *a, **kw: (calls.append(1), real(*a, **kw))[1])
    a = statusline._load(str(proj))
    b = statusline._load(str(proj))
    assert a['entities'] and b['entities']
    assert len(calls) == 1, 'the graph was parsed twice for one unchanged file'


# ── hooks are entry points, not libraries ────────────────────

def test_no_library_module_imports_a_hook_script():
    """A `*_hook.py` reconfigures stdout at IMPORT, because Claude Code hands
    it a pipe. Importing one as a library runs that line in whatever process
    did the importing — and `sys.stdout` is None in a windowed one (pythonw,
    no console, i.e. the GUI). `memory.drain_dirty` did exactly this and took
    the whole auto-memory cycle down with
    `AttributeError: 'NoneType' object has no attribute 'reconfigure'`.

    The dependency may only point hook -> library.
    """
    import ast
    import glob
    pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'claude_sessions')
    offenders = []
    for path in glob.glob(os.path.join(pkg, '*.py')):
        name = os.path.basename(path)
        if name.endswith('_hook.py'):
            continue                      # a hook may import whatever it likes
        tree = ast.parse(open(path, encoding='utf-8').read(), filename=path)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            elif isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            for m in mods:
                if m.split('.')[-1].endswith('_hook'):
                    offenders.append(f'{name}:{node.lineno} imports {m}')
    assert not offenders, (
        'a library module imported a hook entry point:\n  '
        + '\n  '.join(offenders))


def test_every_hook_survives_a_missing_stdout(monkeypatch):
    """The reconfigure that makes a hook's output survive a pipe must not be
    the thing that kills it when there is no stdout at all."""
    import glob
    import re
    pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'claude_sessions')
    bare = []
    for path in sorted(glob.glob(os.path.join(pkg, '*_hook.py'))):
        src = open(path, encoding='utf-8').read()
        for m in re.finditer(r'^(\s*)sys\.std(?:out|err)\.reconfigure\(', src, re.M):
            if not m.group(1):            # column 0 == not inside a try block
                bare.append(f'{os.path.basename(path)}:'
                            f'{src[:m.start()].count(chr(10)) + 1}')
    assert not bare, (
        'unguarded module-level reconfigure — dies when sys.stdout is None:\n  '
        + '\n  '.join(bare))
