"""T-320: the highest-risk uncovered branches of `archeus/harnesses/sources.py`.

Style and fixtures follow `tests/v1/unit/test_settings_sources_units.py`, the
closest existing test of this module: an account home, a project workdir and a
managed settings file under `tmp_path`, every read done against real files and
every OS call the module makes faked only at a seam the existing tests already
use (`config.write_atomic`, `os.path.realpath`, the module's own `plugin_dir`).
No process, no network, no sleep, nothing that needs one platform over the
other: where a branch is only reachable on Windows it is reached here by
faking the one call that decides it, so both reviewers run the same test.

The emphasis is the fail-closed and denial path of each branch, then its
boundary value, then its error path: a settings file that cannot be read must
never mean "load it", a plugin whose directory is not the account's must never
reach the argv, and a record that cannot be written must never be followed by a
spawn. Each test names in the card's report the source branch whose removal or
inversion it would catch.
"""

import hashlib
import json
import os

import pytest

from archeus.harnesses import base, sources
from archeus.infra.paths import MCP_CONFIG


def _writeb(path, data):
    """Raw bytes, with the newlines the test chose and never the platform's."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _write(path, obj):
    _writeb(path, obj if isinstance(obj, (bytes, bytearray)) else
            json.dumps(obj, indent=1).encode('utf-8'))


def _hooks(cmd):
    return {'PreToolUse': [{'matcher': '*', 'hooks': [{'type': 'command', 'command': cmd}]}]}


def _plugin_tree(root, *, manifest=None, skills=('pskill',), hooks=None, mcp=None):
    """A plugin directory as Claude Code installs one: its manifest, its
    `skills/<name>/SKILL.md`, its `hooks/hooks.json`, its own `.mcp.json`."""
    _write(os.path.join(root, '.claude-plugin', 'plugin.json'), manifest or {'name': 'pl'})
    for s in skills:
        _write(os.path.join(root, 'skills', s, 'SKILL.md'),
               b'---\nname: ' + s.encode('utf-8') + b'\n---\nbody\n')
    if hooks is not None:
        _write(os.path.join(root, 'hooks', 'hooks.json'), hooks)
    if mcp is not None:
        _write(os.path.join(root, '.mcp.json'), mcp)
    return root


def _installed(home, entries, *, name='pl@m', version=2):
    """The account home's `plugins/installed_plugins.json`, written verbatim."""
    _write(os.path.join(home, 'plugins', 'installed_plugins.json'),
           {'version': version, 'plugins': {name: entries}})


@pytest.fixture
def world(tmp_path):
    """An account home and a workdir with something in every place ADR-0049
    names, one installed plugin and a managed settings file: the same shape as
    `test_settings_sources_units.world`, kept small so each test changes one
    thing."""
    home, work = str(tmp_path / 'home'), str(tmp_path / 'proj')
    _write(os.path.join(home, 'settings.json'), {
        'hooks': _hooks('user-hook.sh'), 'enabledPlugins': {'pl@m': True},
        'permissions': {'allow': ['Bash(npm test)']}})
    _write(os.path.join(home, '.claude.json'), {'mcpServers': {
        'gh': {'command': 'gh-mcp', 'env': {'TOKEN': 'never-recorded'}}}})
    _write(os.path.join(home, 'CLAUDE.md'), b'user memory\n')
    _write(os.path.join(home, 'skills', 'uskill', 'SKILL.md'), b'x\n')
    _plugin_tree(os.path.join(home, 'plugins', 'pl', '1'),
                 hooks={'hooks': _hooks('plugin-hook.sh')},
                 mcp={'mcpServers': {'plugin-mcp': {'command': 'x'}}})
    _installed(home, [{'installPath': os.path.join(home, 'plugins', 'pl', '1')}])
    _write(os.path.join(work, '.claude', 'settings.json'), {
        'hooks': _hooks('project-hook.sh'), 'permissions': {'deny': ['Read(.env)']}})
    _write(os.path.join(work, '.claude', 'settings.local.json'), {'hooks': _hooks('local.sh')})
    _write(os.path.join(work, '.mcp.json'), {'mcpServers': {'db': {'command': 'db-mcp'}}})
    _write(os.path.join(work, 'CLAUDE.md'), b'project memory\n')
    _write(os.path.join(work, '.claude', 'skills', 'pjskill', 'SKILL.md'), b'x\n')
    managed = os.path.join(str(tmp_path), 'managed', 'managed-settings.json')
    _write(managed, {'hooks': _hooks('managed.sh')})
    return home, work, managed


def take(world, *opt_ins, **kw):
    home, work, managed = world
    kw.setdefault('managed', managed)
    return sources.take(home, work, opt_ins, **kw)


def items(inv, **eq):
    return [i for i in inv['items'] if all(i.get(k) == v for k, v in eq.items())]


