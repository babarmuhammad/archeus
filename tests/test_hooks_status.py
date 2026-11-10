import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

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
    d['hooks']['Stop'][1]['hooks'][0]['command'] = '"old-python" "%s"' % (
        tmp_path / 'gone' / 'claude_sessions' / 'status_hook.py')
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
    run_flow(monkeypatch, DOWN * 4 + on, hooks.hooks_menu)   # four hook rows now sit above
    assert not hooks.status_hook_installed()


def test_session_list_shows_the_state(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _, enc, folder, sids = sb.add_project(n_sessions=2)
    status_hook.handle(_payload(sb.cfg, 'Notification', sid=sids[0]))
    status_hook.handle(_payload(sb.cfg, 'UserPromptSubmit', sid=sids[1]))
    _, cap, _ = run_flow(monkeypatch, ESC, sessions_menu,
                         scan_sessions(folder), folder, 'proj', str(sb.root / 'work' / 'proj'))
    assert 'needs input' in cap.plain and 'working' in cap.plain


def test_the_command_exits_zero_when_the_script_is_gone(tmp_path):
    gone = tmp_path / 'moved' / 'status_hook.py'
    cmd = hooks._status_hook_command().replace(SCRIPT, str(gone))
    assert str(gone) in cmd and 'status_hook.py' in cmd
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
    assert r.returncode == 0


def test_a_disabled_status_hook_is_seen_and_not_installed_twice_and_is_removed(monkeypatch, tmp_path):
    sp = tmp_path / 'settings.json'
    monkeypatch.setattr(hooks, 'settings_path', str(sp))
    assert hooks.install_status_hook()
    d = json.loads(sp.read_text())
    d['hooks_disabled'], d['hooks'] = d['hooks'], {}
    sp.write_text(json.dumps(d))
    assert hooks.status_hook_installed()
    assert hooks.install_status_hook()
    d = json.loads(sp.read_text())
    assert not d.get('hooks')
    assert sum(len(v) for v in d['hooks_disabled'].values()) == 4
    assert hooks.uninstall_status_hook()
    d = json.loads(sp.read_text())
    assert not d.get('hooks') and not d.get('hooks_disabled')
    assert not hooks.status_hook_installed()


def test_install_survives_foreign_junk_in_settings(monkeypatch, tmp_path):
    sp = tmp_path / 'settings.json'
    monkeypatch.setattr(hooks, 'settings_path', str(sp))
    sp.write_text(json.dumps({'hooks': {'Stop': ['junk', {'hooks': ['junk']}]}}))
    assert hooks.install_status_hook() and hooks.status_hook_installed()
    sp.write_text(json.dumps({'hooks': {'Stop': 'junk'}}))
    assert not hooks.install_status_hook()
    sp.write_text(json.dumps({'hooks': []}))
    assert not hooks.install_status_hook()


def test_session_end_deletes_the_state_file(tmp_path):
    status_hook.handle(_payload(tmp_path, 'Stop'))
    assert status_hook.read_all(str(tmp_path)) == {'abc-123': 'idle'}
    status_hook.handle(_payload(tmp_path, 'SessionEnd'))
    assert status_hook.read_all(str(tmp_path)) == {}
    assert not (tmp_path / status_hook.DIRNAME / 'abc-123.json').exists()
    status_hook.handle(_payload(tmp_path, 'SessionEnd', sid='never-seen'))


def test_read_all_deletes_a_ghost_file(tmp_path):
    status_hook.handle(_payload(tmp_path, 'UserPromptSubmit'))
    p = tmp_path / status_hook.DIRNAME / 'abc-123.json'
    v = json.loads(p.read_text())
    v['ts'] -= status_hook.TTL + 1
    p.write_text(json.dumps(v))
    assert status_hook.read_all(str(tmp_path)) == {}
    assert not p.exists()


def test_a_session_id_with_a_trailing_newline_writes_nothing(tmp_path):
    status_hook.handle(_payload(tmp_path, 'Stop', sid='abc\n'))
    assert not os.path.exists(tmp_path / status_hook.DIRNAME)


def test_a_relative_transcript_path_does_not_write_into_the_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'cfg'))
    status_hook.handle({'hook_event_name': 'Stop', 'session_id': 'abc-123',
                        'transcript_path': 'projects/x/y.jsonl'})
    assert not (tmp_path / 'archeus-status').exists()
    assert status_hook.read_all(str(tmp_path / 'cfg')) == {'abc-123': 'idle'}


