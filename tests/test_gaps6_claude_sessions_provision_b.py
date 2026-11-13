"""T-1275: claude_sessions/provision.py:201-286 at 6bbd3b44 (provision review gates every mutation and preserves foreign state).

Selected candidates, not measured coverage. Ranked, with the closest existing test:
1  245 declined plugin review installs nothing     tests/test_gaps6_claude_sessions_provision_a.py covers diff() only, not apply()
2  232 kinds left out get no review, copy or read  none
3  236 missing marketplace source is a failure     none
4  215 source is the fresh re-read, not the diff   tests/test_multihome.py covers discovery, not apply()
5  256 present hook not appended, foreign kept     tests/test_surface_parity.py:148 checks hook reader states only
6  260 hook save False is a failure                none
7  271 agent copy OSError is per item              none
8  278 skill install failure has no fallback copy  none
9  281 existing CLAUDE.md not overwritten (strict xfail)
10 283 explicit target path, failure propagated    none

Branch each test catches: 245 (review gate), 232 (kinds filter), 236 (source guard), 215 (state
re-read), 256 (already-present skip), 260 (save result), 271 (OSError handler), 278 (skill
result), 281 (claude_md write guard, xfail), 283 (target path and write result).
"""

import copy
import os
import shutil
from types import SimpleNamespace

import pytest

from claude_sessions import config as _c
from claude_sessions import hooks, plugins, skills, statusline
from claude_sessions import provision as p


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = SimpleNamespace(states={}, settings={}, saves=[], save_ok=True, installs=[],
                        markets=[], skills=[], skill_ok=True, skill_default=None, copies=[],
                        copy_fail=set(), copytrees=[], statusline=[], md_writes=[], md_ok=True)

    def state(name, cfgdir, **kw):
        base = {'name': name, 'dir': cfgdir, 'marketplaces': {}, 'plugins': set(), 'hooks': {},
                'n_hooks': 0, 'agents': {}, 'skills': {}, 'statusline': False,
                'claude_md': False, 'claude_md_path': ''}
        base.update(kw)
        w.states[cfgdir] = base

    def add_marketplace(source, cfgdir=None):
        w.markets.append((source, cfgdir))
        return True, 'ok'

    def install_plugin(name, marketplace='', cfgdir=None):
        w.installs.append((name, marketplace, cfgdir))
        return True, 'ok'

    def install_statusline(cfgdir=None):
        w.statusline.append(cfgdir)
        return True, 'statusline ok'

    def install_skill(src_dir, dest_root):
        w.skills.append((src_dir, dest_root))
        return os.path.join(dest_root, os.path.basename(src_dir)) if w.skill_ok else ''

    def copyfile(src, dst):
        w.copies.append((src, dst))
        if os.path.basename(src) in w.copy_fail:
            raise OSError('synthetic-denied')

    def write_atomic(path, text, mode=None):
        w.md_writes.append((path, text))
        return w.md_ok

    def save(d, cfgdir=None):
        w.saves.append((cfgdir, copy.deepcopy(d)))
        return w.save_ok

    w.state = state
    monkeypatch.setattr(hooks, 'account_dirs',
                        lambda: [(s['name'], s['dir']) for s in w.states.values()])
    monkeypatch.setattr(p, '_state', lambda name, cfgdir: w.states[cfgdir])
    monkeypatch.setattr(hooks, '_load', lambda cfgdir=None: copy.deepcopy(w.settings.get(cfgdir, {})))
    monkeypatch.setattr(hooks, '_save', save)
    monkeypatch.setattr(plugins, 'add_marketplace', add_marketplace)
    monkeypatch.setattr(plugins, 'install_plugin', install_plugin)
    monkeypatch.setattr(statusline, 'install', install_statusline)
    monkeypatch.setattr(skills, 'install_skill', install_skill)
    monkeypatch.setattr(shutil, 'copyfile', copyfile)
    monkeypatch.setattr(shutil, 'copytree', lambda *a, **k: w.copytrees.append(a))
    monkeypatch.setattr(_c, 'write_atomic', write_atomic)
    monkeypatch.setattr(_c, 'config_dir', str(tmp_path / 'default-home'))
    return w