def argv(world, inv, exec_dir, *, home=..., workdir=...):
    return sources.flag_argv(inv['flags'],
                             home=world[0] if home is ... else home,
                             workdir=world[1] if workdir is ... else workdir,
                             exec_dir=str(exec_dir))


def plugin_items(inv, name='pl@m', source='plugin'):
    """The record's entry for plugin *name* as loaded from its own directory
    (sources.py:309-313); the settings entry that merely enables it is recorded
    under its setting source instead (sources.py:293-296)."""
    return [i for i in inv['items'] if i['type'] == 'plugin' and i['name'] == name
            and i['source'] == source]


def _servers(owner, *names):
    return [{'owner': owner, 'name': n} for n in names]


# ── the spawn's own write, and what may never reach the argv ─────────────────

def test_g01_an_mcp_config_that_cannot_be_written_refuses_the_spawn(world, tmp_path,
                                                                    monkeypatch):
    """sources.py:394-396: no file, no spawn. The refusal is the charged
    `SpawnWriteFailed` the spawn's other writes are, never an OSError out of the
    manager's tick, and nothing is left behind for Claude Code to half-read."""
    inv = take(world, ('account', 'mcp', 'gh'))
    assert inv['flags']['mcp_servers'] == [{'owner': 'account', 'name': 'gh'}]
    a = argv(world, inv, tmp_path / 'exec-ok')
    cfg = json.load(open(a[a.index('--mcp-config') + 1], encoding='utf-8'))
    assert sorted(cfg['mcpServers']) == ['gh']
    # the same flags with a Core that cannot write: nothing spawned, nothing left
    bad = tmp_path / 'exec-bad'
    monkeypatch.setattr(sources.config, 'write_atomic', lambda *args, **kw: False)
    with pytest.raises(base.SpawnWriteFailed) as got:
        sources.flag_argv(inv['flags'], home=world[0], workdir=world[1], exec_dir=str(bad))
    assert isinstance(got.value, base.SpawnFailed)
    assert str(os.path.join(str(bad), MCP_CONFIG)) in str(got.value)
    assert not (bad / MCP_CONFIG).exists()


def test_g02_a_plugin_dir_that_merely_shares_the_plugins_prefix_is_never_passed(
        world, tmp_path):
    """sources.py:108-111 with 184: an `installPath` outside the home's plugins
    directory is not a plugin of this account. The sibling is named
    `<plugins>-evil`, so a `str.startswith` in place of `os.path.commonpath`
    would let it through, its skills and its hooks recorded as loaded."""
    home = world[0]
    root = os.path.join(home, 'plugins')
    evil = _plugin_tree(root + '-evil', skills=('evilskill',))
    _installed(home, [{'installPath': evil}])
    assert sources.plugin_dir(home, 'pl@m') is None
    inv = take(world, ('account', 'plugin', 'pl@m'))
    assert [i['status'] for i in plugin_items(inv)] == ['not_found']
    assert [d['path'] for d in inv['flags']['plugin_dirs']] == [None]
    a = argv(world, inv, tmp_path / 'exec')
    assert '--plugin-dir' not in a and not [x for x in a if x.startswith(evil)]
    assert 'evilskill' not in {i['name'] for i in items(inv, type='skill')}


def test_g03_a_relative_install_path_is_never_a_plugin_of_this_account(world, tmp_path,
                                                                       monkeypatch):
    """sources.py:183-186: a hostile `installed_plugins.json` naming a relative
    path must not make the spawn load whatever sits in the *current directory*
    under that name."""
    home = world[0]
    elsewhere = _plugin_tree(str(tmp_path / 'cwd-plugin'), skills=('cwdskill',))
    _installed(home, [{'installPath': os.path.basename(elsewhere)}])
    monkeypatch.chdir(tmp_path)                    # the relative path resolves from here
    assert sources.plugin_dir(home, 'pl@m') is None
    inv = take(world, ('account', 'plugin', 'pl@m'))
    assert 'cwdskill' not in {i['name'] for i in items(inv, type='skill')}
    assert [d['path'] for d in inv['flags']['plugin_dirs']] == [None]


def test_g04_a_plugin_on_a_volume_that_cannot_be_compared_is_not_loaded(world, monkeypatch):
    """sources.py:112-113: `_inside` fails closed when the two paths have no
    common root - the case `os.path.commonpath` raises `ValueError` for, which is
    a second drive on Windows. `realpath` is faked to name that other volume, so
    the branch is covered on Linux too; either way the plugin is not loaded."""
    home = world[0]
    good = os.path.join(home, 'plugins', 'pl', '1')
    real = os.path.realpath
    assert sources.plugin_dir(home, 'pl@m') == real(good)          # the real thing loads it
    monkeypatch.setattr(os.path, 'realpath',
                        lambda p, *a, **k: real(p, *a, **k) if p != good
                        else os.path.join('d:', 'other', 'pl'))
    assert sources.plugin_dir(home, 'pl@m') is None
    inv = take(world, ('account', 'plugin', 'pl@m'))
    assert [i['status'] for i in plugin_items(inv)] == ['not_found']
    assert [d['path'] for d in inv['flags']['plugin_dirs']] == [None]


