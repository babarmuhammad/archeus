"""The skills manager, against the scopes Claude Code actually loads.

The old shape of this file tested a private library at
`~/.claude/archeus-skills` — a directory no Claude Code has ever read, so
every one of those assertions was green while the feature was inert. What is
tested now is the inventory: personal (`<account>/skills`), project, plugin, and
the bundled skills that exist only as usage counters.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, typed, DOWN, ENTER, ESC

from claude_sessions import skills, config


def _personal(sb):
    return skills.personal_dir(str(sb.cfg))


# ── pure helpers ─────────────────────────────────────────────

def test_parse_write_roundtrip(tmp_path):
    d = str(tmp_path / 'commit-message')
    assert skills.write_skill(d, {'name': 'commit-message',
                                  'description': 'write commits',
                                  'allowed-tools': 'Read, Bash'},
                              '# Commit\n\nDo it.')
    meta, body = skills.parse_skill(d)
    assert meta['name'] == 'commit-message'
    assert meta['allowed-tools'] == 'Read, Bash'
    assert '# Commit' in body
    assert os.path.isfile(os.path.join(d, 'SKILL.md'))


def test_bundled_templates_all_valid():
    """Every shipped template parses and carries an attribution footer."""
    tmpls = skills.list_skills(skills.bundled_templates_dir())
    assert len(tmpls) >= 6
    for name, desc, d in tmpls:
        meta, body = skills.parse_skill(d)
        assert meta.get('name'), f'{name} missing name'
        assert meta.get('description'), f'{name} missing description'
        assert '<!--' in body and 'archeus' in body.lower(), \
            f'{name} missing attribution footer'


def test_the_personal_scope_is_the_one_claude_code_reads(monkeypatch, tmp_path):
    """`<cfgdir>/skills`, resolved per call.

    The account changes under a running process — the statusline lesson — so a
    module-level constant would pin whichever one was active at import."""
    sb = Sandbox(monkeypatch, tmp_path)
    assert skills.personal_dir(str(sb.cfg)) == os.path.join(str(sb.cfg), 'skills')
    assert skills.personal_dir() == os.path.join(config.config_dir, 'skills')
    # and "my library" now means exactly that, not the private directory
    assert skills.library_dir() == skills.personal_dir()
    assert 'archeus-skills' in skills.legacy_library_dir()


def test_templates_are_starters_not_a_scope(monkeypatch, tmp_path):
    """They used to be merged with the private library into one list labelled
    `[template]`/`[library]`, which made an install SOURCE look like something
    that was loaded."""
    Sandbox(monkeypatch, tmp_path)
    rows = skills.list_templates()
    assert rows and all(src == 'template' for _n, _d, _dir, src in rows)


# ── the inventory ────────────────────────────────────────────

def _usage(sb, mapping):
    """Write Claude Code's own skillUsage into the sandbox account."""
    with open(os.path.join(str(sb.cfg), '.claude.json'), 'w', encoding='utf-8') as f:
        json.dump({'skillUsage': {k: {'usageCount': v, 'lastUsedAt': 0}
                                  for k, v in mapping.items()}}, f)


