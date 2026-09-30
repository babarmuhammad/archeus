"""`ARCHEUS_HOME` resolution (target-architecture §5.1) and the execution path
contract (execution-architecture §3.1)."""

import os

import pytest

from archeus.core.domain import ids
from archeus.infra import paths

HOME = os.path.expanduser('~')


def test_the_override_wins_on_every_platform(tmp_path):
    for plat in ('win32', 'darwin', 'linux'):
        env = {'ARCHEUS_HOME': str(tmp_path / 'h'), 'LOCALAPPDATA': 'C:/L',
               'XDG_DATA_HOME': '/xdg'}
        assert paths.archeus_home(env, plat) == os.path.abspath(str(tmp_path / 'h'))


def test_windows_uses_localappdata():
    got = paths.archeus_home({'LOCALAPPDATA': os.path.join(HOME, 'LAD')}, 'win32')
    assert got == os.path.abspath(os.path.join(HOME, 'LAD', 'Archeus'))
    fallback = paths.archeus_home({}, 'win32')
    assert fallback == os.path.abspath(os.path.join(HOME, 'AppData', 'Local', 'Archeus'))


def test_macos_uses_application_support():
    assert paths.archeus_home({}, 'darwin') == os.path.abspath(
        os.path.join(HOME, 'Library', 'Application Support', 'Archeus'))


def test_linux_uses_xdg_data_home_only_when_absolute():
    xdg = os.path.abspath(os.path.join(HOME, 'xdg-data'))
    assert paths.archeus_home({'XDG_DATA_HOME': xdg}, 'linux') == os.path.join(xdg, 'archeus')
    default = os.path.abspath(os.path.join(HOME, '.local', 'share', 'archeus'))
    assert paths.archeus_home({'XDG_DATA_HOME': 'relative/dir'}, 'linux') == default
    assert paths.archeus_home({'ARCHEUS_HOME': '  '}, 'linux') == default


def test_it_resolves_at_call_time_not_import_time(monkeypatch, tmp_path):
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'one'))
    first = paths.run_dir()
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'two'))
    assert paths.run_dir() != first and paths.run_dir().startswith(str(tmp_path / 'two'))


@pytest.mark.parametrize('plat', ['win32', 'darwin', 'linux'])
def test_the_default_is_never_the_legacy_dot_archeus(plat):
    got = paths.archeus_home({}, plat)
    assert os.path.normcase(got) != os.path.normcase(os.path.join(HOME, '.archeus'))
    assert '.archeus' not in os.path.normcase(got).replace('\\', '/').split('/')


@pytest.mark.parametrize('bad', [os.path.join('~', '.archeus'),
                                 os.path.join(HOME, '.archeus'),
                                 os.path.join(HOME, 'proj', '.archeus', 'v1')])
def test_a_legacy_archeus_directory_is_refused_even_when_named(bad):
    with pytest.raises(ValueError, match='legacy'):
        paths.archeus_home({'ARCHEUS_HOME': bad}, 'linux')


def test_resolving_touches_no_disk(tmp_path):
    home = tmp_path / 'not-created'
    paths.archeus_home({'ARCHEUS_HOME': str(home)})
    paths.ExecPaths(ids.new_id('execution'), run=str(home / 'run'))
    assert not home.exists()


def test_the_execution_files_of_the_process_io_contract(archeus_home):
    exe = ids.new_id('execution')
    p = paths.exec_paths(exe)
    base = os.path.join(str(archeus_home), 'run', 'exec', exe)
    assert p.dir == base
    assert {os.path.basename(x) for x in (p.spawning, p.prompt, p.stream, p.pid, p.ended)} == {
        'spawning', 'prompt.txt', 'stream.jsonl', 'pid.json', 'ended'}
    assert all(os.path.dirname(x) == base for x in (p.spawning, p.prompt, p.stream, p.pid, p.ended))
    assert paths.processes_registry() == os.path.join(str(archeus_home), 'run', 'processes.jsonl')


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
ARCH = os.path.join(ROOT, 'docs', 'architecture')


def _arch_docs():
    for name in sorted(os.listdir(ARCH)):
        if name.endswith('.md'):
            yield name, open(os.path.join(ARCH, name), encoding='utf-8').read()


def test_v1_and_the_legacy_qt_shell_own_disjoint_entries():
    fold = lambda names: {n.lower() for n in names}          # NTFS is case-insensitive
    assert not fold(paths.V1_OWNED) & fold(paths.QT_OWNED)


def test_the_ownership_table_is_the_declaration():
    """target-architecture §5.1's table, paths.V1_OWNED/QT_OWNED and every
    `<ARCHEUS_HOME>/<entry>` the documents mention must agree."""
    import re
    text = open(os.path.join(ARCH, 'target-architecture.md'), encoding='utf-8').read()
    table = text[text.index('**Ownership inside `<ARCHEUS_HOME>`.**'):]
    table = table[:table.index('\n\n', table.index('| Entry |'))]
    rows = {}
    for line in table.splitlines():
        if line.startswith('| `'):
            entry, owner = [c.strip() for c in line.strip('|').split('|')][:2]
            for name in re.findall(r'`([^`]+?)/?`', entry):
                rows[name] = owner
    assert {n for n, o in rows.items() if o == 'V1'} == set(paths.V1_OWNED)
    assert {n for n, o in rows.items() if o == 'legacy Qt shell'} == set(paths.QT_OWNED)
    mentioned = set()
    for _name, doc in _arch_docs():
        mentioned |= set(re.findall(r'<ARCHEUS_HOME>/([A-Za-z0-9_.-]+)', doc))
    assert mentioned <= set(paths.V1_OWNED), mentioned - set(paths.V1_OWNED)


def test_every_v1_path_lands_in_a_v1_owned_entry(archeus_home):
    for p in (paths.run_dir(), paths.processes_registry(),
              paths.exec_paths(ids.new_id('execution')).stream):
        top = os.path.relpath(p, str(archeus_home)).split(os.sep)[0]
        assert top in paths.V1_OWNED, p


def test_the_qt_shell_still_names_itself_archeus():
    """The ownership table exists because of this one call: Qt derives its
    per-user directories from the application name. If it changes, the table
    in target-architecture §5.1 must change with it."""
    src = open(os.path.join(ROOT, 'claude_sessions', 'gui_qt.py'), encoding='utf-8').read()
    assert "app.setApplicationName('archeus')" in src


def test_no_instruction_deletes_archeus_home_as_a_whole():
    """A reset removes V1's entries by name; the directory also holds the
    legacy Qt cache. Any sentence about deleting ARCHEUS_HOME must say never."""
    import re
    bad = []
    for name, doc in _arch_docs():
        for sent in re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', doc)):
            if (re.search(r'\b(delete|remove|rm)\b', sent, re.I)
                    and re.search(r'`?ARCHEUS_HOME`? directory', sent)
                    and 'never' not in sent.lower()):
                bad.append('%s: %s' % (name, sent[:100]))
    assert not bad, bad


@pytest.mark.parametrize('bad', ['../../etc', 'exe_../x', 'msn_01J00000000000000000000000',
                                 'exe_' + '0' * 25, ''])
def test_only_an_execution_id_can_name_an_execution_directory(bad):
    with pytest.raises(ValueError):
        paths.ExecPaths(bad)
