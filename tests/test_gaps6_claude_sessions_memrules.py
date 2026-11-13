"""T-1295: claude_sessions/memrules.py:21-160; ranked candidate gaps, not coverage.

1 :152 test_foreign_directory_survives; closest test_memrules: test_sync_prunes_only_own_files checks files only.
2 :152 test_prefixed_user_rule_survives; same closest test assumes prefix ownership.
3 :119 test_disabled_has_no_work; test_setting_disables checks mkdir only.
4 :124/:133 test_invalid_entities_do_not_make_unit; test_sync_writes_a_path_scoped_rule has two valid entities.
5 :26 test_colliding_units_survive; same closest test has one unit.
6 :72/:79 test_sample_scope_and_root; test_a_glob_is_never_narrower_than_its_own_module lacks mixed separators.
7 :53/:58 test_segment_scope; test_the_glob_is_a_path_prefix_not_a_string_prefix lacks blanks and mixed separators.
8 :93/:95 test_frontmatter_quotes_are_inert; test_only_paths_scopes_a_rule uses ordinary identifiers.
9 :104/:112 test_redacted_write_filters_relations; test_persisted_scrub.test_a_memory_rule_body_is_redacted renders only.
10 :147/:157 test_failed_write_does_not_prune; test_sync_prunes_only_own_files has no write failure.
"""

import builtins
from unittest.mock import Mock

import pytest

from claude_sessions import config, memrules


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, 'load_settings', lambda: {'memory_rules': True})
    monkeypatch.setattr(memrules, 'tokens_estimate', lambda text: 0)
    monkeypatch.setattr(memrules, 'redact', lambda text: text)


def entities(module='m'):
    return [{'name': name, 'repo': 'r', 'module': module, 'type': 'component'}
            for name in ('Alpha', 'Beta')]


def rules(tmp_path):
    path = tmp_path / '.claude' / 'rules'
    path.mkdir(parents=True)
    return path


def test_foreign_directory_survives(tmp_path):
    directory = rules(tmp_path)
    foreign = directory / 'archeus-mem-foreign'
    foreign.mkdir()
    (foreign / 'keep.md').write_text('mine', encoding='utf-8')
    user = directory / 'user.md'
    user.write_text('mine', encoding='utf-8')
    assert memrules.sync_rules(str(tmp_path), None, {}) == []
    assert user.read_text(encoding='utf-8') == 'mine'
    assert (foreign / 'keep.md').read_text(encoding='utf-8') == 'mine'


@pytest.mark.xfail(strict=True, reason='Prefix alone deletes user-owned rule: claude_sessions/memrules.py:152-154')
def test_prefixed_user_rule_survives(tmp_path):
    user = rules(tmp_path) / 'archeus-mem-personal.md'
    user.write_text('User authored; no generated ownership marker', encoding='utf-8')
    memrules.sync_rules(str(tmp_path), None, {})
    assert user.exists()
    assert user.read_text(encoding='utf-8').startswith('User authored')


def test_disabled_has_no_work(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'load_settings', lambda: {'memory_rules': False})
    forbidden = Mock(side_effect=AssertionError('disabled work'))
    monkeypatch.setattr(memrules.os, 'makedirs', forbidden)
    monkeypatch.setattr(memrules.os, 'listdir', forbidden)
    monkeypatch.setattr(memrules.os, 'remove', forbidden)
    monkeypatch.setattr(memrules, 'open', forbidden, raising=False)
    monkeypatch.setattr(memrules, 'render_rule', forbidden)
    assert memrules.sync_rules(str(tmp_path), None, {'entities': entities()}) == []
    forbidden.assert_not_called()


def test_invalid_entities_do_not_make_unit(tmp_path):
    rows = entities()
    rows[1]['valid'] = False
    rows.append(dict(rows[0], name='Lesson', type='lesson'))
    assert memrules.sync_rules(str(tmp_path), None, {'entities': rows}) == []
    assert list((tmp_path / '.claude' / 'rules').iterdir()) == []