@pytest.mark.parametrize('shape', ['version1', 'noversion', 'noplugins', 'notdict',
                                   'notjson', 'absent'],
                         ids=('version1', 'noversion', 'noplugins', 'notdict', 'notjson',
                              'absent'))
def test_g05_an_installed_plugins_manifest_archeus_does_not_read_loads_nothing(world, tmp_path,
                                                                               shape):
    """sources.py:180: only format 2 with a `plugins` object names a plugin. Every
    other shape is no plugin at all - never a partial read of a file Claude Code
    itself would read differently, and never a crash out of `take`."""
    home = world[0]
    good = os.path.join(home, 'plugins', 'pl', '1')
    path = os.path.join(home, 'plugins', 'installed_plugins.json')
    if shape == 'version1':
        _write(path, {'version': 1, 'plugins': {'pl@m': [{'installPath': good}]}})
    elif shape == 'noversion':
        _write(path, {'plugins': {'pl@m': [{'installPath': good}]}})
    elif shape == 'noplugins':
        _write(path, {'version': 2})
    elif shape == 'notdict':
        _write(path, {'version': 2, 'plugins': [good]})
    elif shape == 'notjson':
        _write(path, b'{not json')
    elif shape == 'absent':
        os.remove(path)
    assert sources.plugin_dir(home, 'pl@m') is None
    inv = take(world, ('account', 'plugin', 'pl@m'))
    assert [i['status'] for i in plugin_items(inv)] == ['not_found']
    assert [d['path'] for d in inv['flags']['plugin_dirs']] == [None]
    assert '--plugin-dir' not in argv(world, inv, tmp_path / 'exec')


def test_g06_a_hostile_entry_list_is_skipped_and_the_next_valid_entry_is_found(world):
    """sources.py:182-186: an entry that is not an object, an `installPath` that is
    not a string or not a directory, and a path outside the plugins root are each
    skipped - and a junk entry must neither hide the good entry beside it nor
    raise out of `take` and stop every execution of the pass."""
    home = world[0]
    good = os.path.join(home, 'plugins', 'pl', '1')
    root = os.path.join(home, 'plugins')
    _installed(home, ['a string', 42, None, {'installPath': 42}, {'installPath': root + '-evil'},
                      {'installPath': os.path.join(root, 'gone')}, {'installPath': good}])
    assert sources.plugin_dir(home, 'pl@m') == os.path.realpath(good)
    inv = take(world, ('account', 'plugin', 'pl@m'))
    assert [i['status'] for i in plugin_items(inv)] == ['opted_in']
    assert inv['flags']['plugin_dirs'][0]['path'] == os.path.realpath(good)
    # and when no entry is usable there is no plugin: not a crash, not a guess
    _installed(home, ['a string', {'installPath': 42}, {'installPath': root + '-evil'}])
    assert sources.plugin_dir(home, 'pl@m') is None
    assert [d['path'] for d in take(world, ('account', 'plugin', 'pl@m'))['flags'][
        'plugin_dirs']] == [None]


def test_g07_an_unreadable_mcp_file_never_admits_a_server(world, tmp_path):
    """sources.py:166-169 with 320-328: a `.claude.json` that is not a JSON object
    and a `.mcp.json` whose `mcpServers` is not an object name no server at all;
    the unreadable one is said with its error and stays `excluded`, the server its
    owner opted in is `not_found`, and no `--mcp-config` is written for it."""
    home, work, _m = world
    _write(os.path.join(home, '.claude.json'), b'[1, 2]')
    _write(os.path.join(work, '.mcp.json'), {'mcpServers': 'db'})
    inv = take(world, ('account', 'mcp', 'gh'), ('project', 'mcp', 'db'))
    (u,) = items(inv, type='unreadable', source='user')
    assert (u['status'], u['error'], u['name']) == ('excluded', 'not a JSON object',
                                                    '.claude.json')
    assert not items(inv, type='unreadable', source='project')
    assert {(i['source'], i['name'], i['status']) for i in items(inv, type='mcp_server')} == {
        ('user', 'gh', 'not_found'), ('project', 'db', 'not_found'),
        ('plugin:pl@m', 'plugin-mcp', 'excluded')}          # the plugin's own: never in
    assert inv['flags']['mcp_servers'] == []
    exec_dir = tmp_path / 'exec'
    assert '--mcp-config' not in argv(world, inv, exec_dir)
    assert not (exec_dir / MCP_CONFIG).exists()


