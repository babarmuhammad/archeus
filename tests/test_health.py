import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, ENTER, ESC

from claude_sessions import health


def test_claudemd_over_budget(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    open(os.path.join(actual, 'CLAUDE.md'), 'w', encoding='utf-8').write('word ' * 3000)
    issues = health._check_claudemd(actual)
    assert issues and 'heavy' in issues[0][1]


def test_claudemd_ok_within_budget(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    open(os.path.join(actual, 'CLAUDE.md'), 'w', encoding='utf-8').write('# small\n')
    assert health._check_claudemd(actual) == []


def test_missing_add_dir_flagged(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    with open(os.path.join(folder, 'add-dirs.txt'), 'w', encoding='utf-8') as f:
        f.write(r'C:\definitely\not\there' + '\n')
    issues = health._check_dirs(folder)
    assert issues and 'add-dir path missing' in issues[0][1]


def test_session_log_appended(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, sids = sb.add_project('alpha', n_sessions=1)
    ok = health.append_session_log(actual, folder, sids[0])
    assert ok
    log = open(os.path.join(actual, '.archeus', 'session-log.md'),
               encoding='utf-8').read()
    assert sids[0][:8] in log and 'goal:' in log


def test_frequent_bash_commands(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    lines = []
    for i in range(4):
        lines.append({'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'name': 'Bash', 'input': {'command': f'git status {i}'}}]}})
    lines.append({'message': {'role': 'assistant', 'content': [
        {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'rm -rf x'}}]}})
    with open(os.path.join(folder, 'aaa.jsonl'), 'w', encoding='utf-8') as f:
        for o in lines:
            f.write(json.dumps(o) + '\n')
    freq = health.frequent_bash_commands(folder, min_count=3)
    assert freq == [('git', 4)]                     # rm below threshold


def test_propose_allowlist_writes_on_approve(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    lines = [{'message': {'role': 'assistant', 'content': [
        {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'git log'}}]}}] * 3
    with open(os.path.join(folder, 'aaa.jsonl'), 'w', encoding='utf-8') as f:
        for o in lines:
            f.write(json.dumps(o) + '\n')
    res, cap, _ = run_flow(monkeypatch, ENTER, health.propose_allowlist, actual, folder)
    n, err = res
    assert n == 1 and err == ''
    sp = json.load(open(os.path.join(actual, '.claude', 'settings.json'), encoding='utf-8'))
    assert 'Bash(git:*)' in sp['permissions']['allow']


def test_check_project_aggregates(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    issues = health.check_project(actual, folder)
    assert any('no semantic memory' in m for _s, m, _h in issues)
