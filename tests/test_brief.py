import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox

from claude_sessions import brief, memory


def test_work_suggestions_from_signals(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    mem = memory._empty()
    mem['entities'] = [
        {'name': 'Fix1', 'type': 'lesson', 'kind': 'error_fix', 'status': 'approved',
         'summary': 'retry-after backoff needed', 'repo': '', 'module': ''},
        {'name': 'Engine', 'type': 'component', 'summary': 'core', 'repo': 'app',
         'module': 'engine', 'rank': 20},
    ]
    memory.save_memory(actual, folder, mem)
    sug = brief.work_suggestions(actual, folder)
    txts = ' '.join(t for _tag, t in sug)
    assert 'recurring issue' in txts and 'retry-after' in txts
    assert 'central module' in txts and 'app/engine' in txts


def test_a_bare_project_is_told_how_to_start(monkeypatch, tmp_path):
    """An untouched project has no lessons and no graph, but it is NOT out of
    things to say: every point of freshness it is missing is a step it has not
    taken yet. The list used to fall through to 'no signals yet'."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    sug = brief.work_suggestions(actual, folder)
    txts = ' '.join(t for _s, t in sug)
    assert sug
    assert 'no signals' in txts or 'no semantic memory' in txts \
        or any(tag == 'stale' for tag, _t in sug)
    # and every stale line names the remedy, not just the symptom
    for tag, text in sug:
        if tag == 'stale':
            assert '—' in text and 'freshness' in text


def test_dismissing_a_scan_finding_is_remembered(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    brief.save_scan(actual, folder, [{'kind': 'vuln', 'text': 'cfgdir is not validated anywhere'},
                                     {'kind': 'idea', 'text': 'add a per-account status column'}])
    txts = ' '.join(t for _s, t in brief.work_suggestions(actual, folder))
    assert 'cfgdir is not validated' in txts and 'per-account status' in txts

    brief.dismiss_scan_item(actual, folder, 'cfgdir is not validated anywhere')
    txts = ' '.join(t for _s, t in brief.work_suggestions(actual, folder))
    assert 'cfgdir is not validated' not in txts and 'per-account status' in txts

    # a re-scan must not resurrect what you already said no to
    brief.save_scan(actual, folder, [{'kind': 'vuln', 'text': 'cfgdir is not validated anywhere'}])
    txts = ' '.join(t for _s, t in brief.work_suggestions(actual, folder))
    assert 'cfgdir is not validated' not in txts


def test_the_work_list_never_calls_claude(monkeypatch, tmp_path):
    """Rendering is free. `run_scan` is the only path allowed to spend a token,
    and it is behind a button — the recall hook's lesson, applied to advice."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')

    def _boom(*a, **k):
        raise AssertionError('work_suggestions made a model call')

    monkeypatch.setattr(memory, '_claude_stdin', _boom)
    brief.work_suggestions(actual, folder)


def test_scan_output_is_parsed_leniently_and_tagged_safely(monkeypatch, tmp_path):
    items = brief.parse_scan(
        "- bug|gui_api unpacks a None return from prune_claude_md\n"
        "vuln | cfgdir is joined with a path on forty endpoints\n"
        "```\n"
        "nonsense|a kind nobody defined\n"
        "x\n"
        "idea|short\n")
    kinds = [i['kind'] for i in items]
    texts = ' '.join(i['text'] for i in items)
    assert 'bug' in kinds and 'vuln' in kinds
    # an unknown kind keeps its sentence but cannot invent a new tag
    assert 'idea' in kinds and 'nonsense' not in kinds
    assert 'prune_claude_md' in texts
    # too short to be a finding
    assert 'short' not in texts


def test_session_diff_non_git(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    out = brief.session_diff(actual, folder)
    assert out and 'nothing to diff' in out[0]


def test_session_diff_git(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    def _g(*a):
        subprocess.run(['git', *a], cwd=actual, capture_output=True, text=True)
    _g('init'); _g('config', 'user.email', 't@t'); _g('config', 'user.name', 't')
    open(os.path.join(actual, 'f.txt'), 'w').write('x')
    _g('add', '-A'); _g('commit', '-m', 'first commit here')
    out = brief.session_diff(actual, folder)
    assert any('commit' in l.lower() for l in out)


def test_session_diff_subproject_repo(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    # NO git at root — repo lives in a sub-project
    sub = os.path.join(actual, 'service')
    os.makedirs(sub)
    def _g(*a):
        subprocess.run(['git', *a], cwd=sub, capture_output=True, text=True)
    _g('init'); _g('config', 'user.email', 't@t'); _g('config', 'user.name', 't')
    open(os.path.join(sub, 'f.txt'), 'w').write('x')
    _g('add', '-A'); _g('commit', '-m', 'subproject commit xyz')
    out = brief.session_diff(actual, folder)
    joined = '\n'.join(out)
    assert 'service' in joined and 'subproject commit' in joined