def test_g08_the_mcp_config_holds_only_definitions_that_exist_and_are_objects(world):
    """sources.py:374-381: a definition that is not an object never reaches the
    file Claude Code reads, a name the *first* owner brought keeps that owner's
    definition rather than being silently redefined by the second, and an owner
    with no home or workdir contributes nothing."""
    home, work, _m = world
    assert sources.mcp_config(home, work, _servers('account', 'gh')) == {
        'mcpServers': {'gh': {'command': 'gh-mcp', 'env': {'TOKEN': 'never-recorded'}}}}
    _write(os.path.join(work, '.mcp.json'), {'mcpServers': {
        'gh': {'command': 'project-gh'}, 'dup': {'command': 'project-dup'},
        'plain': 'not-an-object', 'nothing': None}})
    # a project's server loads only as the file its digest approved (owner item 76)
    with open(os.path.join(work, '.mcp.json'), 'rb') as f:
        pin = hashlib.sha256(f.read()).hexdigest()
    assert sources.mcp_config(home, work, _servers('project', 'dup')) == {'mcpServers': {}}
    got = sources.mcp_config(home, work, _servers('account', 'gh', 'nothere')
                             + [dict(s, digest=pin) for s in _servers(
                                 'project', 'gh', 'dup', 'plain', 'nothing', 'missing')])
    assert got == {'mcpServers': {
        'gh': {'command': 'gh-mcp', 'env': {'TOKEN': 'never-recorded'}},
        'dup': {'command': 'project-dup'}}}
    assert sources.mcp_config(None, work, _servers('account', 'gh')) == {'mcpServers': {}}
    assert sources.mcp_config(home, None, _servers('project', 'dup')) == {'mcpServers': {}}
    assert sources.mcp_config(home, work, _servers('other', 'gh')) == {'mcpServers': {}}
    # what the record keeps of all this is the name, never the definition
    raw = json.dumps(take(world, ('account', 'mcp', 'gh')))
    assert 'gh-mcp' not in raw and 'never-recorded' not in raw


def test_a_project_mcp_server_loads_only_as_the_file_it_was_approved(world):
    """sources.take with pins: a project's opt-in loads its server only while the
    .mcp.json is the file whose digest was approved (owner item 76). Unpinned or
    changed, the server is excluded with its digest shown so it can be approved."""
    _home, work, _m = world
    path = os.path.join(work, '.mcp.json')
    _write(path, {'mcpServers': {'db': {'command': 'db-mcp'}}})
    pin = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    opt = (('project', 'mcp', 'db'),)
    (unpinned,) = items(take(world, *opt), type='mcp_server', name='db')
    assert (unpinned['status'], unpinned['reason'], unpinned['sha256']) == (
        'excluded', 'mcp_not_pinned', pin)
    inv = take(world, *opt, pins=(('project', 'mcp', 'db', pin),))
    assert inv['flags']['mcp_servers'] == [{'owner': 'project', 'name': 'db', 'digest': pin}]
    _write(path, {'mcpServers': {'db': {'command': 'evil'}}})
    (changed,) = items(take(world, *opt, pins=(('project', 'mcp', 'db', pin),)),
                       type='mcp_server', name='db')
    assert (changed['status'], changed['reason']) == ('excluded', 'mcp_changed')
    assert take(world, *opt, pins=(('project', 'mcp', 'db', pin),))['flags']['mcp_servers'] == []


def test_g09_with_no_account_and_no_project_nothing_is_read_and_nothing_loads(tmp_path):
    """sources.py:176-177/199-200/288/316-320/335-347/375-377/400-402: an execution
    with neither a home nor a workdir reads nothing and loads nothing, and never
    falls back to Claude Code's own default, which is every source. A plugin that
    cannot resolve contributes a `None` path the argv then drops."""
    inv = sources.take(None, None, (('account', 'mcp', 'gh'), ('project', 'plugin', 'pl@m')),
                       managed=os.path.join(str(tmp_path), 'no-managed.json'))
    assert inv['flags'] == {'setting_sources': [], 'strict_mcp_config': True,
                            'mcp_servers': [], 'disable_slash_commands': True,
                            'plugin_dirs': [{'name': 'pl@m', 'path': None}]}
    # the whole record of an execution with nothing on disk: the plugin its opt-in
    # named (which resolved to nothing), the server its opt-in named (which is not
    # there either), and the CLI's own class items
    assert [(i['source'], i['type'], i['name'], i['status']) for i in inv['items']] == [
        ('plugin', 'plugin', 'pl@m', 'not_found'),
        ('user', 'mcp_server', 'gh', 'not_found'),
        ('cli', 'plugin', 'built-in plugins', 'builtin'),
        ('cli', 'skill', 'bundled skills', 'excluded')]
    assert sources.plugin_dir(None, 'pl@m') is None
    assert sources.mcp_config(None, None, _servers('account', 'gh')) == {'mcpServers': {}}
    a = sources.flag_argv(inv['flags'], home=None, workdir=None, exec_dir=str(tmp_path / 'e'))
    assert a == ['--setting-sources', '', '--strict-mcp-config', '--disable-slash-commands']


