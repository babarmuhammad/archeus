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


def test_mutations_go_through_the_claude_cli():
    """Not reimplemented. Claude Code resolves sources, validates manifests and
    owns these caches; writing them directly would work until the format moved,
    which it already has."""
    import inspect
    for fn in (plugins.add_marketplace, plugins.remove_marketplace,
               plugins.install_plugin, plugins.remove_plugin):
        assert '_claude_cli' in inspect.getsource(fn), fn.__name__


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
    # a slashed branch keeps only its leaf, and detached is not a branch
    assert ts[1]['branch'] == 'x'
    assert ts[2]['detached'] is True and ts[2]['branch'] == ''


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
    ok, msg = worktrees.remove('/wt')
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
