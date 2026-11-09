import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, DOWN, ENTER, ESC

from claude_sessions import hooks, status_hook
from claude_sessions.session_menu import sessions_menu
from claude_sessions.sessions import scan_sessions

SCRIPT = os.path.join(os.path.dirname(status_hook.__file__), 'status_hook.py')


def _payload(cfg, event, sid='abc-123', **extra):
    return {'hook_event_name': event, 'session_id': sid,
            'transcript_path': os.path.join(str(cfg), 'projects', 'enc', sid + '.jsonl'), **extra}


def test_each_event_writes_its_state(tmp_path):
    for event, extra, want in [
            ('UserPromptSubmit', {}, 'working'),
            ('Notification', {'notification_type': 'permission_prompt'}, 'needs_input'),
            ('Notification', {}, 'needs_input'),
            ('Notification', {'notification_type': 'idle_prompt'}, 'idle'),
            ('Stop', {}, 'idle')]:
        status_hook.handle(_payload(tmp_path, event, **extra))
        assert status_hook.read_all(str(tmp_path)) == {'abc-123': want}


def test_unrelated_notification_and_bad_session_id_write_nothing(tmp_path):
    status_hook.handle(_payload(tmp_path, 'Notification', notification_type='auth_success'))
    status_hook.handle(_payload(tmp_path, 'Stop', sid='../evil'))
    status_hook.handle(_payload(tmp_path, 'PreToolUse'))
    assert not os.path.exists(tmp_path / status_hook.DIRNAME)


def test_a_state_older_than_the_ttl_is_a_ghost(tmp_path):
    status_hook.handle(_payload(tmp_path, 'UserPromptSubmit'))
    p = tmp_path / status_hook.DIRNAME / 'abc-123.json'
    v = json.loads(p.read_text())
    v['ts'] -= status_hook.TTL + 1
    p.write_text(json.dumps(v))
    assert status_hook.read_all(str(tmp_path)) == {}


def test_the_script_never_fails_the_agent(tmp_path):
    for stdin in ('not json', '[]', ''):
        r = subprocess.run([sys.executable, SCRIPT], input=stdin, text=True,
                           capture_output=True, timeout=30)
        assert r.returncode == 0 and r.stdout == ''
    r = subprocess.run([sys.executable, SCRIPT], text=True, capture_output=True, timeout=30,
                       input=json.dumps(_payload(tmp_path, 'Stop')))
    assert r.returncode == 0 and r.stdout == ''
    assert status_hook.read_all(str(tmp_path)) == {'abc-123': 'idle'}


def test_install_is_idempotent_repairs_and_uninstall_leaves_foreign_hooks(tmp_path, monkeypatch):
    sp = tmp_path / 'settings.json'
    monkeypatch.setattr(hooks, 'settings_path', str(sp))
    foreign = {'hooks': [{'type': 'command', 'command': 'beep'}]}
    sp.write_text(json.dumps({'hooks': {'Stop': [foreign]}, 'permissions': {'allow': ['x']}}))
    assert not hooks.status_hook_installed()
    assert hooks.install_status_hook() and hooks.install_status_hook()
    d = json.loads(sp.read_text())
    assert hooks.status_hook_installed()
    for event in ('UserPromptSubmit', 'Notification', 'Stop'):
        ours = [h for e in d['hooks'][event] for h in e['hooks'] if 'status_hook.py' in h['command']]
        assert len(ours) == 1
    d['hooks']['Stop'][1]['hooks'][0]['command'] = '"old-python" "/gone/status_hook.py"'
    sp.write_text(json.dumps(d))
    assert hooks.install_status_hook()
    assert json.loads(sp.read_text())['hooks']['Stop'][1]['hooks'][0]['command'] == hooks._status_hook_command()

    assert hooks.uninstall_status_hook() and hooks.uninstall_status_hook()
    d = json.loads(sp.read_text())
    assert d['hooks'] == {'Stop': [foreign]} and d['permissions'] == {'allow': ['x']}
    assert not hooks.status_hook_installed()


def test_hooks_menu_row_toggles_it_and_nothing_installs_unasked(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    assert not hooks.status_hook_installed()
    on = DOWN * 5 + ENTER + ESC          # past the five template/edit rows
    run_flow(monkeypatch, on, hooks.hooks_menu)
    assert hooks.status_hook_installed()
    run_flow(monkeypatch, DOWN * 3 + on, hooks.hooks_menu)   # three hook rows now sit above
    assert not hooks.status_hook_installed()


def test_session_list_shows_the_state(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _, enc, folder, sids = sb.add_project(n_sessions=2)
    status_hook.handle(_payload(sb.cfg, 'Notification', sid=sids[0]))
    status_hook.handle(_payload(sb.cfg, 'UserPromptSubmit', sid=sids[1]))
    _, cap, _ = run_flow(monkeypatch, ESC, sessions_menu,
                         scan_sessions(folder), folder, 'proj', str(sb.root / 'work' / 'proj'))
    assert 'needs input' in cap.plain and 'working' in cap.plain