# ── the boundaries of the record ─────────────────────────────────────────────

def test_g10_the_record_is_cut_at_exactly_max_items_and_the_cut_is_said(world, monkeypatch):
    """sources.py:366: `items[:MAX_ITEMS]` and `truncated: len(items) > MAX_ITEMS`
    read one boundary twice - off by one there either loses an item in silence or
    calls a whole record truncated, and a tail cut instead of a head cut drops the
    settings entries the record was made for."""
    monkeypatch.setattr(sources, 'MAX_ITEMS', 10 ** 6)            # the record whole
    full = take(world)['items']
    assert len(full) > 10 and take(world)['truncated'] is False
    monkeypatch.setattr(sources, 'MAX_ITEMS', len(full))          # exactly the whole
    inv = take(world)
    assert inv['items'] == full and inv['truncated'] is False
    monkeypatch.setattr(sources, 'MAX_ITEMS', len(full) - 1)      # one item over
    inv = take(world)
    assert len(inv['items']) == len(full) - 1 and inv['truncated'] is True
    assert inv['items'] == full[:-1]                                # the head, not the tail


def test_g11_an_unbounded_settings_file_cannot_make_an_unbounded_record(world):
    """sources.py:292-298 with 366 and the default MAX_ITEMS: 800 hooks in one
    settings file are recorded as at most MAX_ITEMS items and the cut is said. The
    head is kept in the source's own order (`sorted` events), so an inversion to a
    tail cut is caught here too."""
    def group(key):
        return [{'matcher': '*', 'hooks': [{'type': 'command', 'command': '%s%d.sh' % (key, i)}
                                           for i in range(400)]}]
    _write(os.path.join(world[0], 'settings.json'),
           {'hooks': {'PreToolUse': group('pre'), 'PostToolUse': group('post')}})
    inv = take(world, ('account', 'source', 'user'))
    assert len(inv['items']) == sources.MAX_ITEMS and inv['truncated'] is True
    assert {i['type'] for i in inv['items']} == {'hook'}           # nothing later survived
    assert [i['name'] for i in inv['items'][:400]] == [
        'PostToolUse: post%d.sh' % i for i in range(400)]
    assert inv['items'][-1]['name'] == 'PreToolUse: pre99.sh'


def test_g12_an_overlong_name_is_recorded_cut_and_never_whole(world):
    """sources.py:252 and 264: `str(name)[:NAME_MAX]` and the manifest's `loads_as`
    are the only bound on what a settings file can make the record carry; without
    them one rule of any size is one item of any size."""
    huge = 'x' * 5000
    _write(os.path.join(world[0], 'settings.json'), {'permissions': {'allow': ['Bash(%s)' % huge]}})
    _write(os.path.join(world[0], 'plugins', 'pl', '1', '.claude-plugin', 'plugin.json'),
           {'name': 'y' * 5000})
    inv = take(world, ('account', 'source', 'user'), ('account', 'plugin', 'pl@m'))
    (perm,) = items(inv, source='user', type='permission')
    assert perm['name'] == ('allow: Bash(%s)' % huge)[:sources.NAME_MAX]
    assert len(perm['name']) == sources.NAME_MAX == 200
    assert ('allow: Bash(%s)' % huge).startswith(perm['name'])     # cut, never mangled
    (plug,) = plugin_items(inv)
    assert plug['loads_as'] == 'y' * sources.NAME_MAX
    assert max(len(i['name']) for i in inv['items']) <= sources.NAME_MAX


# ── the error paths: a file that is not there, or not readable, or not shaped ──

@pytest.mark.parametrize('raw, why', [(b'[1, 2]', 'not a JSON object'),
                                      (b'"a string"', 'not a JSON object'),
                                      (b'', 'not JSON'), (b'{oops', 'not JSON'),
                                      (b'\xff\xfe{"hooks": {}}', 'not JSON')],
                         ids=('list', 'string', 'empty', 'notjson', 'badutf8'))
def test_g13_a_settings_file_that_is_not_a_json_object_loads_nothing_and_is_said(world, raw, why):
    """sources.py:97-105 with 290-291: what the module cannot read as a settings
    object is recorded as `unreadable` with its error and the source's own status,
    and contributes no item at all - never treated as an empty settings file, which
    is how a truncated file would silently stop excluding things."""
    _write(os.path.join(world[0], 'settings.json'), raw)
    inv = take(world, ('account', 'source', 'user'))
    (u,) = items(inv, type='unreadable', source='user')
    assert (u['status'], u['error'], u['name']) == ('opted_in', why, 'settings.json')
    assert not [i for i in items(inv, source='user') if i['type'] in (
        'hook', 'permission', 'plugin')]                      # nothing was read from it
    # a BOM is not an error: the same file with one parses (sources.py:102)
    _write(os.path.join(world[0], 'settings.json'),
           b'\xef\xbb\xbf' + json.dumps({'hooks': _hooks('bom.sh')}).encode('utf-8'))
    inv = take(world, ('account', 'source', 'user'))
    assert not items(inv, type='unreadable', source='user')
    assert [i['name'] for i in items(inv, type='hook', source='user')] == ['PreToolUse: bom.sh']