@pytest.mark.xfail(strict=True, reason='Sanitization aliases units and overwrites: claude_sessions/memrules.py:26')
def test_colliding_units_survive(tmp_path):
    rows = entities('a.b') + [dict(e, name='Other' + e['name']) for e in entities('a_b')]
    names = memrules.sync_rules(str(tmp_path), None, {'entities': rows})
    assert len(set(names)) == 2
    bodies = [(tmp_path / '.claude' / 'rules' / name).read_text(encoding='utf-8')
              for name in names]
    assert any('# r/a.b' in body for body in bodies)
    assert any('# r/a_b' in body for body in bodies)


def test_sample_scope_and_root():
    rows = [{'source_files': [r'pkg\skills\one\a.py', 'pkg/skills/one/b.py']}]
    assert memrules._unit_glob(rows, 'pkg/skills') == 'pkg/skills/**'
    rows.append({'source_files': ['README.md']})
    assert memrules._unit_glob(rows, '(root)') == '*'


def test_segment_scope():
    rows = [{'source_files': [r'tests\a.py', 'tools/b.py', '  ', '']}]
    assert memrules._unit_glob(rows, '') == '*'
    assert memrules._unit_glob(rows, 'tools') == 'tools/**'
    assert memrules._unit_glob([{'source_files': ['pkg/a/x', r'pkg\ab\y']}]) == 'pkg/**'


@pytest.mark.xfail(strict=True, reason='Unescaped YAML identifiers inject keys: claude_sessions/memrules.py:93-95')
def test_frontmatter_quotes_are_inert():
    body = memrules.render_rule('r', 'm"\ninjected: true\n#', '', [], [])
    front = body.split('---')[1]
    assert 'paths:' in front and 'globs:' not in front
    assert '\ninjected:' not in front
    assert len(front.splitlines()) == 4


def test_redacted_write_filters_relations(monkeypatch, tmp_path):
    seen = []

    def redact(text):
        seen.append(text)
        return text.replace('SYNTHETIC_SECRET', '[redacted]')

    monkeypatch.setattr(memrules, 'redact', redact)
    rows = entities()
    rows[0]['summary'] = 'SYNTHETIC_SECRET'
    rels = [{'source': 'Alpha', 'target': 'Beta', 'rel': 'uses'},
            {'source': 'Alpha', 'target': 'Outside', 'rel': 'leaks'},
            {'source': 'Outside', 'target': 'Beta', 'rel': 'leaks'}]
    names = memrules.sync_rules(str(tmp_path), None, {'entities': rows, 'relations': rels})
    body = (tmp_path / '.claude' / 'rules' / names[0]).read_text(encoding='utf-8')
    assert len(seen) == 1 and 'SYNTHETIC_SECRET' in seen[0]
    assert 'SYNTHETIC_SECRET' not in body and '[redacted]' in body
    assert 'Alpha uses Beta' in body and 'Outside' not in body


def test_failed_write_does_not_prune(monkeypatch, tmp_path):
    directory = rules(tmp_path)
    name = memrules.rule_filename('r', 'm')
    good = directory / name
    good.write_text('previous good rule', encoding='utf-8')
    stale = directory / 'archeus-mem-stale.md'
    stale.write_text('previous stale rule', encoding='utf-8')
    events = []

    def failing_open(path, mode='r', **kwargs):
        events.append(mode)
        if mode == 'w':
            raise OSError('synthetic write refusal')
        return builtins.open(path, mode, **kwargs)

    monkeypatch.setattr(memrules, 'open', failing_open, raising=False)
    remove = Mock()
    monkeypatch.setattr(memrules.os, 'remove', remove)
    log = Mock()
    monkeypatch.setattr(config, 'log', log)
    assert memrules.sync_rules(str(tmp_path), None, {'entities': entities()}) == []
    assert events == ['r', 'w']
    remove.assert_not_called()
    log.exception.assert_called_once_with('memrules: sync failed')
    assert good.read_text(encoding='utf-8') == 'previous good rule'
    assert stale.exists()
