"""Plugins/marketplaces and the worktree board.

These are the two categories archeus was absent from. What is worth testing is
not the listing — that is a JSON read — but the two claims that justify building
them at all:

  · PROVENANCE: which flat-list row came from a bundle. Nothing else can say it,
    and a wrong answer is worse than none, because the action it informs is
    "delete this".
  · THE SESSION JOIN: which session is working in which worktree. Only a tool
    that owns both halves can make it, and it is the whole point of the board.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import plugins, worktrees


def _plugin_tree(tmp_path):
    """A plugins dir shaped like the real one on disk."""
    root = tmp_path / 'cfg' / 'plugins'
    (root / 'marketplaces' / 'mkt').mkdir(parents=True)
    cache = root / 'cache' / 'mkt' / 'demo' / '1.0'
    (cache / 'skills' / 'alpha').mkdir(parents=True)
    (cache / 'skills' / 'alpha' / 'SKILL.md').write_text('x', encoding='utf-8')
    (cache / 'agents').mkdir()
    (cache / 'agents' / 'helper.md').write_text('x', encoding='utf-8')
    (cache / 'agents' / 'README.md').write_text('x', encoding='utf-8')
    (cache / 'hooks').mkdir()
    (cache / 'hooks' / 'hooks.json').write_text('{}', encoding='utf-8')
    (cache / 'hooks' / 'package.json').write_text('{}', encoding='utf-8')
    (root / 'known_marketplaces.json').write_text(json.dumps({
        'mkt': {'source': {'source': 'github', 'repo': 'o/r'},
                'installLocation': str(root / 'marketplaces' / 'mkt'),
                'lastUpdated': '2026-01-01T00:00:00Z'}}), encoding='utf-8')
    (root / 'installed_plugins.json').write_text(json.dumps({
        'version': 2,
        'plugins': {'demo@mkt': [{'scope': 'user', 'installPath': str(cache),
                                  'version': '1.0', 'installedAt': 'x',
                                  'gitCommitSha': 'abc123'}]}}), encoding='utf-8')
    return str(tmp_path / 'cfg')


# ── plugins ───────────────────────────────────────────────────

def test_it_reads_the_format_that_is_actually_on_disk(tmp_path):
    """The docs describe a `marketplaces.json` this version does not write. The
    real files are known_marketplaces.json and installed_plugins.json."""
    cfg = _plugin_tree(tmp_path)
    mkts = plugins.known_marketplaces(cfg)
    assert [m['name'] for m in mkts] == ['mkt']
    assert mkts[0]['repo'] == 'o/r'
    inst = plugins.installed(cfg)
    assert len(inst) == 1
    assert inst[0]['name'] == 'demo' and inst[0]['marketplace'] == 'mkt'
    assert inst[0]['scope'] == 'user'


def test_provenance_maps_every_contributed_name_back_to_its_plugin(tmp_path):
    """THE reason this module exists. Without it the managers show a flat list
    and the obvious action on an unrecognised row — delete it — breaks a
    plugin."""
    cfg = _plugin_tree(tmp_path)
    idx = plugins.provenance_index(cfg)
    assert idx['skill']['alpha'] == 'demo@mkt'
    assert idx['agent']['helper'] == 'demo@mkt'
    assert idx['hook']['hooks'] == 'demo@mkt'


def test_packaging_files_are_not_reported_as_content(tmp_path):
    """README and package.json sit in those folders too. Labelling them as
    plugin content makes the index lie, and a wrong provenance label is worse
    than no label — it is the one thing this list must be trusted about."""
    cfg = _plugin_tree(tmp_path)
    idx = plugins.provenance_index(cfg)
    assert 'README' not in idx.get('agent', {}), idx
    assert 'package' not in idx.get('hook', {}), idx


def test_a_plugin_whose_files_vanished_is_flagged_not_hidden(tmp_path):
    """installed_plugins.json can outlive the cache. Silently dropping the row
    hides the reason a skill stopped working."""
    cfg = _plugin_tree(tmp_path)
    raw = json.loads((tmp_path / 'cfg' / 'plugins' / 'installed_plugins.json')
                     .read_text(encoding='utf-8'))
    raw['plugins']['demo@mkt'][0]['installPath'] = str(tmp_path / 'gone')
    (tmp_path / 'cfg' / 'plugins' / 'installed_plugins.json').write_text(
        json.dumps(raw), encoding='utf-8')
    s = plugins.summary(cfg)
    assert len(s['plugins']) == 1
    assert s['plugins'][0]['missing'] is True


def test_corrupt_state_files_do_not_crash_the_page(tmp_path):
    """These files belong to Claude Code and their shape has already changed
    once. A stale row beats a traceback."""
    root = tmp_path / 'cfg' / 'plugins'
    root.mkdir(parents=True)
    (root / 'known_marketplaces.json').write_text('{{{ not json', encoding='utf-8')
    (root / 'installed_plugins.json').write_text('[]', encoding='utf-8')
    assert plugins.known_marketplaces(str(tmp_path / 'cfg')) == []
    assert plugins.installed(str(tmp_path / 'cfg')) == []
    assert plugins.provenance_index(str(tmp_path / 'cfg')) == {}


def test_every_mutation_goes_through_the_one_cli_seam():
    """Not reimplemented, and not six copies of "find the binary" either. The
    CLI resolves sources, validates manifests and owns these caches; writing
    them directly would work until the format moved, which it already has. All
    six go through `_cli`, which is the only place a verb and a binary are
    chosen."""
    import inspect
    for fn in (plugins.add_marketplace, plugins.remove_marketplace,
               plugins.update_marketplaces, plugins.install_plugin,
               plugins.remove_plugin, plugins.update_plugin):
        src = inspect.getsource(fn)
        assert '_cli(' in src, fn.__name__
        assert 'get_claude_exe' not in src and 'proc.run' not in src, fn.__name__


def test_every_harness_with_plugins_has_the_verbs_for_them():
    """The capability table says which CLIs have marketplaces; PLUGIN_VERBS says
    what each one calls the operations. A harness in one and not the other is a
    page with no commands behind it, or commands reachable from no page."""
    from claude_sessions import harnesses as h
    for hid in h.ids():
        has_page = h.cap(hid, 'plugins')[0]
        assert has_page == (hid in plugins.PLUGIN_VERBS), hid
    # and the one asymmetry, which is a measurement and not an oversight:
    # Codex documents plugin add/list/remove and no per-plugin upgrade, so
    # archeus draws no Update button there rather than shelling out to a verb
    # that does not exist.
    assert 'update' in plugins.PLUGIN_VERBS['claude']
    assert 'update' not in plugins.PLUGIN_VERBS['codex']


def test_a_name_cannot_land_in_an_option_position(monkeypatch):
    """These take a free-text value from a box now. A value starting `-` is an
    option to the CLI whether or not a shell is involved — the same reasoning
    `add_marketplace` already applied to a git source."""
    called = []
    monkeypatch.setattr(plugins, '_run',
                        lambda *a, **k: (called.append(a) or (True, '')))
    for bad in ('-rf', '--json', '../x', 'a b', 'ext::sh -c id', ''):
        for fn in (plugins.install_plugin, plugins.remove_plugin,
                   plugins.update_plugin, plugins.remove_marketplace):
            ok, msg = fn(bad)
            assert ok is False and msg, (fn.__name__, bad)
    assert called == [], 'a rejected name still reached a subprocess'


def test_every_recommendation_can_actually_be_installed(tmp_path):
    """A recommendation whose marketplace archeus cannot add is a dead row: the
    install fails with "no such plugin" and the page offers no way out."""
    for hid, rows in plugins.RECOMMENDED.items():
        assert hid in plugins.PLUGIN_VERBS, hid
        for name, mkt, why in rows:
            assert mkt in plugins.RECOMMENDED_SOURCES, (name, mkt)
            assert why.endswith('.'), name
    cfg = _plugin_tree(tmp_path)
    got = {r['name']: r for r in plugins.recommendations(cfg)}
    assert got, 'the default harness must have a starting set'
    # nothing in the set is installed in this tree, and nothing claims to be
    assert not any(r['installed'] for r in got.values())
    assert not any(r['registered'] for r in got.values())
    assert all(r['source'] for r in got.values())


def test_a_recommendation_already_installed_says_so(tmp_path):
    """The flag is joined against what is on disk, not against the table — a
    curated row that says Install for something you already have is the one
    thing that makes the card untrustworthy."""
    cfg = _plugin_tree(tmp_path)
    name, mkt, _why = plugins.RECOMMENDED['claude'][0]
    root = tmp_path / 'cfg' / 'plugins'
    doc = json.loads((root / 'installed_plugins.json').read_text(encoding='utf-8'))
    doc['plugins']['%s@%s' % (name, mkt)] = [{'scope': 'user', 'version': '1'}]
    (root / 'installed_plugins.json').write_text(json.dumps(doc), encoding='utf-8')
    got = {r['name']: r for r in plugins.recommendations(cfg)}
    assert got[name]['installed'] is True
    assert sum(1 for r in got.values() if r['installed']) == 1


def test_plugin_install_is_reviewed_like_any_other_third_party_bundle():
    """A plugin ships agents and hooks into the auto-discovery surfaces — the
    same exposure as install_from_git, with more moving parts."""
    import inspect
    src = inspect.getsource(plugins.review_plugin)
    assert 'skillscan.review_gate' in src
    # and when there is nothing local to inspect it must SAY so, not imply a
    # check happened
    assert 'nothing could be inspected' in src


# ── worktrees ─────────────────────────────────────────────────

def test_porcelain_parsing_handles_every_worktree_shape(monkeypatch):
    out = ('worktree /repo\nHEAD abcdef1234\nbranch refs/heads/main\n\n'
           'worktree /repo/../wt-a\nHEAD 1234abcdef\nbranch refs/heads/feature/x\n\n'
           'worktree /repo/../wt-b\nHEAD deadbeef99\ndetached\n\n')
    monkeypatch.setattr(worktrees, '_git', lambda *a, **k: out)
    ts = worktrees.list_worktrees('/repo')
    assert len(ts) == 3
    assert ts[0]['main'] is True and ts[1]['main'] is False
    assert ts[1]['branch'] == 'feature/x'
    assert ts[2]['detached'] is True and ts[2]['branch'] == ''


def test_a_slash_branch_in_a_real_worktree_merges_by_its_whole_name(tmp_path):
    import subprocess

    def git(cwd, *a):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                       cwd=cwd, check=True, capture_output=True)
    repo, wt = tmp_path / 'repo', tmp_path / 'wt'
    repo.mkdir()
    git(repo, 'init', '-q', '-b', 'main')
    # the merge commit is made by the repo's own git, not by the -c of the helper above;
    # a repo-local identity keeps CI's identity-less git and the user's global config out of it
    git(repo, 'config', 'user.name', 't')
    git(repo, 'config', 'user.email', 't@t')
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'base')
    git(repo, 'worktree', 'add', '-q', '-b', 'feature/x', str(wt))
    (wt / 'f.txt').write_text('x')
    git(wt, 'add', 'f.txt')
    git(wt, 'commit', '-q', '-m', 'work')
    side = [t for t in worktrees.list_worktrees(str(repo)) if not t['main']][0]
    assert side['branch'] == 'feature/x'
    ok, msg = worktrees.merge_into_main(str(repo), side['branch'])
    assert ok, msg
    assert (repo / 'f.txt').exists()


def test_not_a_repo_is_an_empty_board_not_an_error(monkeypatch):
    monkeypatch.setattr(worktrees, '_git', lambda *a, **k: None)
    b = worktrees.board('/nope')
    assert b == {'worktrees': [], 'repo': False}


def test_the_board_joins_sessions_to_the_worktrees_they_run_in(monkeypatch):
    """The join nobody else can make: a transcript records its cwd, a worktree
    is a path. This is the whole point of the board."""
    monkeypatch.setattr(worktrees, '_git', lambda args, cwd, **k:
                        ('worktree /repo\nHEAD aaa\nbranch refs/heads/main\n\n'
                         'worktree /repo-wt\nHEAD bbb\nbranch refs/heads/side\n\n')
                        if args[:2] == ['worktree', 'list'] else '')
    import time
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {
        os.path.normcase(os.path.normpath('/repo-wt')): {
            'sid': 'deadbeef', 'mtime': time.time() - 30, 'account': 'work',
            'msgs': 12, 'branch': 'side', 'title': 'refactor', 'cfgdir': ''}})
    b = worktrees.board('/repo')
    side = [w for w in b['worktrees'] if w['name'].endswith('repo-wt')][0]
    assert side['session']['sid'] == 'deadbeef'
    assert side['session']['live'] is True
    assert side['session']['account'] == 'work'
    main = [w for w in b['worktrees'] if w['main']][0]
    assert main['session'] is None


def test_a_stale_session_is_not_live_in_its_worktree(monkeypatch):
    monkeypatch.setattr(worktrees, '_git', lambda args, cwd, **k:
                        'worktree /repo\nHEAD aaa\nbranch refs/heads/main\n\n'
                        if args[:2] == ['worktree', 'list'] else '')
    import time
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {
        os.path.normcase(os.path.normpath('/repo')): {
            'sid': 'x', 'mtime': time.time() - worktrees.LIVE_WINDOW * 3,
            'account': 'a', 'msgs': 1, 'branch': '', 'title': '', 'cfgdir': ''}})
    b = worktrees.board('/repo')
    assert b['worktrees'][0]['session']['live'] is False


def test_live_trees_sort_above_idle_ones(monkeypatch):
    """The board is for finding the one that needs you, not browsing dirs."""
    monkeypatch.setattr(worktrees, '_git', lambda args, cwd, **k:
                        ('worktree /repo\nHEAD a\nbranch refs/heads/main\n\n'
                         'worktree /wt-idle\nHEAD b\nbranch refs/heads/i\n\n'
                         'worktree /wt-live\nHEAD c\nbranch refs/heads/l\n\n')
                        if args[:2] == ['worktree', 'list'] else '')
    import time
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {
        os.path.normcase(os.path.normpath('/wt-live')): {
            'sid': 'l', 'mtime': time.time(), 'account': 'a', 'msgs': 1,
            'branch': '', 'title': '', 'cfgdir': ''}})
    names = [w['name'] for w in worktrees.board('/repo')['worktrees']]
    assert names[0].endswith('wt-live'), names
    assert names[-1] == 'repo', names          # the main tree goes last


# ── a project that is a PARENT of repos ───────────────────────

def _multi(monkeypatch, found, kinds=None):
    """Stub discovery + per-repo boards; no git, no session scan."""
    from claude_sessions import repos as _repos
    monkeypatch.setattr(_repos, 'find_git_repos', lambda root, **k: list(found))
    monkeypatch.setattr(_repos, 'classify',
                        lambda p: (kinds or {}).get(p, 'repo'))
    monkeypatch.setattr(_repos, 'remember', lambda measured: None)
    monkeypatch.setattr(_repos, 'state', lambda p, **k: {
        'branch': 'main', 'dirty': 0, 'ahead': 0, 'behind': 0,
        'head': 'aaaaaaa', 'stale': False})
    import claude_sessions.connections as conn
    monkeypatch.setattr(conn, '_discover_repos', lambda r, f: list(found))
    monkeypatch.setattr(worktrees, 'board', lambda p, f=None, by_cwd=None: {
        'repo': True, 'worktrees': [{
            'path': p, 'name': os.path.basename(p), 'branch': 'main',
            'head': 'aaaaaaa', 'main': True, 'dirty': 0, 'ahead': 0,
            'behind': 0, 'session': None}]})


def test_a_parent_directory_of_repos_is_not_an_empty_board(monkeypatch):
    """THE reported bug. D:/repos holds 15 repos and is not itself a repo, so
    `git worktree list` failed there and the tab said 'not a git repository'."""
    _multi(monkeypatch, [os.path.join('/p', 'a'), os.path.join('/p', 'b')])
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {})
    b = worktrees.project_board('/p')
    assert b['repo'] is True
    assert [r['name'] for r in b['repos']] == ['a', 'b'], b['repos']
    assert b['multi'] is True


def test_submodules_nest_under_the_repo_that_owns_them(monkeypatch):
    """IKM.Workspace carries seven. Flat, they read as unrelated projects."""
    top = os.path.join('/p', 'ws')
    sub = os.path.join(top, 'core')
    _multi(monkeypatch, [top, sub], {sub: 'submodule'})
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {})
    b = worktrees.project_board('/p')
    assert len(b['repos']) == 1, b['repos']
    assert [c['name'] for c in b['repos'][0]['children']] == ['core']
    assert b['repos'][0]['children'][0]['kind'] == 'submodule'


def test_a_single_repo_project_is_unchanged(monkeypatch):
    """D:/Claude must render exactly as it did before any of this."""
    _multi(monkeypatch, ['/only'])
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {})
    b = worktrees.project_board('/only')
    assert b['multi'] is False
    assert len(b['repos']) == 1 and b['repos'][0]['worktrees'][0]['main'] is True


def test_the_session_scan_runs_once_for_the_whole_project(monkeypatch):
    """It walks every transcript of every account. Per-repo it would dominate
    everything else on the page — 15 repos means 15 full scans."""
    _multi(monkeypatch, [f'/p/r{i}' for i in range(15)])
    calls = []
    monkeypatch.setattr(worktrees, '_sessions_by_cwd',
                        lambda p, f: calls.append(p) or {})
    worktrees.project_board('/p')
    assert len(calls) == 1, calls


def test_nothing_below_is_still_an_honest_empty(monkeypatch):
    from claude_sessions import repos as _repos
    monkeypatch.setattr(_repos, 'find_git_repos', lambda root, **k: [])
    import claude_sessions.connections as conn
    monkeypatch.setattr(conn, '_discover_repos', lambda r, f: [])
    assert worktrees.project_board('/nope')['repo'] is False


def test_removing_a_worktree_refuses_to_discard_uncommitted_work(monkeypatch):
    monkeypatch.setattr(worktrees, 'dirty', lambda p: (4, 0))
    called = []
    monkeypatch.setattr(worktrees, '_git', lambda *a, **k: called.append(a) or '')
    # '/wt' is absolute only on Windows up to 3.12: since 3.13 ntpath.isabs('/wt') is False,
    # so remove() would refuse for the wrong reason. An abspath is absolute on every version.
    ok, msg = worktrees.remove(os.path.abspath('wt'))
    assert ok is False and '4 uncommitted' in msg
    assert called == [], 'git ran despite the refusal'


def test_a_merge_is_gated_by_the_shared_confirm():
    """Same approval path as every other destructive write — the endpoint never
    decides on its own that a merge is a good idea."""
    import inspect
    from claude_sessions import gui_api
    src = inspect.getsource(gui_api.api_worktree_merge)
    assert 'diffview.confirm' in src
    assert src.index('diffview.confirm') < src.index('merge_into_main')


def test_the_board_does_not_parse_transcripts_to_list(monkeypatch):
    """It runs whenever the tab opens. Listing is git plus stat; parsing happens
    only when you open a session."""
    import inspect
    src = inspect.getsource(worktrees.board)
    for heavy in ('iter_transcript', 'extract_lessons', 'assemble_breakdown'):
        assert heavy not in src, heavy


# ── two worktrees changing the same files ─────────────────────

FULL = 'a' * 40


def _two_trees_git(monkeypatch, diffs, status, calls=None, extra_trees=()):
    """git as canned answers: the porcelain list, the main tree's full HEAD,
    `diff base...HEAD` per worktree path and `status --porcelain` per worktree path."""
    listing = ('worktree /repo\nHEAD aaaaaaaa11\nbranch refs/heads/main\n\n'
               'worktree /wt-a\nHEAD bbbbbbbb22\nbranch refs/heads/a\n\n'
               'worktree /wt-b\nHEAD cccccccc33\nbranch refs/heads/b\n\n'
               + ''.join(f'worktree {p}\nHEAD dddddddd44\nbranch refs/heads/x\n\n'
                         for p in extra_trees))

    diffs = {os.path.normpath(p): v for p, v in diffs.items()}
    status = {os.path.normpath(p): v for p, v in status.items()}

    def git(args, cwd, **k):
        cwd = os.path.normpath(cwd)
        plain = args[:2] == ['-c', 'core.quotepath=off']
        args = args[2:] if plain else args
        if calls is not None:
            calls.append((args[0], cwd))
        if args[:2] == ['worktree', 'list']:
            return listing
        if args[:2] == ['rev-parse', 'HEAD']:
            return FULL + '\n' if cwd == os.path.normpath('/repo') else None
        if args[0] == 'diff':
            assert plain and '--no-renames' in args and args[-1] == FULL + '...HEAD', args
            return diffs.get(cwd, '')
        if args[0] == 'status':
            assert plain and '-uall' in args, args
            return status.get(cwd, '')
        return ''
    monkeypatch.setattr(worktrees, '_git', git)
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {})


def _pair(b, x, y):
    return [o for o in b['overlaps'] if {os.path.basename(o['a']), os.path.basename(o['b'])} == {x, y}]


def test_two_worktrees_that_changed_the_same_file_are_flagged(monkeypatch):
    """The merge conflict is cheaper to avoid than to resolve: say so while both
    agents are still running. Committed and dirty files both count."""
    _two_trees_git(monkeypatch,
                   diffs={'/wt-a': 'src/x.py\nsrc/only_a.py\n'},
                   status={'/wt-b': ' M src/x.py\n?? notes.txt\n'})
    b = worktrees.board('/repo')
    [o] = b['overlaps']
    assert (o['count'], o['files']) == (1, ['src/x.py'])
    assert {os.path.basename(o['a']), os.path.basename(o['b'])} == {'wt-a', 'wt-b'}
    assert 'overlaps_skipped' not in b


def test_the_main_trees_own_dirty_files_count_but_it_has_no_base(monkeypatch):
    """Main is compared by its uncommitted files only: a diff of main against
    main would be empty, so the call is not made."""
    calls = []
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'a.py\n'}, status={'/repo': ' M a.py\n'},
                   calls=calls)
    b = worktrees.board('/repo')
    assert len(_pair(b, 'repo', 'wt-a')) == 1
    assert ('diff', os.path.normpath('/repo')) not in calls


def test_a_rename_counts_as_both_its_paths(monkeypatch):
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'new.py\n'},
                   status={'/wt-b': 'R  old.py -> new.py\n'})
    assert worktrees.board('/repo')['overlaps'][0]['files'] == ['new.py']
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'old.py\n'},
                   status={'/wt-b': 'R  old.py -> new.py\n'})
    assert worktrees.board('/repo')['overlaps'][0]['files'] == ['old.py']


def test_the_diff_base_is_the_full_sha_not_the_listings_abbreviation(monkeypatch):
    """An 8 character prefix can be ambiguous in a big repo, and git then fails."""
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'x.py\n'}, status={'/wt-b': ' M x.py\n'})
    real = worktrees._git
    monkeypatch.setattr(worktrees, '_git', lambda args, cwd, **k:
                        None if args[-1].endswith('...HEAD') and len(args[-1]) < 47
                        else real(args, cwd))
    assert len(worktrees.board('/repo')['overlaps']) == 1


def test_a_main_tree_git_cannot_name_leaves_the_committed_diff_out_not_the_board(monkeypatch):
    calls = []
    _two_trees_git(monkeypatch, diffs={}, calls=calls,
                   status={'/wt-a': ' M x.py\n', '/wt-b': ' M x.py\n'})
    real = worktrees._git
    monkeypatch.setattr(worktrees, '_git', lambda args, cwd, **k:
                        None if 'rev-parse' in args else real(args, cwd))
    b = worktrees.board('/repo')
    assert len(b['worktrees']) == 3 and len(b['overlaps']) == 1
    assert not [c for c in calls if c[0] == 'diff']


def test_only_five_shared_paths_are_listed_but_all_are_counted(monkeypatch):
    names = ''.join(f'f{i}.py\n' for i in range(9))
    _two_trees_git(monkeypatch, diffs={'/wt-a': names, '/wt-b': names}, status={})
    [o] = worktrees.board('/repo')['overlaps']
    assert o['count'] == 9 and o['files'] == [f'f{i}.py' for i in range(5)]


@pytest.mark.skipif(os.name != 'nt', reason='case folds only where the filesystem does')
def test_shared_files_are_compared_case_insensitively_on_windows(monkeypatch):
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'Src/A.py\n', '/wt-b': 'src/a.py\n'}, status={})
    [o] = worktrees.board('/repo')['overlaps']
    assert o['count'] == 1


def test_a_worktree_git_cannot_read_is_left_out_not_reported_clean_or_clashing(monkeypatch):
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'x.py\n', '/wt-b': None},
                   status={'/wt-b': ' M x.py\n'})
    assert worktrees.board('/repo')['overlaps'] == []


def test_too_many_worktrees_skips_the_check_and_says_so(monkeypatch):
    calls = []
    extra = [f'/x{i}' for i in range(worktrees.OVERLAP_MAX_TREES)]
    _two_trees_git(monkeypatch, diffs={}, status={}, calls=calls, extra_trees=extra)
    b = worktrees.board('/repo')
    assert b['overlaps'] == [] and b['overlaps_skipped'] is True
    assert not [c for c in calls if c[0] == 'diff']


def test_exactly_the_limit_of_worktrees_is_still_checked(monkeypatch):
    calls = []
    extra = [f'/x{i}' for i in range(worktrees.OVERLAP_MAX_TREES - 3)]
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'x.py\n', '/wt-b': 'x.py\n'}, status={},
                   calls=calls, extra_trees=extra)
    b = worktrees.board('/repo')
    assert len(b['worktrees']) == worktrees.OVERLAP_MAX_TREES
    assert len(b['overlaps']) == 1 and 'overlaps_skipped' not in b
    assert [c for c in calls if c[0] == 'diff']


def test_a_status_git_cannot_read_leaves_the_tree_out_without_raising(monkeypatch):
    _two_trees_git(monkeypatch, diffs={'/wt-a': 'x.py\n', '/wt-b': 'x.py\n'},
                   status={'/wt-b': None})
    b = worktrees.board('/repo')
    assert b['overlaps'] == [] and 'overlaps_skipped' not in b
    assert next(w for w in b['worktrees'] if w['name'] == 'wt-b')['dirty'] == 0


def _repo_with_two_trees(tmp_path, bare=False):
    """A real repo (or a bare one) with a committed `old.py` and linked worktrees
    wt-a and wt-b: (git, repo, [wt-a, wt-b])."""
    import subprocess

    def git(cwd, *a):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                       cwd=cwd, check=True, capture_output=True)
    src = tmp_path / 'src'
    src.mkdir()
    git(src, 'init', '-q', '-b', 'main')
    (src / 'old.py').write_text('x')
    git(src, 'add', '.')
    git(src, 'commit', '-q', '-m', 'base')
    repo = src
    if bare:
        repo = tmp_path / 'repo.git'
        git(tmp_path, 'clone', '-q', '--bare', str(src), str(repo))
    wts = [tmp_path / 'wt-a', tmp_path / 'wt-b']
    for wt in wts:
        git(repo, 'worktree', 'add', '-q', '-b', wt.name, str(wt))
    return git, repo, wts


def _shared(b):
    return {f.replace('\\', '/') for o in b['overlaps'] for f in o['files']}


def test_a_bare_main_repo_still_gets_the_committed_overlaps(tmp_path):
    git, repo, (a, b) = _repo_with_two_trees(tmp_path, bare=True)
    for wt in (a, b):
        (wt / 'x.py').write_text(wt.name)
        git(wt, 'add', '.')
        git(wt, 'commit', '-q', '-m', 'x')
    got = worktrees.board(str(repo))
    assert {w['name'] for w in got['worktrees']} == {'wt-a', 'wt-b'}
    assert _shared(got) == {'x.py'} and 'overlaps_skipped' not in got


def test_an_untracked_directory_overlaps_the_file_another_tree_committed_in_it(tmp_path):
    git, repo, (a, b) = _repo_with_two_trees(tmp_path)
    (b / 'newdir').mkdir()
    (b / 'newdir' / 'x.py').write_text('b')
    git(b, 'add', '.')
    git(b, 'commit', '-q', '-m', 'x')
    (a / 'newdir').mkdir()
    (a / 'newdir' / 'x.py').write_text('a')
    assert _shared(worktrees.board(str(repo))) == {'newdir/x.py'}


def test_a_non_ascii_path_matches_between_status_and_diff(tmp_path):
    git, repo, (a, b) = _repo_with_two_trees(tmp_path)
    (a / 'café.py').write_text('a')
    git(a, 'add', '.')
    git(a, 'commit', '-q', '-m', 'x')
    (b / 'café.py').write_text('b')
    assert _shared(worktrees.board(str(repo))) == {'café.py'}


def test_a_rename_in_one_tree_overlaps_a_delete_in_another(tmp_path):
    git, repo, (a, b) = _repo_with_two_trees(tmp_path)
    git(a, 'mv', 'old.py', 'new.py')
    git(a, 'commit', '-q', '-m', 'rename')
    git(b, 'rm', '-q', 'old.py')
    assert _shared(worktrees.board(str(repo))) == {'old.py'}


def test_the_overlaps_reach_the_project_board(monkeypatch):
    _multi(monkeypatch, ['/only'])
    monkeypatch.setattr(worktrees, '_sessions_by_cwd', lambda p, f: {})
    monkeypatch.setattr(worktrees, 'board', lambda p, f=None, by_cwd=None: {
        'repo': True, 'overlaps': [{'a': '/a', 'b': '/b', 'count': 2, 'files': ['x', 'y']}],
        'worktrees': [{'path': p, 'name': 'only', 'branch': 'main', 'head': 'a',
                       'main': True, 'dirty': 0, 'ahead': 0, 'behind': 0, 'session': None}]})
    assert worktrees.project_board('/only')['repos'][0]['overlaps'][0]['count'] == 2