def test_g14_a_file_that_exists_but_cannot_be_read_is_said_with_its_error(world):
    """sources.py:86-94 with 290-291 and 349-353: where a settings file or a
    CLAUDE.md has been replaced by a directory (an editor mid-save, a hostile run
    of `claude`), the read raises an OSError that is not FileNotFoundError: the
    item is recorded with that error and no `sha256`, so the record says it could
    not tell - while a file that is simply absent is recorded as nothing."""
    home, work, _m = world
    for path in (os.path.join(home, 'settings.json'), os.path.join(work, 'CLAUDE.md')):
        os.remove(path)
        os.mkdir(path)
    inv = take(world, ('project', 'source', 'project'))
    (u,) = items(inv, type='unreadable', source='user')
    assert u['error'] in ('IsADirectoryError', 'PermissionError')      # the OS's own name
    assert (u['status'], u['name']) == ('excluded', 'settings.json')
    (md,) = [i for i in items(inv, type='claude_md', source='project') if i['name'] == 'CLAUDE.md']
    assert md['status'] == 'opted_in' and md['error'] in ('IsADirectoryError', 'PermissionError')
    assert 'sha256' not in md
    # a CLAUDE.md that is not there is recorded as nothing at all (sources.py:350-351)
    os.rmdir(os.path.join(work, 'CLAUDE.md'))
    os.remove(os.path.join(home, 'CLAUDE.md'))
    inv = take(world, ('project', 'source', 'project'))
    gone = {i['name'] for i in items(inv, type='claude_md') if i['source'] == 'user'}
    assert 'CLAUDE.md' not in gone and not [
        i for i in items(inv, type='claude_md', source='project')
        if i['name'] in ('CLAUDE.md', 'CLAUDE.local.md', '.claude/CLAUDE.md')]
    # the settings file that is still a directory is still said, once and only once
    assert len(items(inv, type='unreadable', source='user')) == 1


def test_g15_a_hostile_settings_shape_neither_crashes_nor_predicts_a_load(world):
    """sources.py:145-163: hooks that are not a dict, groups that are not a list,
    hook entries that are not objects or name no command, `enabledPlugins` and
    `permissions` that are not objects, and rules that are objects of their own -
    all of them recorded or skipped, never a `TypeError` out of `take` (which would
    stop every execution of the pass) and never an item that predicts a load."""
    _write(os.path.join(world[0], 'settings.json'), {
        'hooks': {'PreToolUse': 'not-a-list', 'SessionStart': [{'hooks': 'not-a-list'}],
                  'X': ['not-a-dict', {'matcher': '*'}, None, {'hooks': [
                      {'type': 'command'}, {'command': ''}, 'nope', {'command': 'real.sh'}]}]},
        'enabledPlugins': 'not-a-dict',
        'permissions': {'allow': {'not': 'a-list'}, 'ask': [{'nested': {'deep': 1}}],
                        'deny': None, 'extra': 'never-read'},
        'env': {'SECRET_TOKEN': 'never-read'}})
    _write(os.path.join(world[1], '.claude', 'settings.json'), {'hooks': 'not-a-dict',
                                                                'permissions': ['x']})
    _plugin_tree(os.path.join(world[0], 'plugins', 'pl', '1'),
                 hooks={'hooks': {'PreToolUse': 'not-a-list',
                                  'Y': [{'hooks': ['x', {'command': 'p.sh'}, {'nope': 1}]}]}})
    inv = take(world, ('account', 'source', 'user'), ('project', 'source', 'project'),
               ('account', 'plugin', 'pl@m'))      # the junk hooks.json is the plugin's own
    assert [i['name'] for i in items(inv, type='hook', source='user')] == ['X: real.sh']
    assert {i['name'] for i in items(inv, type='permission', source='user')} == {
        "allow: not", "ask: {'nested': {'deep': 1}}"}
    assert not items(inv, source='user', type='plugin')            # enabledPlugins was junk
    assert [i['name'] for i in items(inv, type='hook', source='plugin:pl@m')] == ['Y: p.sh']
    assert not [i for i in items(inv, source='project') if i['type'] in (
        'hook', 'permission', 'plugin', 'unreadable')]          # nothing was read of them
    assert items(inv, type='mcp_server', name='db')[0]['status'] == 'excluded'
    raw = json.dumps(inv)
    assert 'never-read' not in raw and 'SECRET_TOKEN' not in raw