def test_inventory_reports_every_scope(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    proj = tmp_path / 'proj'
    (proj / '.claude' / 'skills').mkdir(parents=True)
    skills.write_skill(os.path.join(_personal(sb), 'commit-message'),
                       {'name': 'commit-message', 'description': 'commits'}, 'body')
    skills.write_skill(os.path.join(str(proj), '.claude', 'skills', 'deploy'),
                       {'name': 'deploy', 'description': 'ships'}, 'body')
    # a plugin, laid out the way Claude Code lays one out on disk
    pdir = sb.cfg / 'plugins' / 'cache' / 'mkt' / 'demo' / '1.0'
    skills.write_skill(str(pdir / 'skills' / 'review'),
                       {'name': 'review', 'description': 'reviews'}, 'body')
    (sb.cfg / 'plugins').mkdir(exist_ok=True)
    with open(sb.cfg / 'plugins' / 'installed_plugins.json', 'w', encoding='utf-8') as f:
        json.dump({'version': 2, 'plugins': {'demo@mkt': [
            {'scope': 'user', 'installPath': str(pdir), 'version': '1.0'}]}}, f)
    _usage(sb, {'commit-message': 4, 'demo:review': 2, 'doctor': 9})

    inv = skills.inventory(str(proj), str(sb.cfg))
    assert [r['command'] for r in inv['personal']] == ['commit-message']
    assert inv['personal'][0]['uses'] == 4
    assert [r['command'] for r in inv['project']] == ['deploy']
    assert [r['command'] for r in inv['plugin']] == ['demo:review']
    assert inv['plugin'][0]['uses'] == 2
    # a bundled skill exists ONLY as a usage counter — never a hardcoded list
    assert [r['command'] for r in inv['bundled']] == ['doctor']


def test_a_shadowed_project_skill_says_so(monkeypatch, tmp_path):
    """Claude Code resolves personal over project, so an identically named
    project skill never runs. Listing it as if it did is a lie."""
    sb = Sandbox(monkeypatch, tmp_path)
    proj = tmp_path / 'proj'
    for base in (_personal(sb), os.path.join(str(proj), '.claude', 'skills')):
        skills.write_skill(os.path.join(base, 'deploy'),
                           {'name': 'deploy', 'description': 'x'}, 'body')
    inv = skills.inventory(str(proj), str(sb.cfg))
    assert inv['project'][0]['shadowed'] is True
    assert inv['personal'][0]['shadowed'] is False


def test_the_command_is_the_folder_not_the_frontmatter(monkeypatch, tmp_path):
    """For a personal or project skill, Claude Code takes the command from the
    DIRECTORY name; `name:` is only a display label. Showing the label as the
    command tells the user to type something that does not exist."""
    sb = Sandbox(monkeypatch, tmp_path)
    skills.write_skill(os.path.join(_personal(sb), 'deploy-staging'),
                       {'name': 'Fancy Deploy', 'description': 'x'}, 'body')
    row = skills.inventory('', str(sb.cfg))['personal'][0]
    assert row['command'] == 'deploy-staging'
    assert row['name'] == 'Fancy Deploy'


def test_install_targets_the_scope_it_is_given(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    proj = tmp_path / 'proj'
    proj.mkdir()
    src = os.path.join(skills.bundled_templates_dir(), 'commit-message')

    dest = skills.install_skill(src, skills.personal_dir(str(sb.cfg)))
    assert dest.startswith(_personal(sb)) and os.path.isfile(os.path.join(dest, 'SKILL.md'))

    dest2 = skills.install_skill(src, skills.project_skills_dir(str(proj)))
    assert dest2.startswith(str(proj))
    assert skills.delete_skill(dest2)
    assert skills.list_skills(skills.project_skills_dir(str(proj))) == []


def test_a_personal_skill_reaches_every_account(monkeypatch, tmp_path):
    """"Personal" has to mean *you*, not whichever login was active when you
    saved it — the rule the hook fan-out and sync-accounts already follow.
    Without it a skill vanished the moment you switched accounts."""
    sb = Sandbox(monkeypatch, tmp_path)
    other = tmp_path / 'acct-b'
    (other / 'projects').mkdir(parents=True)
    monkeypatch.setattr(config, 'all_config_dirs',
                        lambda: [('default', str(sb.cfg)), ('teamB', str(other))])
    src = os.path.join(skills.bundled_templates_dir(), 'commit-message')

    done = skills.install_personal(src)
    assert [n for n, _d in done] == ['default', 'teamB']
    for d in (sb.cfg, other):
        assert os.path.isfile(os.path.join(str(d), 'skills', 'commit-message', 'SKILL.md'))
    assert skills.personal_accounts(done[0][1]) == ['default', 'teamB']

    gone = skills.delete_personal(done[0][1])
    assert [n for n, _d in gone] == ['default', 'teamB']
    assert not os.path.isdir(os.path.join(str(other), 'skills', 'commit-message'))


def test_usage_is_merged_across_accounts(monkeypatch, tmp_path):
    """The counters are per account, and reading one showed a third of the
    truth to anyone working under several logins."""
    sb = Sandbox(monkeypatch, tmp_path)
    other = tmp_path / 'acct-b'
    other.mkdir()
    monkeypatch.setattr(config, 'all_config_dirs',
                        lambda: [('default', str(sb.cfg)), ('teamB', str(other))])
    _usage(sb, {'commit-message': 3})
    with open(os.path.join(str(other), '.claude.json'), 'w', encoding='utf-8') as f:
        json.dump({'skillUsage': {'commit-message': {'usageCount': 4,
                                                     'lastUsedAt': time.time() * 1000}}}, f)
    got = skills._usage()
    assert got['commit-message']['uses'] == 7
    assert got['commit-message']['last_used'] == 'now', 'the most recent age wins'


def test_the_two_usage_signals_are_kept_apart(monkeypatch, tmp_path):
    """`skillUsage` counts ONE thing: typing `/name`. A plugin that works through
    a SessionStart hook never touches it — which is why caveman reads as "used
    twice, 56 days ago" while shaping every session. The second signal is
    measured from the transcripts, and the two are never merged into one number.
    """
    sb = Sandbox(monkeypatch, tmp_path)
    _usage(sb, {'demo:demo': 2})
    monkeypatch.setattr(skills, '_activity',
                        lambda cfgdir=None: {'of': 30, 'hits': {'demo': 27}})
    monkeypatch.setattr(skills, 'plugin_skills',
                        lambda cfgdir=None: [('demo@mkt', 'demo', str(tmp_path / 'p'))])
    skills.write_skill(str(tmp_path / 'p'),
                       {'name': 'demo', 'description': 'a demo skill that does things'}, 'x')
    row = skills.inventory('', str(sb.cfg))['plugin'][0]
    assert row['uses'] == 2, 'the typed count is still the typed count'
    assert (row['sessions'], row['of_sessions']) == (27, 30)
    assert row['via'] == 'demo'


def test_a_bundles_activity_is_not_credited_to_each_of_its_skills(monkeypatch, tmp_path):
    """The caveman plugin ships thirteen skills. Its hook firing says the BUNDLE
    ran, not that all thirteen were used."""
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(skills, '_activity',
                        lambda cfgdir=None: {'of': 30, 'hits': {'demo': 27}})
    monkeypatch.setattr(skills, 'plugin_skills',
                        lambda cfgdir=None: [('demo@mkt', 'other', str(tmp_path / 'p'))])
    skills.write_skill(str(tmp_path / 'p'),
                       {'name': 'other', 'description': 'a different skill entirely'}, 'x')
    row = skills.inventory('', str(sb.cfg))['plugin'][0]
    assert row['sessions'] == 0 and row['via'] == ''


def test_the_two_reasons_a_skill_never_fires_are_flagged(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    skills.write_skill(os.path.join(_personal(sb), 'manual'),
                       {'name': 'manual', 'description': 'a perfectly good description here',
                        'disable-model-invocation': 'true'}, 'x')
    skills.write_skill(os.path.join(_personal(sb), 'thin'),
                       {'name': 'thin', 'description': 'stuff'}, 'x')
    rows = {r['command']: r for r in skills.inventory('', str(sb.cfg))['personal']}
    assert rows['manual']['auto'] is False, 'Claude may never load this on its own'
    assert rows['manual']['weak'] is False
    assert rows['thin']['auto'] is True and rows['thin']['weak'] is True


def test_a_folded_description_is_not_read_as_empty(tmp_path):
    """`description: >-` continues on the indented lines below it. Reading only
    the first line gave every plugin skill the description '>-', which the UI
    then reported as "thin description" — a warning about the parser."""
    d = str(tmp_path / 'folded')
    os.makedirs(d)
    with open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8') as f:
        f.write('---\nname: folded\ndescription: >-\n  Use when the task is long\n'
                '  and spans two lines.\n---\n\nbody\n')
    meta, _ = skills.parse_skill(d)
    assert meta['description'].startswith('Use when the task is long')
    assert skills._quality(meta) == (True, False)


def test_save_to_library_lands_where_claude_code_looks(monkeypatch, tmp_path):
    """The whole point of the rework: this used to write into a directory
    nothing reads, so "copy to library" looked like installing and did nothing."""
    sb = Sandbox(monkeypatch, tmp_path)
    src = os.path.join(skills.bundled_templates_dir(), 'test-writer')
    dest = skills.save_to_library(src, str(sb.cfg))
    assert dest.startswith(_personal(sb))
    assert os.path.isfile(os.path.join(dest, 'SKILL.md'))


# ── the one-time migration ───────────────────────────────────

def test_the_private_library_moves_into_every_account_once(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    legacy = tmp_path / 'archeus-skills'
    monkeypatch.setattr(config, 'skills_library_dir', str(legacy))
    skills.write_skill(os.path.join(str(legacy), 'token-economy'),
                       {'name': 'token-economy', 'description': 'terse'}, 'body')

    done = skills.migrate_library()
    assert done and os.path.isfile(
        os.path.join(_personal(sb), 'token-economy', 'SKILL.md'))
    # the source is NOT deleted: a migration that loses the only copy of
    # something the user wrote is not a migration
    assert os.path.isfile(os.path.join(str(legacy), 'token-economy', 'SKILL.md'))
    # and it runs once
    assert skills.migrate_library() == []


def test_the_migration_never_overwrites_a_personal_skill(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    legacy = tmp_path / 'archeus-skills'
    monkeypatch.setattr(config, 'skills_library_dir', str(legacy))
    skills.write_skill(os.path.join(str(legacy), 'x'), {'name': 'x'}, 'old')
    skills.write_skill(os.path.join(_personal(sb), 'x'), {'name': 'x'}, 'mine')
    skills.migrate_library()
    _meta, body = skills.parse_skill(os.path.join(_personal(sb), 'x'))
    assert 'mine' in body


def test_slug():
    assert skills._slug('Commit Message!') == 'commit-message'
    assert skills._slug('') == 'skill'


# ── TUI flow ─────────────────────────────────────────────────

def test_the_screen_names_every_scope(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    skills.write_skill(os.path.join(_personal(sb), 'commit-message'),
                       {'name': 'commit-message', 'description': 'commits'}, 'body')
    _usage(sb, {'commit-message': 3})
    cap = run_flow(monkeypatch, ESC, skills.skills_menu, None)[1]
    plain = cap.plain
    assert 'personal' in plain and 'built into Claude Code' in plain
    assert '/commit-message' in plain, 'the row must show the command you type'
    assert 'used 3x' in plain, 'usage is the answer to "am I using this?"'


def test_new_manual_lands_in_the_personal_scope(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    seq = typed('New skill (manual)')       # the menu filters as you type
    seq += ENTER
    seq += typed('note-taker') + ENTER      # name
    seq += typed('take notes') + ENTER      # description
    seq += ENTER                            # tools: none selected, confirm
    seq += ESC                              # leave menu
    run_flow(monkeypatch, seq, skills.skills_menu, None)
    d = os.path.join(_personal(sb), 'note-taker')
    assert os.path.isfile(os.path.join(d, 'SKILL.md'))
    meta, _ = skills.parse_skill(d)
    assert meta['name'] == 'note-taker'
