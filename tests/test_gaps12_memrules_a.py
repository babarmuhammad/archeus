"""T-1421: claude_sessions/memrules.py rule naming and glob scoping, lines 23-81.

Ranked candidate branches, pruning and overwrite risk first:
1. sync_rules 137-141       two units whose names differ only in separators both survive
2. rule_filename 23-24      non-ASCII-only and empty names fall back to 'root'
3. sync_rules 156-161       a user rule file (no archeus-mem- prefix) is never pruned
4. _unit_glob 46-48         blank source_files entries are ignored
5. _unit_glob 55            backslash paths scope like posix paths
6. _unit_glob 58-62         common prefix is taken over path segments
7. _unit_glob 74-75         module boundary is a path, not a string, prefix
8. _unit_glob 63-64         root-like module names are never scoped
9. _unit_glob 77-78         no common prefix: the unit's own module dir
10. _unit_glob 44-81        a unit with no files: module scope, else '*'

Probe 1 is refuted at unit level: sync_rules adds a sha256 suffix when two units
map to one name (memrules.py:138-140), so both files are written. Covered here
by a passing test, no strict xfail. Closest existing test: test_gaps6 test_colliding_units_survive.
"""

import os

import pytest

from claude_sessions import config, memrules


@pytest.fixture
def rules_on(monkeypatch):
    monkeypatch.setattr(config, 'load_settings', lambda: {'memory_rules': True})


def _ent(name, module, files):
    return {'name': name, 'type': 'component', 'repo': 'proj', 'module': module,
            'summary': 'x', 'source_files': files, 'valid': True}


def test_units_differing_only_in_separators_do_not_share_a_file(tmp_path, rules_on):
    mem = {'entities': [
        _ent('a1', 'x/y', ['x/y/a.py']), _ent('a2', 'x/y', ['x/y/b.py']),
        _ent('b1', 'x_y', ['x_y/c.py']), _ent('b2', 'x_y', ['x_y/d.py']),
    ]}
    written = memrules.sync_rules(str(tmp_path), None, mem)
    rules_dir = os.path.join(str(tmp_path), '.claude', 'rules')
    assert len(set(written)) == 2
    assert sorted(os.listdir(rules_dir)) == sorted(written)
    bodies = {nm: open(os.path.join(rules_dir, nm), encoding='utf-8').read() for nm in written}
    assert any('# proj/x/y' in b for b in bodies.values())
    assert any('# proj/x_y' in b for b in bodies.values())


def test_user_rule_file_survives_sync_and_stale_own_file_is_pruned(tmp_path, rules_on):
    rules_dir = os.path.join(str(tmp_path), '.claude', 'rules')
    os.makedirs(rules_dir)
    with open(os.path.join(rules_dir, 'my-rule.md'), 'w', encoding='utf-8') as f:
        f.write('mine')
    with open(os.path.join(rules_dir, 'archeus-mem-stale.md'), 'w', encoding='utf-8') as f:
        f.write('old')
    mem = {'entities': [_ent('a1', 'pkg', ['pkg/a.py']), _ent('a2', 'pkg', ['pkg/b.py'])]}
    memrules.sync_rules(str(tmp_path), None, mem)
    assert os.path.exists(os.path.join(rules_dir, 'my-rule.md'))
    assert not os.path.exists(os.path.join(rules_dir, 'archeus-mem-stale.md'))


def test_non_ascii_only_name_falls_back_to_root():
    assert memrules.rule_filename('p', 'λ') == 'archeus-mem-p-root.md'
    assert memrules.rule_filename('p', '') == 'archeus-mem-p-root.md'


def test_blank_source_file_is_ignored():
    assert memrules._unit_glob([{'source_files': ['  ', '']}], 'claude_sessions/ui') == 'claude_sessions/ui/**'
    assert memrules._unit_glob([{'source_files': ['  ']}], '') == '*'


def test_windows_separators_give_same_glob_as_posix():
    win = memrules._unit_glob([{'source_files': ['claude_sessions\\ui\\x.py']}], '')
    posix = memrules._unit_glob([{'source_files': ['claude_sessions/ui/x.py']}], '')
    assert win == posix == 'claude_sessions/ui/**'


def test_common_prefix_is_segmentwise_not_characterwise():
    ents = [{'source_files': ['ab/x.py']}, {'source_files': ['abc/y.py']}]
    assert memrules._unit_glob(ents, '') == '*'


def test_module_prefix_boundary_is_path_not_string():
    ents = [{'source_files': ['claude_sessions/ui/x.py', 'claude_sessions/ui/y.py']}]
    assert memrules._unit_glob(ents, 'claude_sessions') == 'claude_sessions/**'
    assert memrules._unit_glob(ents, 'claude_sess') == 'claude_sessions/ui/**'


@pytest.mark.parametrize('module', ['(root)', '.', '/', ''])
def test_root_like_module_names_are_unscoped(module):
    assert memrules._unit_glob([{'source_files': ['README.md']}], module) == '*'
    assert memrules._unit_glob([{'source_files': []}], module) == '*'


def test_no_common_prefix_falls_back_to_module_dir():
    ents = [{'source_files': ['ab/x.py']}, {'source_files': ['cd/y.py']}]
    assert memrules._unit_glob(ents, 'claude_sessions/ui') == 'claude_sessions/ui/**'


def test_unit_without_files_scopes_to_module_or_star():
    assert memrules._unit_glob([{}], 'pkg') == 'pkg/**'
    assert memrules._unit_glob([{}], '') == '*'