def row(name, cfgdir, have_md=False, **missing):
    m = {'marketplaces': [], 'plugins': [], 'hooks': [], 'statusline': False,
         'agents': [], 'skills': [], 'claude_md': False}
    m.update(missing)
    return {'name': name, 'dir': cfgdir, 'have': {'claude_md': have_md}, 'missing': m, 'todo': 1}


def diff_of(*rows, sources=None):
    return {'accounts': list(rows), 'clean': False, 'plugin_sources': sources or {}}


def test_declined_review_skips_only_that_plugin(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    d = diff_of(row('acct', acct, plugins=['p1@m', 'p2@m']), sources={'p1@m': 'm', 'p2@m': 'm'})
    reviews = []

    def review(name, mkt):
        reviews.append((name, mkt))
        return name != 'p1'

    done = p.apply(d=d, review=review)
    assert reviews == [('p1', 'm'), ('p2', 'm')]
    assert world.installs == [('p2', 'm', acct)]
    assert done == [('acct', 'plugins', 'p1@m (review declined)', False),
                    ('acct', 'plugins', 'p2@m', True)]


def test_kinds_left_out_are_never_reviewed_installed_or_read(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    world.state('src', str(tmp_path / 'src'), marketplaces={'m': {'repo': 'acme/m'}},
                agents={'a.md': '/src/a.md'}, skills={'s': '/src/s'})
    d = diff_of(row('acct', acct, marketplaces=['m'], plugins=['p@m'], agents=['a.md'],
                    skills=['s'], statusline=True), sources={'p@m': 'm'})
    reviews = []
    done = p.apply(d=d, kinds=('marketplaces',),
                   review=lambda name, mkt: reviews.append(name) or True)
    assert world.markets == [('acme/m', acct)]
    assert reviews == [] and world.installs == []
    assert world.copies == [] and world.skills == [] and world.statusline == []
    assert [(n, k) for n, k, _, _ in done] == [('acct', 'marketplaces')]


def test_missing_marketplace_source_is_recorded_not_invented(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    world.state('src', str(tmp_path / 'src'),
                marketplaces={'m': {}, 'n': {'repo': '', 'source': ''}, 'k': {'repo': 'acme/k'}})
    done = p.apply(d=diff_of(row('acct', acct, marketplaces=['m', 'n', 'k'])))
    assert world.markets == [('acme/k', acct)]
    assert done == [('acct', 'marketplaces', 'm (no source recorded)', False),
                    ('acct', 'marketplaces', 'n (no source recorded)', False),
                    ('acct', 'marketplaces', 'k', True)]


def test_agent_source_is_the_fresh_reread_not_the_diff(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    world.state('src', str(tmp_path / 'src'), agents={'a.md': '/fresh/a.md'})
    done = p.apply(d=diff_of(row('acct', acct, agents=['a.md'])))
    assert world.copies == [('/fresh/a.md', os.path.join(acct, 'agents', 'a.md'))]
    assert done == [('acct', 'agents', 'a.md', True)]


def test_vanished_agent_source_is_a_recorded_failure(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    world.state('src', str(tmp_path / 'src'), agents={})
    done = p.apply(d=diff_of(row('acct', acct, agents=['gone.md'])))
    assert [(n, k, ok) for n, k, _, ok in done] == [('acct', 'agents', False)]
    assert world.copies == []


def test_hook_already_present_is_not_appended_and_foreign_settings_survive(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    guard = {'hooks': [{'type': 'command', 'command': 'guard.py'}]}
    stop = {'hooks': [{'type': 'command', 'command': 'notify.py'}]}
    mine = {'hooks': [{'type': 'command', 'command': 'mine.sh'}]}
    world.settings[acct] = {'permissions': {'allow': ['Bash(ls)']},
                            'hooks': {'PreToolUse': [guard, mine]}}
    world.state('src', str(tmp_path / 'src'),
                hooks={('PreToolUse', ('guard.py',)): guard, ('Stop', ('notify.py',)): stop})
    done = p.apply(d=diff_of(row('acct', acct, hooks=['x'])))
    (cfgdir, saved), = world.saves
    assert cfgdir == acct
    assert saved == {'permissions': {'allow': ['Bash(ls)']},
                     'hooks': {'PreToolUse': [guard, mine], 'Stop': [stop]}}
    assert done == [('acct', 'hooks', '1 hook(s)', True)]


def test_hook_save_failure_is_reported_and_nothing_to_add_saves_nothing(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    entry = {'hooks': [{'type': 'command', 'command': 'n.py'}]}
    world.state('src', str(tmp_path / 'src'), hooks={('Stop', ('n.py',)): entry})
    world.save_ok = False
    seen = []
    done = p.apply(d=diff_of(row('acct', acct, hooks=['x'])),
                   progress=lambda *a: seen.append(a))
    assert done == [('acct', 'hooks', '1 hook(s)', False)] and seen == done

    world.saves.clear()
    world.save_ok = True
    world.settings[acct] = {'hooks': {'Stop': [entry]}}
    done = p.apply(d=diff_of(row('acct', acct, hooks=['x'])))
    assert done == [('acct', 'hooks', '0 hook(s)', True)]
    assert world.saves == []


def test_agent_copy_failure_is_per_item_and_lands_in_the_selected_account(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    world.state('src', str(tmp_path / 'src'), agents={'a.md': '/src/a.md', 'b.md': '/src/b.md'})
    world.copy_fail = {'a.md'}
    done = p.apply(d=diff_of(row('acct', acct, agents=['a.md', 'b.md'])))
    assert done == [('acct', 'agents', 'a.md: synthetic-denied', False),
                    ('acct', 'agents', 'b.md', True)]
    assert world.copies == [('/src/a.md', os.path.join(acct, 'agents', 'a.md')),
                            ('/src/b.md', os.path.join(acct, 'agents', 'b.md'))]


def test_failed_skill_install_is_recorded_and_never_copied_elsewhere(world, tmp_path):
    acct = str(tmp_path / 'acct')
    world.state('acct', acct)
    world.state('src', str(tmp_path / 'src'), skills={'s': '/src/skills/s'})
    world.skill_ok = False
    done = p.apply(d=diff_of(row('acct', acct, skills=['s'])))
    assert done == [('acct', 'skills', 's: copy failed', False)]
    assert world.skills == [('/src/skills/s', os.path.join(acct, 'skills'))]
    assert world.copies == [] and world.copytrees == []
    assert not os.path.exists(tmp_path / 'default-home')


def test_missing_claude_md_is_copied_from_the_union_into_the_selected_account(world, tmp_path):
    acct = str(tmp_path / 'acct')
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'CLAUDE.md').write_bytes(b'global\n')
    world.state('acct', acct)
    world.state('src', str(src), claude_md=True)
    done = p.apply(d=diff_of(row('acct', acct, claude_md=True), row('src', str(src), have_md=True)))
    assert world.md_writes == [(os.path.join(acct, 'CLAUDE.md'), 'global\n')]
    assert done == [('acct', 'claude_md', 'CLAUDE.md', True)]


def test_stale_missing_flag_does_not_overwrite_an_existing_claude_md(world, tmp_path):
    acct = tmp_path / 'acct'
    acct.mkdir()
    (acct / 'CLAUDE.md').write_bytes(b'mine\n')
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'CLAUDE.md').write_bytes(b'global\n')
    world.state('acct', str(acct), claude_md=True)
    world.state('src', str(src), claude_md=True)
    p.apply(d=diff_of(row('acct', str(acct), claude_md=True), row('src', str(src), have_md=True)))
    assert world.md_writes == []


def test_claude_md_targets_the_selected_account_and_failure_propagates(world, tmp_path):
    target = str(tmp_path / 'target')
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'CLAUDE.md').write_bytes(b'global\n')
    world.state('target', target)
    world.state('src', str(src), claude_md=True)
    world.md_ok = False
    done = p.apply(d=diff_of(row('target', target, claude_md=True),
                             row('src', str(src), have_md=True)))
    assert world.md_writes == [(os.path.join(target, 'CLAUDE.md'), 'global\n')]
    assert done == [('target', 'claude_md', 'CLAUDE.md', False)]
    assert not any(path.startswith(str(src)) for path, _ in world.md_writes)