def test_the_temp_file_name_is_unique_per_process(tmp_path, monkeypatch):
    seen = []
    real = os.replace
    monkeypatch.setattr(os, 'replace', lambda a, b: (seen.append(os.path.basename(a)), real(a, b)))
    status_hook.handle(_payload(tmp_path, 'Stop'))
    assert seen == ['abc-123.%d.tmp' % os.getpid()]


def test_a_foreign_hook_of_the_same_script_name_is_never_ours(tmp_path, monkeypatch):
    sp = tmp_path / 'settings.json'
    monkeypatch.setattr(hooks, 'settings_path', str(sp))
    live = tmp_path / 'company' / 'status_hook.py'
    live.parent.mkdir()
    live.write_text('# theirs')
    theirs = [{'type': 'command', 'command': 'python /company/status_hook.py'},
              {'type': 'command', 'command': '"python" "%s"' % live}]
    sp.write_text(json.dumps({'hooks': {'Stop': [{'hooks': theirs}]}}))
    assert not hooks.status_hook_installed()
    assert hooks.install_status_hook()
    assert json.loads(sp.read_text())['hooks']['Stop'][0]['hooks'] == theirs
    assert hooks.uninstall_status_hook()
    assert json.loads(sp.read_text())['hooks'] == {'Stop': [{'hooks': theirs}]}


def _stop_hooks(sp, monkeypatch, *commands):
    monkeypatch.setattr(hooks, 'settings_path', str(sp))
    theirs = [{'type': 'command', 'command': c} for c in commands]
    sp.write_text(json.dumps({'hooks': {'Stop': [{'hooks': theirs}]}}))
    return theirs


def test_a_path_that_does_not_resolve_here_is_not_a_former_install(tmp_path, monkeypatch):
    # relative: it resolves where the hook runs, not where the manager does; and a
    # dead absolute one outside a package directory of ours was never written by us
    theirs = _stop_hooks(tmp_path / 'settings.json', monkeypatch,
                         '"python" "./company/status_hook.py"',
                         '"python" "claude_sessions/status_hook.py"',
                         '"python" "%s"' % (tmp_path / 'gone' / 'status_hook.py'))
    monkeypatch.chdir(tmp_path)
    assert not hooks.status_hook_installed()
    assert hooks.install_status_hook()
    assert json.loads((tmp_path / 'settings.json').read_text())['hooks']['Stop'][0]['hooks'] == theirs
    assert hooks.uninstall_status_hook()
    assert json.loads((tmp_path / 'settings.json').read_text())['hooks'] == {'Stop': [{'hooks': theirs}]}


def test_a_former_install_whose_checkout_is_gone_is_ours_and_is_repaired(tmp_path, monkeypatch):
    sp = tmp_path / 'settings.json'
    _stop_hooks(sp, monkeypatch, '"C:\\gone\\python.exe" "%s" || exit 0'
                % (tmp_path / 'old' / 'claude_sessions' / 'status_hook.py'))
    assert hooks.install_status_hook()
    assert json.loads(sp.read_text())['hooks']['Stop'] == [
        {'hooks': [{'type': 'command', 'command': hooks._status_hook_command()}]}]


@pytest.mark.skipif(os.path.normcase('A') == 'A', reason='file names are case-sensitive here')
def test_our_hook_is_ours_however_its_path_is_cased(tmp_path, monkeypatch):
    sp = tmp_path / 'settings.json'
    monkeypatch.setattr(hooks, 'settings_path', str(sp))
    assert hooks.install_status_hook()
    sp.write_text(sp.read_text().replace('status_hook.py', 'STATUS_HOOK.PY')
                  .replace('claude_sessions', 'Claude_Sessions'))
    assert hooks.status_hook_installed()
    assert hooks.install_status_hook()
    stop = json.loads(sp.read_text())['hooks']['Stop']
    assert stop == [{'hooks': [{'type': 'command', 'command': hooks._status_hook_command(),
                                'timeout': 5}]}]
    assert hooks.uninstall_status_hook() and not json.loads(sp.read_text()).get('hooks')