def test_g16_a_hostile_skills_tree_adds_no_skill_and_never_enables_slash_commands(world):
    """sources.py:116-122 with 335-345: a `skills` root that is a file, a skill
    directory with no `SKILL.md`, a `SKILL.md` that is a directory, a plain file
    among the skill names, and a `skills/synced` that is not a directory - every
    one of them yields no skill, and the flag stays `--disable-slash-commands`,
    which is the fail-closed answer rather than a guess that one loaded."""
    home = world[0]
    skills = os.path.join(home, 'skills')
    os.remove(os.path.join(skills, 'uskill', 'SKILL.md'))          # a skill with no SKILL.md
    os.makedirs(os.path.join(skills, 'md-is-a-dir', 'SKILL.md'))   # SKILL.md is a directory
    _writeb(os.path.join(skills, 'a-plain-file'), b'x\n')          # a file among the names
    _writeb(os.path.join(skills, 'synced'), b'not a directory\n')  # the synced root is a file
    inv = take(world, ('account', 'source', 'user'))
    assert items(inv, type='skill', source='user') == []
    assert inv['flags']['disable_slash_commands'] is True           # nothing arrived with it
    assert [i['name'] for i in items(inv, type='skill', source='project')] == ['pjskill']
    # the same answer when `synced` is a directory whose entries are not directories
    os.remove(os.path.join(skills, 'synced'))
    _writeb(os.path.join(skills, 'synced', 'not-a-directory'), b'x\n')
    inv = take(world, ('account', 'source', 'user'))
    assert items(inv, type='skill', source='user') == []
    assert not [i for i in inv['items'] if i.get('via') == 'synced']
    assert inv['flags']['disable_slash_commands'] is True


def test_g17_what_a_plugin_declares_is_read_only_inside_the_plugin(world):
    """sources.py:125-142: a manifest's `skills` may name paths; a path outside the
    plugin directory is not read even when it exists and holds a real skill (a
    sibling plugin's whole `skills` directory, a skill of its own one level up),
    an entry that is not a string is skipped rather than raising, and a declared
    path that is itself one skill is named by its `SKILL.md`, falling back to the
    directory's own name when the front matter says none."""
    home = world[0]
    root = os.path.join(home, 'plugins', 'pl', '1')
    _write(os.path.join(root, '.claude-plugin', 'plugin.json'), {
        'name': 'pl', 'skills': [42, None, True, {'x': 1}, 'decl', 'solo',
                                   '../../pl-evil/skills', '../../pl-outside']})
    _write(os.path.join(root, 'decl', 'sub', 'SKILL.md'), b'---\nname: sub\n---\nbody\n')
    _write(os.path.join(root, 'solo', 'SKILL.md'), b'# no front matter here\n')
    # two real things outside the plugin its manifest could reach if it were trusted:
    # a directory of skills, and one skill that is itself a directory
    _plugin_tree(os.path.join(home, 'plugins', 'pl-evil'), skills=('escaped',))
    _write(os.path.join(home, 'plugins', 'pl-outside', 'SKILL.md'), b'---\nname: outside\n---\n')
    inv = take(world, ('account', 'plugin', 'pl@m'))
    assert {i['name'] for i in items(inv, source='plugin:pl@m', type='skill')} == {
        'pskill', 'sub', 'solo'}
    assert 'escaped' not in {i['name'] for i in inv['items']}      # never read, never named
    assert 'outside' not in {i['name'] for i in inv['items']}
    assert 'pl-outside' not in {i['name'] for i in inv['items']}
    assert {i['status'] for i in items(inv, source='plugin:pl@m', type='skill')} == {'opted_in'}
    # the servers it brings stay out whatever the opt-in (--strict-mcp-config)
    assert {i['status'] for i in items(inv, source='plugin:pl@m', type='mcp_server')} == {
        'excluded'}
    assert {i['name'] for i in items(inv, type='hook')} >= {'PreToolUse: plugin-hook.sh'}


def test_g18_no_setting_source_predicts_a_load_the_flags_do_not_pass(world, tmp_path):
    """sources.py:237-240 with 358-362: an item of a setting source predicts loaded
    exactly when `--setting-sources` names that source, in both directions; and a
    `recorded_only` name that is not one of the three sources can never reach the
    argv, only the recorded item."""
    for opt_in, on in ((('account', 'source', 'user'), 'user'), (('project', 'source', 'local'),
                                                                  'local'), ((), None)):
        inv = take(world, opt_in) if opt_in else take(world)
        passed = inv['flags']['setting_sources']
        assert passed == ([on] if on else [])
        for src in sources.SOURCES:
            sts = {i['status'] for i in inv['items'] if i['source'] == src}
            assert bool(sts & set(sources.LOADED)) == (src in passed), (src, sts, passed)
    inv = take(world, recorded_only=('user', 'bogus'))
    assert inv['recorded_only'] == ['user', 'bogus']
    assert inv['flags']['setting_sources'] == ['user']
    a = argv(world, inv, tmp_path / 'exec')
    assert a[:2] == ['--setting-sources', 'user'] and 'bogus' not in a


