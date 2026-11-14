"""Hook ownership by file identity: hooks._is_ours and hooks.former_script on tmp_path seams."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import hooks


def _boom(*args, **kw):
    raise AssertionError('former-install fallback must not be reached')


def test_P1_malformed_hook_shapes_are_refused_before_the_filesystem():
    for h in ('not-a-dict', ['type', 'command'], None, 42,
              {},
              {'command': None},
              {'command': {'type': 'command'}},
              {'type': 'command'},
              {'command': 'python %s' % os.path.join(hooks._PKG, 'status_hook.py')},
              {'command': '"python" "%s" extra' % os.path.join(hooks._PKG, 'status_hook.py')},
              {'command': '"python" "%s" || exit 0 || rm -rf /'
                          % os.path.join(hooks._PKG, 'status_hook.py')},
              {'command': '"python" "%s" "more"' % os.path.join(hooks._PKG, 'status_hook.py')},
              {'command': '  '}):
        assert hooks._is_ours(h, 'status_hook.py') is False, h
    assert hooks._is_ours({'command': ''}, 'status_hook.py') is False


def test_P2_live_namesake_under_our_dir_name_is_refused_before_any_fallback(tmp_path, monkeypatch):
    namesake = tmp_path / 'claude_sessions' / 'status_hook.py'
    namesake.parent.mkdir()
    namesake.write_text('# theirs, and still on disk\n')
    assert not os.path.samefile(str(namesake), os.path.join(hooks._PKG, 'status_hook.py'))
    monkeypatch.setattr(hooks, 'former_script', _boom)
    cmd = '"python" "%s" || exit 0' % namesake
    assert hooks._is_ours({'command': cmd}, 'status_hook.py') is False


def test_P3_path_equality_never_rescues_an_existing_file_that_fails_identity(tmp_path, monkeypatch):
    # the '..' spelling normalizes to our path, so only the identity check can say no
    spell = os.path.join(hooks._PKG, 'sub', '..', 'status_hook.py')
    assert os.path.normcase(os.path.normpath(spell)) == \
        os.path.normcase(os.path.join(hooks._PKG, 'status_hook.py'))
    exists_seen, same_seen = [], []
    monkeypatch.setattr(os.path, 'exists', lambda p: exists_seen.append(p) or True)
    monkeypatch.setattr(os.path, 'samefile',
                        lambda a, b: same_seen.append((a, b)) or False)
    monkeypatch.setattr(hooks, 'former_script', _boom)
    assert hooks._is_ours({'command': '"python" "%s"' % spell}, 'status_hook.py') is False
    assert exists_seen == [spell] and same_seen == [(spell, os.path.join(hooks._PKG,
                                                                         'status_hook.py'))]
    assert os.listdir(tmp_path) == []


def test_P4_live_directory_is_refused_by_identity_without_fallback_or_touches(tmp_path, monkeypatch):
    d = tmp_path / 'claude_sessions' / 'status_hook.py'
    d.mkdir(parents=True)
    same_seen = []
    monkeypatch.setattr(os.path, 'samefile',
                        lambda a, b: same_seen.append((a, b)) or False)
    monkeypatch.setattr(hooks, 'former_script', _boom)
    assert hooks._is_ours({'command': '"python" "%s" || exit 0' % d}, 'status_hook.py') is False
    assert same_seen == [(str(d), os.path.join(hooks._PKG, 'status_hook.py'))]
    assert d.is_dir() and d.parent.is_dir()
    assert sorted(os.listdir(tmp_path)) == ['claude_sessions']


def test_P5_install_twice_and_uninstall_keep_the_package_named_foreign_hook(tmp_path):
    cfgdir = tmp_path / 'claude-config'
    cfgdir.mkdir()
    home = tmp_path / 'company-app'
    (home / 'claude_sessions').mkdir(parents=True)
    theirs = home / 'claude_sessions' / 'status_hook.py'
    theirs.write_text('# theirs, live\n')
    cmd_theirs = '"python" "%s" || exit 0' % theirs
    sp = cfgdir / 'settings.json'
    sp.write_text(json.dumps({'hooks': {'Stop': [{'hooks': [
        {'type': 'command', 'command': cmd_theirs}]}]}, 'permissions': {'allow': ['x']}}))

    assert hooks.install_status_hook(cfgdir=str(cfgdir)) is True
    assert hooks.install_status_hook(cfgdir=str(cfgdir)) is True
    d = json.loads(sp.read_text())
    for event in hooks._STATUS_EVENTS:
        ours = [h for e in d['hooks'][event] for h in e['hooks']
                if h.get('command') == hooks._status_hook_command()]
        assert len(ours) == 1, event
    assert hooks.status_hook_installed(cfgdir=str(cfgdir))

    assert hooks.uninstall_status_hook(cfgdir=str(cfgdir)) is True
    assert hooks.uninstall_status_hook(cfgdir=str(cfgdir)) is True
    d = json.loads(sp.read_text())
    assert d['hooks'] == {'Stop': [{'hooks': [{'type': 'command', 'command': cmd_theirs}]}]}
    assert d['permissions'] == {'allow': ['x']}
    assert theirs.read_text() == '# theirs, live\n'
    assert not hooks.status_hook_installed(cfgdir=str(cfgdir))


def test_P6_our_missing_script_is_ours_by_path_equality_alone(tmp_path, monkeypatch):
    # exists is faked False, so only the path-equality arm can answer True
    monkeypatch.setattr(os.path, 'exists', lambda p: False)
    same_seen = []
    monkeypatch.setattr(os.path, 'samefile',
                        lambda a, b: same_seen.append((a, b)) or True)
    monkeypatch.setattr(hooks, 'former_script', _boom)
    cmd = '"python" "%s" || exit 0' % os.path.join(hooks._PKG, 'status_hook.py')
    assert hooks._is_ours({'command': cmd}, 'status_hook.py') is True
    assert same_seen == []


def test_P7_dead_foreign_basename_under_our_dir_name_is_not_ours(tmp_path, monkeypatch):
    dead = tmp_path / 'claude_sessions' / 'their_status_hook.py'
    monkeypatch.setattr(hooks, 'former_script', _boom)
    cmd = '"python" "%s" || exit 0' % dead
    assert hooks._is_ours({'command': cmd}, 'status_hook.py') is False
    monkeypatch.setattr(hooks, 'former_script', lambda p: True)
    ours = tmp_path / 'claude_sessions' / 'status_hook.py'
    assert hooks._is_ours({'command': '"python" "%s"' % ours}, 'status_hook.py') is True


def test_P8_former_script_never_claims_a_file_that_is_still_there(tmp_path):
    live = tmp_path / 'claude_sessions' / 'status_hook.py'
    live.parent.mkdir()
    live.write_text('# still installed somewhere else\n')
    assert hooks.former_script(str(live)) is False
    assert hooks.former_script(os.path.join(str(tmp_path), 'claude_sessions',
                                            'status_hook.py')) is False


def test_P9_former_script_refuses_relative_paths_without_touching_the_fs(tmp_path, monkeypatch):
    def no_fs(*a):
        raise AssertionError('filesystem consulted for a relative path')
    monkeypatch.setattr(os.path, 'exists', no_fs)
    rel = os.path.join(os.path.basename(hooks._PKG), 'status_hook.py')
    assert hooks.former_script(rel) is False
    assert hooks.former_script('./status_hook.py') is False


def test_P10_identity_race_error_fails_closed_with_the_fallback_silent(tmp_path, monkeypatch):
    # exists says True, then samefile loses the race: must return False, not fall through
    gone = tmp_path / 'claude_sessions' / 'status_hook.py'
    monkeypatch.setattr(os.path, 'exists', lambda p: True)

    def race(*a):
        raise FileNotFoundError(2, 'race')
    monkeypatch.setattr(os.path, 'samefile', race)
    monkeypatch.setattr(hooks, 'former_script', _boom)
    assert hooks._is_ours({'command': '"python" "%s" || exit 0' % gone}, 'status_hook.py') is False
