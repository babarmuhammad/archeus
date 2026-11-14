import builtins
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox
from claude_sessions import agents


class SimulatedCrash(BaseException):
    pass


def _seed(sb, name):
    d = sb.agents_lib / '01-core'
    d.mkdir(parents=True, exist_ok=True)
    agents.write_agent(str(d / f'{name}.md'),
                       {'name': name, 'description': 'Use when x.'},
                       'Body %s.' % name)


def _proj(tmp_path):
    p = tmp_path / 'proj'
    p.mkdir()
    return p


def _dest(proj):
    return proj / '.claude' / 'agents'


def _manifest(proj):
    p = _dest(proj) / agents._MANIFEST
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else None


def _same(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def test_locked_managed_file_keeps_its_ownership_record(monkeypatch, tmp_path):
    """Manifest owns a.md, the selection is empty, and a.md is locked. The leftover
    file must stay in the record, or the next sync treats it as the user's own."""
    sb = Sandbox(monkeypatch, tmp_path)
    _seed(sb, 'a')
    proj = _proj(tmp_path)
    assert agents.sync_project_agents(str(proj), ['01-core/a']) == 1

    real_remove = os.remove

    def locked(p, *a, **k):
        if os.path.basename(str(p)) == 'a.md':
            raise PermissionError('simulated lock')
        return real_remove(p, *a, **k)

    monkeypatch.setattr(os, 'remove', locked)
    assert agents.sync_project_agents(str(proj), []) == 0
    assert (_dest(proj) / 'a.md').exists()
    assert _manifest(proj) == ['a.md'], 'a surviving managed file lost its ownership record'

    monkeypatch.setattr(os, 'remove', real_remove)
    agents.sync_project_agents(str(proj), [])
    assert not (_dest(proj) / 'a.md').exists(), 'the next sync could not remove the leftover'
    assert _manifest(proj) is None


def test_managed_file_keeps_its_record_when_its_source_cannot_be_read(monkeypatch, tmp_path):
    """Managed a.md is still selected, but its library source cannot be read. The
    old copy stays on disk, so the record must still name it."""
    sb = Sandbox(monkeypatch, tmp_path)
    _seed(sb, 'a')
    proj = _proj(tmp_path)
    assert agents.sync_project_agents(str(proj), ['01-core/a']) == 1

    src = str(sb.agents_lib / '01-core' / 'a.md')
    real_open = builtins.open

    def unreadable(file, mode='r', *a, **kw):
        if not isinstance(file, int) and not any(c in mode for c in 'wax+') \
                and _same(file, src):
            raise OSError('simulated read failure')
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, 'open', unreadable)
    assert agents.sync_project_agents(str(proj), ['01-core/a']) == 0
    assert (_dest(proj) / 'a.md').exists()
    assert _manifest(proj) == ['a.md'], 'a file still on disk lost its ownership record'


def test_crash_after_the_first_record_keeps_managed_names(monkeypatch, tmp_path):
    """A crash between the first record and the removal of a deselected managed
    file must not leave that file unowned."""
    sb = Sandbox(monkeypatch, tmp_path)
    _seed(sb, 'a')
    proj = _proj(tmp_path)
    assert agents.sync_project_agents(str(proj), ['01-core/a']) == 1

    real_remove = os.remove

    def crash(p, *a, **k):
        if os.path.basename(str(p)) == 'a.md':
            raise SimulatedCrash()
        return real_remove(p, *a, **k)

    monkeypatch.setattr(os, 'remove', crash)
    with pytest.raises(SimulatedCrash):
        agents.sync_project_agents(str(proj), [])
    assert _manifest(proj) == ['a.md'], 'a crash disowned a managed file before removing it'


def test_a_successful_removal_drops_the_name_from_the_manifest(monkeypatch, tmp_path):
    """Control: a deselected file that is removed leaves the record, and the
    selected one stays."""
    sb = Sandbox(monkeypatch, tmp_path)
    _seed(sb, 'a')
    _seed(sb, 'b')
    proj = _proj(tmp_path)
    assert agents.sync_project_agents(str(proj), ['01-core/a', '01-core/b']) == 2
    assert sorted(_manifest(proj)) == ['a.md', 'b.md']

    assert agents.sync_project_agents(str(proj), ['01-core/b']) == 1
    assert not (_dest(proj) / 'a.md').exists()
    assert _manifest(proj) == ['b.md']




@pytest.mark.parametrize('routed', [False, True])
def test_user_file_created_after_the_check_is_not_overwritten(monkeypatch, tmp_path, routed):
    """The name looks absent at the ownership check, then the user creates rev.md
    before the copy. The copy must not overwrite it, and the name is not recorded."""
    sb = Sandbox(monkeypatch, tmp_path)
    _seed(sb, 'rev')
    proj = _proj(tmp_path)
    _dest(proj).mkdir(parents=True)
    own = _dest(proj) / 'rev.md'
    own.write_text('USER OWN AGENT\n', encoding='utf-8')

    real_lexists = os.path.lexists
    seen = []

    def absent_once(p):
        if not seen and _same(p, own):
            seen.append(p)
            return False
        return real_lexists(p)

    monkeypatch.setattr(os.path, 'lexists', absent_once)
    n = agents.sync_project_agents(str(proj), ['01-core/rev'], routed=routed)
    monkeypatch.setattr(os.path, 'lexists', real_lexists)

    assert seen, 'the check never ran for rev.md'
    assert n == 0, n
    assert own.read_text(encoding='utf-8') == 'USER OWN AGENT\n', 'the user file was overwritten'
    assert 'rev.md' not in (_manifest(proj) or []), 'the user file was claimed'
