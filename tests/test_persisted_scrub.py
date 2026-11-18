"""T-1090: what Archeus persists in a project is redacted before it is written (the
bash log, denied.jsonl, the memory rule files, the memory block), and a read-only check
reports secrets in the project's Claude Code settings and whether git would commit them
(owner item 101: report only). Every secret here is synthetic."""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, ENTER

from claude_sessions import health, memrules

_PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'claude_sessions')
S = 'SYNTHhunter2'
CMD = 'PGPASSWORD=%s psql -h db.example.com' % S


def _hook(payload, *args):
    # a plain script, as hooks.py spawns it: the sys.path bootstrap is what makes the
    # `archeus` import work, so it is run here and not imported
    return subprocess.run([sys.executable, os.path.join(_PKG, 'logbash_hook.py'), *args],
                          input=json.dumps(payload).encode(), capture_output=True, timeout=60)


def test_the_bash_log_is_redacted_by_the_hook_script(tmp_path):
    r = _hook({'cwd': str(tmp_path), 'tool_input': {'command': CMD}})
    assert r.returncode == 0, r.stderr
    log = (tmp_path / '.archeus' / 'bash-log.txt').read_text(encoding='utf-8')
    assert S not in log and 'PGPASSWORD=[redacted] psql' in log


def test_denied_jsonl_is_redacted_by_the_hook_script(tmp_path):
    r = _hook({'cwd': str(tmp_path), 'tool_name': 'Bash', 'tool_input': {'command': CMD},
               'permission_decision_reason': 'denied: ' + CMD}, '--denied')
    assert r.returncode == 0, r.stderr
    rec = json.loads((tmp_path / '.archeus' / 'denied.jsonl').read_text(encoding='utf-8'))
    assert S not in json.dumps(rec) and rec['command'].startswith('PGPASSWORD=[redacted]')


def test_a_secret_is_redacted_before_the_record_is_cut(tmp_path):
    from claude_sessions import automode
    automode.record(str(tmp_path), 'Bash', 'x' * 490 + ' TOKEN=' + S, '')
    rec = json.loads((tmp_path / '.archeus' / 'denied.jsonl').read_text(encoding='utf-8'))
    assert 'SYNTH' not in rec['command']


def test_a_hook_that_cannot_write_still_exits_zero(tmp_path):
    blocker = tmp_path / 'file'
    blocker.write_text('x')
    assert _hook({'cwd': str(blocker), 'tool_input': {'command': CMD}}).returncode == 0
    r = subprocess.run([sys.executable, os.path.join(_PKG, 'logbash_hook.py')],
                       input=b'not json', capture_output=True, timeout=60)
    assert r.returncode == 0


def test_a_memory_rule_body_is_redacted():
    ents = [{'name': 'Db', 'type': 'service', 'summary': 'connect with ' + CMD},
            {'name': 'Api', 'type': 'service', 'summary': 'x'}]
    body = memrules.render_rule('r', 'm', 'export API_KEY=' + S, ents, [])
    assert S not in body and 'API_KEY=[redacted]' in body


def test_the_memory_block_is_redacted(monkeypatch, tmp_path):
    from claude_sessions import claude_md
    claude_md.write_memory_block(str(tmp_path), '- Db — ' + CMD)
    text = (tmp_path / 'CLAUDE.md').read_text(encoding='utf-8')
    assert S not in text and 'PGPASSWORD=[redacted]' in text


@pytest.mark.parametrize('command', [CMD, 'curl -u admin:%s https://x' % S, 'TOKEN=%s make' % S,
                                     'sk-ant-api03-%s run' % ('A' * 20), 'git status'])
def test_an_allowlist_candidate_is_one_bare_word(monkeypatch, tmp_path, command):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    line = {'message': {'role': 'assistant', 'content': [
        {'type': 'tool_use', 'name': 'Bash', 'input': {'command': command}}]}}
    with open(os.path.join(folder, 'aaa.jsonl'), 'w', encoding='utf-8') as f:
        f.write((json.dumps(line) + '\n') * 3)
    res, _cap, _ = run_flow(monkeypatch, ENTER, health.propose_allowlist, actual, folder)
    sp = os.path.join(actual, '.claude', 'settings.json')
    rules = json.load(open(sp, encoding='utf-8'))['permissions']['allow'] if os.path.isfile(sp) else []
    from archeus.core.redact import redact
    for rule in rules:
        word = rule[len('Bash('):-len(':*)')]
        assert '=' not in word and ' ' not in word and redact(word) == word, rule
    assert rules == {'git status': ['Bash(git:*)'], 'curl -u admin:%s https://x' % S: ['Bash(curl:*)']}.get(command, [])