def test_g19_a_plugin_the_account_enables_and_the_owner_opts_in_is_recorded_at_both_ends(
        world, tmp_path):
    """sources.py:293-296: an `enabledPlugins` entry its owner also opted in is
    recorded at its setting source as `opted_in` with `via: plugin_dir` and, apart
    from that, as the plugin its own directory brings; one nobody opted in stays at
    its source's status with no `via` and is never passed as a directory."""
    inv = take(world, ('account', 'source', 'user'))                # enabled, not opted in
    (entry,) = items(inv, source='user', type='plugin')
    assert (entry['name'], entry['status']) == ('pl@m', 'opted_in') and 'via' not in entry
    assert inv['flags']['plugin_dirs'] == [] and '--plugin-dir' not in argv(
        world, inv, tmp_path / 'exec-a')
    inv = take(world, ('account', 'source', 'user'), ('account', 'plugin', 'pl@m'))
    (entry,) = items(inv, source='user', type='plugin')
    assert (entry['status'], entry['via']) == ('opted_in', 'plugin_dir')
    (loaded,) = plugin_items(inv)
    assert (loaded['status'], loaded['via'], loaded['loads_as']) == (
        'opted_in', 'plugin_dir', 'pl')
    assert {i['source'] for i in items(inv, type='skill')} >= {'plugin:pl@m', 'project'}
    a = argv(world, inv, tmp_path / 'exec-b')
    assert a[a.index('--plugin-dir') + 1] == os.path.realpath(
        os.path.join(world[0], 'plugins', 'pl', '1'))
    assert '--disable-slash-commands' not in a                      # it brings a skill


def test_g20_managed_settings_are_recorded_even_when_they_cannot_be_read(world):
    """sources.py:300-305: managed settings always apply, so a managed file that
    cannot be parsed is still recorded - with its error and `not_excludable`, never
    omitted, which would let the record read as though nothing outside the three
    sources applied. A managed file that is not there is recorded as nothing."""
    _writeb(world[2], b'{oops')
    inv = take(world)
    (m,) = items(inv, type='managed_settings')
    assert (m['status'], m['error'], m['name']) == ('not_excludable', 'not JSON',
                                                    'managed-settings.json')
    assert not [i for i in items(inv, source='managed') if i['type'] != 'managed_settings']
    _write(world[2], {'hooks': _hooks('managed.sh'), 'permissions': {'allow': ['Read(x)']}})
    inv = take(world, ('project', 'source', 'local'))
    assert [(i['type'], i['status']) for i in items(inv, source='managed')] == [
        ('managed_settings', 'not_excludable'), ('hook', 'not_excludable'),
        ('permission', 'not_excludable')]
    # no opt-in and no flag of Archeus's reaches them, and they are not a source
    assert {i['status'] for i in inv['items'] if i['source'] == 'managed'} == {'not_excludable'}
    assert 'managed' not in inv['flags']['setting_sources']
    assert not items(take(world, managed=os.path.join(os.path.dirname(world[2]),
                                                       'absent.json')), source='managed')


@pytest.mark.parametrize('there', [False, True], ids=('gone-midway', 'appeared-midway'))
def test_g21_the_argv_names_exactly_the_plugin_dirs_the_record_said_loaded(world, tmp_path,
                                                                           monkeypatch, there):
    """sources.py `take`: the plugin directory is asked for once, so the record and
    the flags built from it cannot disagree when an uninstaller (or a `claude plugin
    install`) moves it in between: the record says opted_in and the argv carries the
    directory, or the record says not_found and the argv carries none."""
    home = world[0]
    good = os.path.realpath(os.path.join(home, 'plugins', 'pl', '1'))
    _write(os.path.join(home, 'settings.json'), {'hooks': _hooks('user-hook.sh')})
    seen = []
    real = sources.plugin_dir

    def flaky(path, name):                       # the directory on the first ask only
        seen.append(name)
        return None if there == bool(len(seen) == 1) else real(path, name)

    monkeypatch.setattr(sources, 'plugin_dir', flaky)
    inv = take(world, ('account', 'plugin', 'pl@m'))
    assert len(seen) == 1, 'the module asked for the same directory twice'
    status, path = ('not_found', None) if there else ('opted_in', good)
    assert [i['status'] for i in plugin_items(inv)] == [status]          # what was recorded
    assert [d['path'] for d in inv['flags']['plugin_dirs']] == [path]    # what the flags carry
    a = sources.flag_argv(inv['flags'], home=home, workdir=world[1], exec_dir=str(tmp_path / 'e'))
    assert ('--plugin-dir' in a) == (not there)
