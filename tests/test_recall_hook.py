import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox

from claude_sessions import memory, hooks

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'claude_sessions', 'recall_hook.py')


def _run_hook(stdin_text, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, HOOK], input=stdin_text,
                          capture_output=True, text=True, timeout=30, env=e)


def _graph():
    return {'schema_version': 2, 'entities': [
        {'name': 'UsageParser', 'type': 'component',
         'summary': 'parses plan usage limits', 'repo': 'app', 'module': 'usage',
         'source_files': ['app/usage.py'], 'rank': 5}],
        'relations': [], 'summaries': {}, 'provenance': {},
        'module_edges': [], 'lessons_scanned': {}, 'session_counter': 0}


def test_hook_injects_context(monkeypatch, tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    mdir = proj / '.archeus' / 'memory'
    mdir.mkdir(parents=True)
    (mdir / 'graph.json').write_text(json.dumps(_graph()), encoding='utf-8')
    # settings live in the REAL ~/.claude/archeus.json — force enable via env-safe
    # temp settings file by pointing USERPROFILE at tmp
    home = tmp_path / 'home'
    (home / '.claude').mkdir(parents=True)
    (home / '.claude' / 'archeus.json').write_text(
        json.dumps({'memory_prompt_hook': True, 'memory_budget': 600}), encoding='utf-8')
    payload = json.dumps({'hook_event_name': 'UserPromptSubmit',
                          'cwd': str(proj), 'prompt': 'fix the usage limits parser'})
    r = _run_hook(payload, env={'USERPROFILE': str(home)})
    assert r.returncode == 0
    out = json.loads(r.stdout)
    hso = out['hookSpecificOutput']
    assert hso['hookEventName'] == 'UserPromptSubmit'
    assert 'UsageParser' in hso['additionalContext']


def test_hook_silent_without_graph(tmp_path):
    proj = tmp_path / 'empty'
    proj.mkdir()
    payload = json.dumps({'hook_event_name': 'UserPromptSubmit',
                          'cwd': str(proj), 'prompt': 'anything'})
    r = _run_hook(payload)
    assert r.returncode == 0 and r.stdout.strip() == ''


def test_hook_silent_on_malformed_stdin(tmp_path):
    r = _run_hook('this is not json {')
    assert r.returncode == 0 and r.stdout.strip() == ''


def test_hook_disabled_by_default(tmp_path):
    proj = tmp_path / 'proj'
    (proj / '.archeus' / 'memory').mkdir(parents=True)
    (proj / '.archeus' / 'memory' / 'graph.json').write_text(
        json.dumps(_graph()), encoding='utf-8')
    home = tmp_path / 'home'
    (home / '.claude').mkdir(parents=True)          # no settings → default off
    payload = json.dumps({'hook_event_name': 'UserPromptSubmit',
                          'cwd': str(proj), 'prompt': 'usage'})
    r = _run_hook(payload, env={'USERPROFILE': str(home)})
    assert r.returncode == 0 and r.stdout.strip() == ''


# ── installer ────────────────────────────────────────────────

def test_install_and_uninstall_memory_hook(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    sp = str(sb.cfg / 'settings.json')
    monkeypatch.setattr(hooks, 'settings_path', sp)
    assert not hooks.memory_hook_installed()
    assert hooks.install_memory_hook()
    assert hooks.memory_hook_installed()
    d = json.load(open(sp, encoding='utf-8'))
    cmd = d['hooks']['UserPromptSubmit'][0]['hooks'][0]['command']
    assert 'recall_hook.py' in cmd and cmd.startswith('"')
    # idempotent
    assert hooks.install_memory_hook()
    assert len(d['hooks']['UserPromptSubmit']) == 1
    # stale path repaired
    d['hooks']['UserPromptSubmit'][0]['hooks'][0]['command'] = '"old.exe" "x/recall_hook.py"'
    json.dump(d, open(sp, 'w', encoding='utf-8'))
    assert hooks.install_memory_hook()
    d2 = json.load(open(sp, encoding='utf-8'))
    assert sys.executable in d2['hooks']['UserPromptSubmit'][0]['hooks'][0]['command']
    # uninstall
    assert hooks.uninstall_memory_hook()
    assert not hooks.memory_hook_installed()