_git = pytest.mark.skipif(not shutil.which('git'), reason='git not installed')


@pytest.fixture
def _no_git_config(monkeypatch, tmp_path_factory):
    # a user's global excludes file may ignore settings.local.json already
    home = str(tmp_path_factory.mktemp('home'))
    for k, v in (('HOME', home), ('USERPROFILE', home), ('XDG_CONFIG_HOME', home),
                 ('GIT_CONFIG_GLOBAL', os.path.join(home, 'gitconfig')), ('GIT_CONFIG_NOSYSTEM', '1')):
        monkeypatch.setenv(k, v)


def _project(tmp_path, local=None, shared=None):
    subprocess.run(['git', 'init', '-q'], cwd=str(tmp_path), check=True)
    (tmp_path / '.claude').mkdir()
    for name, allow in (('settings.local.json', local), ('settings.json', shared)):
        if allow is not None:
            (tmp_path / '.claude' / name).write_text(
                json.dumps({'permissions': {'allow': allow}}, indent=2), encoding='utf-8')
    return str(tmp_path)


def _snapshot(root):
    return {os.path.join(d, n): open(os.path.join(d, n), 'rb').read()
            for d, _, ns in os.walk(root) if '.git' not in d.split(os.sep) for n in ns}


@_git
@pytest.mark.usefixtures('_no_git_config')
def test_a_secret_in_a_local_allow_rule_is_reported_masked(tmp_path):
    root = _project(tmp_path, local=['Bash(ls:*)', 'Bash(%s)' % CMD])
    before = _snapshot(root)
    found = health.settings_hygiene(root)
    assert {'path': os.path.join('.claude', 'settings.local.json'), 'line': 5, 'rule': 'permissions.allow',
            'sample': '"Bash(PGPASSWORD=[redacted] psql -h db.example.com)"'} in found
    assert S not in json.dumps(found)
    assert {'path': os.path.join('.claude', 'settings.local.json'), 'line': 0,
            'rule': 'not ignored by git', 'sample': ''} in found
    assert _snapshot(root) == before


@_git
@pytest.mark.usefixtures('_no_git_config')
def test_an_ignored_local_settings_file_with_no_secret_is_not_reported(tmp_path):
    root = _project(tmp_path, local=['Bash(ls:*)'])
    (tmp_path / '.gitignore').write_text('.claude/settings.local.json\n', encoding='utf-8')
    assert health.settings_hygiene(root) == []


@_git
@pytest.mark.usefixtures('_no_git_config')
def test_a_committed_settings_file_with_a_secret_is_reported_tracked(tmp_path):
    root = _project(tmp_path, shared=['Bash(curl -u admin:%s https://x)' % S])
    subprocess.run(['git', 'add', '.claude/settings.json'], cwd=root, check=True)
    found = health.settings_hygiene(root)
    assert [f['rule'] for f in found] == ['permissions.allow', 'tracked by git']


@_git
@pytest.mark.usefixtures('_no_git_config')
def test_a_secret_in_an_archeus_rule_file_is_reported(tmp_path):
    root = _project(tmp_path)
    rules = tmp_path / '.claude' / 'rules'
    rules.mkdir()
    (rules / 'archeus-mem-x.md').write_text('# x\n- Db — %s\n' % CMD, encoding='utf-8')
    (rules / 'mine.md').write_text(CMD, encoding='utf-8')
    found = health.settings_hygiene(root)
    rel = os.path.join('.claude', 'rules', 'archeus-mem-x.md')
    assert [(f['path'], f['line'], f['rule']) for f in found] == \
        [(rel, 2, 'memory rule'), (rel, 0, 'not ignored by git')]


@_git
@pytest.mark.usefixtures('_no_git_config')
def test_the_health_card_warns_and_never_fixes(tmp_path):
    root = _project(tmp_path, local=['Bash(%s)' % CMD])
    before = _snapshot(root)
    issues = health._check_settings_hygiene(root)
    assert [s for s, _m, _h in issues] == ['warn', 'warn'] and S not in repr(issues)
    assert 'never' in issues[0][2]
    assert _snapshot(root) == before


def test_no_settings_file_no_finding_and_no_git(monkeypatch, tmp_path):
    from claude_sessions import repos
    monkeypatch.setattr(repos, '_git', lambda *a, **k: pytest.fail('git spawned'))
    assert health.settings_hygiene(str(tmp_path)) == []
