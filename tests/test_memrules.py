import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox

from claude_sessions import memrules, memory


def _mem():
    return {
        'entities': [
            {'name': 'Engine', 'type': 'component', 'summary': 'core engine',
             'repo': 'svc', 'module': 'engine', 'source_files': ['svc/engine/core.py']},
            {'name': 'Cache', 'type': 'component', 'summary': 'lru cache',
             'repo': 'svc', 'module': 'engine', 'source_files': ['svc/engine/cache.py']},
            {'name': 'Lonely', 'type': 'component', 'summary': 'single entity',
             'repo': 'svc', 'module': 'tiny', 'source_files': ['svc/tiny/x.py']},
            {'name': 'L', 'type': 'lesson', 'status': 'approved', 'summary': 'x',
             'repo': 'svc', 'module': 'engine', 'source_files': []},
        ],
        'relations': [{'source': 'Engine', 'target': 'Cache', 'rel': 'uses', 'unit': 'svc/engine'}],
        'summaries': {'svc/engine': 'the engine module'},
    }


def test_sync_writes_a_path_scoped_rule(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    written = memrules.sync_rules(actual, folder, _mem())
    assert written == [memrules.rule_filename('svc', 'engine')]
    p = os.path.join(actual, '.claude', 'rules', written[0])
    body = open(p, encoding='utf-8').read()
    # `paths:`, not `globs:` — Claude Code loads a rule with no `paths` field
    # into EVERY session, so the old key made every rule file always-on while
    # archeus reported it as lazy.
    assert 'paths:' in body and '- "svc/engine/**"' in body
    assert 'globs:' not in body
    assert 'Engine' in body and 'Cache' in body
    assert 'the engine module' in body
    assert 'Engine uses Cache' in body
    assert 'Lonely' not in body                     # <2 entities → no rule
    assert '- L (' not in body                      # lessons never in rules


def test_sync_prunes_only_own_files(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    rules_dir = os.path.join(actual, '.claude', 'rules')
    os.makedirs(rules_dir)
    stale = os.path.join(rules_dir, 'archeus-mem-old-unit.md')
    user = os.path.join(rules_dir, 'my-own-rule.md')
    open(stale, 'w').write('x')
    open(user, 'w').write('mine')
    memrules.sync_rules(actual, folder, _mem())
    assert not os.path.exists(stale)                 # our stale file pruned
    assert os.path.exists(user)                      # user rule untouched


def test_rule_token_cap(monkeypatch, tmp_path):
    ents = [{'name': f'E{i}', 'type': 'component', 'summary': 'word ' * 60,
             'repo': 'r', 'module': 'm', 'source_files': ['r/m/a.py']} for i in range(40)]
    body = memrules.render_rule('r', 'm', 'summary', ents, [])
    assert memory.tokens_estimate(body) <= memrules.RULE_MAX_TOKENS + 20


def test_setting_disables(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    monkeypatch.setattr('claude_sessions.config.load_settings',
                        lambda: {'memory_rules': False})
    assert memrules.sync_rules(actual, folder, _mem()) == []
    assert not os.path.isdir(os.path.join(actual, '.claude', 'rules'))


# ── the glob is the whole point of these files ───────────────
# `os.path.commonprefix` is a CHARACTER operation. On this repo it turned
# {tests/, tools/} into the prefix "t" and the glob "t/**" — which matches
# nothing, so that rule's ~375 tokens could never load — while any unit whose
# files diverged at the first segment collapsed to "**", i.e. always loaded, in
# a module whose docstring promises "zero always-on token cost". Both were on
# disk at once.

def test_the_glob_is_a_path_prefix_not_a_string_prefix():
    got = memrules._unit_glob([{'source_files': ['tests/a.py']},
                               {'source_files': ['tools/b.py']}], 'tools')
    assert got != 't/**', 'a character prefix matches nothing'
    assert got.startswith('tools/') or got == '*'


def test_no_generated_rule_is_scoped_to_everything():
    """`**` is indistinguishable from an always-on rule."""
    for ents, mod in (([{'source_files': ['README.md']},
                        {'source_files': ['setup.py']}], '(root)'),
                      ([], ''),
                      ([{'source_files': []}], '')):
        assert memrules._unit_glob(ents, mod) != '**', (ents, mod)


def test_a_unit_with_no_files_falls_back_to_its_own_directory():
    assert memrules._unit_glob([], 'claude_sessions/web') == 'claude_sessions/web/**'


def test_a_normal_nested_unit_keeps_its_full_path():
    got = memrules._unit_glob([{'source_files': ['claude_sessions/web/app.js']},
                               {'source_files': ['claude_sessions/web/motion.js']}],
                              'claude_sessions/web')
    assert got == 'claude_sessions/web/**'


def test_written_rules_are_never_globally_scoped(tmp_path):
    """End to end: whatever the entities look like, nothing on disk says `**`."""
    import re as _re
    mem = {'entities': [
        {'name': 'A', 'type': 'module', 'summary': 's', 'repo': 'R',
         'module': '(root)', 'source_files': ['README.md'], 'valid': True},
        {'name': 'B', 'type': 'module', 'summary': 's', 'repo': 'R',
         'module': '(root)', 'source_files': ['setup.py'], 'valid': True},
    ], 'relations': [], 'summaries': {}}
    memrules.sync_rules(str(tmp_path), None, mem)
    rules = tmp_path / '.claude' / 'rules'
    written = list(rules.glob('archeus-mem-*.md')) if rules.is_dir() else []
    assert written, 'nothing was written'
    for p in written:
        txt = p.read_text(encoding='utf-8')
        assert _re.search(r'(?m)^paths\s*:', txt), f'{p.name} is not path-scoped at all'
        m = _re.search(r'-\s*"([^"]*)"', txt)
        assert m and m.group(1) != '**', p.name


def test_a_root_level_file_is_not_dropped_from_the_prefix():
    """A file at the repo root has an EMPTY dirname. Dropping it computed the
    prefix from the unit's other files, so this repo's `(root)` unit — README.md
    plus claude_sessions/__init__.py — came out scoped `claude_sessions/**`:
    firing on a tree it is not about, never on the root files it IS about."""
    got = memrules._unit_glob([{'source_files': ['README.md']},
                               {'source_files': ['claude_sessions/__init__.py']}],
                              '(root)')
    assert not got.startswith('claude_sessions/'), got
    assert got == '*'


def test_only_paths_scopes_a_rule(monkeypatch, tmp_path):
    """Claude Code scopes a rule file on `paths:` alone — "rules without a
    paths field are loaded unconditionally and apply to all files". `globs:` is
    the Cursor spelling, and writing it meant every memory rule archeus ever
    wrote was loaded into every session while the audit reported it as lazy.
    Verified empirically first: all eleven of this repo's rule files appeared in
    a fresh session's context with no matching file opened."""
    from claude_sessions import ctxaudit, recall
    memrules.sync_rules(str(tmp_path), None, _mem())
    p = next((tmp_path / '.claude' / 'rules').glob('archeus-mem-*.md'))
    txt = p.read_text(encoding='utf-8')

    assert ctxaudit._rule_is_lazy(txt) is True
    assert ctxaudit._rule_is_lazy(txt.replace('paths:', 'globs:')) is False, \
        'a globs-only rule was counted as lazy — it loads in every session'

    unit, glob, scoped = recall._rule_frontmatter(txt)
    assert scoped is True and glob == 'svc/engine/**' and unit == 'svc/engine'
    # the legacy shape still reports its glob, but never claims to be scoped
    _u, g, sc = recall._rule_frontmatter('---\nglobs: "svc/**"\n---\n')
    assert g == 'svc/**' and sc is False


def test_a_glob_is_never_narrower_than_its_own_module(tmp_path):
    """`source_files` is a representative SAMPLE, so a unit whose sample landed
    in one subdirectory scoped itself to that subdirectory. On this repo the
    rule for `plugin/skills` — eight skills — came out `plugin/skills/changelog/**`
    and would have fired for one of them. Invisible while every rule loaded
    unconditionally; a real coverage hole the moment `paths:` scopes for real."""
    mem = {'entities': [
        {'name': 'A', 'type': 'model', 'summary': 's', 'repo': 'R',
         'module': 'plugin/skills', 'source_files': ['plugin/skills/changelog/SKILL.md'],
         'valid': True},
        {'name': 'B', 'type': 'model', 'summary': 's', 'repo': 'R',
         'module': 'plugin/skills', 'source_files': ['plugin/skills/changelog/README.md'],
         'valid': True},
    ], 'relations': [], 'summaries': {}}
    memrules.sync_rules(str(tmp_path), None, mem)
    txt = next((tmp_path / '.claude' / 'rules').glob('archeus-mem-*.md')).read_text(
        encoding='utf-8')
    assert '- "plugin/skills/**"' in txt, txt.splitlines()[:5]
