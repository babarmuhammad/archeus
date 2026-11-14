"""Gap tests for ctxaudit.audit_items: session cap, CLAUDE.md line and heading
checks, protected rows, global and rules rows, the SessionStart hook loop and
the big-item warning. Every source of context (global CLAUDE.md, hooks, MCP,
token counter) is faked; nothing reads a real home or a real config file."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import config as _c
from claude_sessions import ctxaudit, hooks, mcp, workspace


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(ctxaudit, 'tokens_estimate', lambda s: len(s))
    monkeypatch.setattr(workspace, '_global_md_paths', lambda: [])
    monkeypatch.setattr(hooks, '_load', lambda cfgdir=None: {})
    monkeypatch.setattr(mcp, '_mcp_ready', False, raising=False)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return path


def _sessions_block(n):
    entries = '\n'.join(f'- topic {i}' for i in range(n))
    return f'{_c._SESSIONS_START}\n{entries}\n{_c._SESSIONS_END}\n'


def _by_label(items):
    return {i['label']: i for i in items}


def _claudemd_project(tmp_path, text):
    proj = tmp_path / 'proj'
    _write(str(proj / 'CLAUDE.md'), text)
    return str(proj)


def test_session_cap_zero_or_none_disables_the_warning(tmp_path):
    proj = _claudemd_project(tmp_path, '# Compact instructions\n' + _sessions_block(3))
    for cap in (0, None):
        items = ctxaudit.audit_items(proj, None, settings={'claude_md_sessions_cap': cap})
        row = _by_label(items)['CLAUDE.md · session topics (3)']
        assert row['warnings'] == [], cap
    items = ctxaudit.audit_items(proj, None, settings={'claude_md_sessions_cap': 2})
    row = _by_label(items)['CLAUDE.md · session topics (3)']
    assert row['warnings'] == ['3 session entries (cap 2) — prune (p)']


def test_session_entries_cap_is_strict(tmp_path):
    settings = {'claude_md_sessions_cap': 3}
    exact = _claudemd_project(tmp_path / 'a', _sessions_block(3))
    over = _claudemd_project(tmp_path / 'b', _sessions_block(4))
    assert _by_label(ctxaudit.audit_items(exact, None, settings))[
        'CLAUDE.md · session topics (3)']['warnings'] == []
    assert _by_label(ctxaudit.audit_items(over, None, settings))[
        'CLAUDE.md · session topics (4)']['warnings'] == [
        '4 session entries (cap 3) — prune (p)']


def test_claudemd_line_limit_is_strict(tmp_path):
    line_warn = 'CLAUDE.md > 200 lines — compress it (c)'
    at_limit = _claudemd_project(tmp_path / 'a', 'x\n' * 200)
    over_limit = _claudemd_project(tmp_path / 'b', 'x\n' * 201)
    row = _by_label(ctxaudit.audit_items(at_limit, None, {}))['CLAUDE.md · manual content']
    assert line_warn not in row['warnings']
    row = _by_label(ctxaudit.audit_items(over_limit, None, {}))['CLAUDE.md · manual content']
    assert line_warn in row['warnings']


def test_compact_heading_match_ignores_case(tmp_path):
    proj = _claudemd_project(tmp_path, '# COMPACT Instructions\nbody\n')
    row = _by_label(ctxaudit.audit_items(proj, None, {}))['CLAUDE.md · manual content']
    assert not any('Compact instructions' in w for w in row['warnings'])


def test_protected_row_appears_only_when_fenced(tmp_path):
    plain = _claudemd_project(tmp_path / 'a', 'just prose\n')
    assert not [l for l in _by_label(ctxaudit.audit_items(plain, None, {}))
                if l.startswith('CLAUDE.md · protected')]
    fenced_text = (f'prose\n{_c._KEEP_START}\nkeep this\n{_c._KEEP_END}\n')
    fenced = _claudemd_project(tmp_path / 'b', fenced_text)
    by = _by_label(ctxaudit.audit_items(fenced, None, {}))
    row = by['CLAUDE.md · protected (1 fenced)']
    assert row['tokens'] == len(ctxaudit._KEEP_RE.findall(fenced_text)[0])


def test_missing_claudemd_row_has_no_path_without_a_project(tmp_path):
    items = ctxaudit.audit_items('', None, {})
    row = _by_label(items)['CLAUDE.md']
    assert row['tokens'] == 0
    assert row['path'] is None
    assert row['warnings'] == ['missing — press c in the sessions menu to scaffold']


def test_global_rows_label_skip_empty_and_strict_warning(monkeypatch, tmp_path):
    g_default = _write(str(tmp_path / 'g1' / 'CLAUDE.md'), 'a' * 501)
    g_work = _write(str(tmp_path / 'g2' / 'CLAUDE.md'), 'b' * 500)
    g_empty = _write(str(tmp_path / 'g3' / 'CLAUDE.md'), '')
    monkeypatch.setattr(workspace, '_global_md_paths', lambda: [
        ('default', g_default), ('work', g_work), ('spare', g_empty)])
    items = ctxaudit.audit_items('', None, {})
    by = _by_label(items)
    assert 'global CLAUDE.md (spare)' not in by
    assert by['global ~/.claude/CLAUDE.md']['tokens'] == 501
    assert by['global ~/.claude/CLAUDE.md']['warnings'] == [
        '> 500 tok — loads in EVERY project']
    assert by['global CLAUDE.md (work)']['tokens'] == 500
    assert by['global CLAUDE.md (work)']['warnings'] == []


def test_rules_are_md_only_sorted_with_lazy_flag(tmp_path):
    proj = tmp_path / 'proj'
    rules = proj / '.claude' / 'rules'
    _write(str(rules / 'zeta.md'), 'always on\n')
    _write(str(rules / 'alpha.md'), '---\npaths: src/**\n---\nlazy body\n')
    _write(str(rules / 'notes.txt'), 'ignored\n')
    items = ctxaudit.audit_items(str(proj), None, {})
    rule_rows = [i for i in items if i['label'].startswith('rule ')]
    assert [i['label'] for i in rule_rows] == ['rule alpha.md', 'rule zeta.md']
    assert [i['lazy'] for i in rule_rows] == [True, False]


def test_big_item_warning_rules(tmp_path):
    proj = tmp_path / 'proj'
    rules = proj / '.claude' / 'rules'
    _write(str(rules / 'big-always.md'), 'x' * 1001)
    _write(str(rules / 'big-lazy.md'), '---\npaths: src/**\n---\n' + 'x' * 1001)
    items = ctxaudit.audit_items(str(proj), None, {})
    by = _by_label(items)
    assert by['rule big-always.md']['warnings'] == ['> 1000 tok on every turn']
    assert by['rule big-lazy.md']['warnings'] == []


def test_unknown_size_hook_never_gets_the_big_item_warning(monkeypatch):
    monkeypatch.setattr(hooks, '_load', lambda cfgdir=None: {'hooks': {'SessionStart': [
        {'hooks': [{'type': 'command', 'command': 'node some-tool.js'}]}]}})
    items = ctxaudit.audit_items('', None, {})
    row = _by_label(items)['hook SessionStart: node some-tool.js']
    assert row['tokens'] is None
    assert row['warnings'] == ['injection size unknown']


def test_bad_hook_entry_does_not_hide_later_hooks(monkeypatch):
    monkeypatch.setattr(hooks, '_load', lambda cfgdir=None: {'hooks': {'SessionStart': [
        {'hooks': ['not-a-dict', {'type': 'command',
                                  'command': 'python concise_hook.py'}]}]}})
    items = ctxaudit.audit_items('', None, {})
    assert 'hook concise-output (SessionStart)' in _by_label(items)
