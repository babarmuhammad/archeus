import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox

from claude_sessions import conventions, memory
from claude_sessions.config import _CONV_START, _CONV_END


def _pref(summary, status='approved', kind='preference', conf=0.9):
    return {'name': summary[:20], 'type': 'lesson', 'kind': kind, 'status': status,
            'summary': summary, 'confidence': conf, 'repo': '', 'module': '(project)'}


def test_promotes_recurring_convention(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    a1, e1, f1, _ = sb.add_project('alpha')
    a2, e2, f2, _ = sb.add_project('beta')
    conv = 'this machine uses PowerShell 5.1 not bash'
    m1 = memory._empty(); m1['entities'] = [_pref(conv)]
    memory.save_memory(a1, f1, m1)
    m2 = memory._empty(); m2['entities'] = [_pref('this machine uses PowerShell 5.1 not bash syntax')]
    memory.save_memory(a2, f2, m2)
    got = conventions.collect_conventions()
    # objects, not (summary, score) tuples: the tuple serialized as a JSON
    # array and the GUI rendered it through JSON.stringify
    assert all(isinstance(r, dict) and 'text' in r and 'score' in r for r in got)
    assert any('PowerShell' in r['text'] for r in got)   # recurs across 2 projects
    assert any(r['projects'] == 2 for r in got)


def test_single_project_not_promoted_unless_pinned(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    a1, e1, f1, _ = sb.add_project('alpha')
    m1 = memory._empty(); m1['entities'] = [_pref('one-off preference only here')]
    memory.save_memory(a1, f1, m1)
    assert conventions.collect_conventions() == []
    # pinned single-project → promoted
    m1['entities'][0]['status'] = 'pinned'
    memory.save_memory(a1, f1, m1)
    assert conventions.collect_conventions()


def test_sync_writes_global_block(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    a1, e1, f1, _ = sb.add_project('alpha')
    a2, e2, f2, _ = sb.add_project('beta')
    c = 'prefer pytest over unittest for tests'
    for a, f in ((a1, f1), (a2, f2)):
        m = memory._empty(); m['entities'] = [_pref(c)]
        memory.save_memory(a, f, m)
    assert conventions.sync_to_global()
    from claude_sessions.config import global_claude_md
    text = open(global_claude_md, encoding='utf-8').read()
    assert _CONV_START in text and _CONV_END in text and 'pytest' in text


def test_sync_disabled_setting(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr('claude_sessions.config.load_settings',
                        lambda: {'conventions_to_global': False})
    assert conventions.sync_to_global() is False


def test_a_decision_counts_as_a_convention(monkeypatch, tmp_path):
    """`decision` travels between repos the way a preference does; excluding it
    was most of the reason this list stayed empty."""
    sb = Sandbox(monkeypatch, tmp_path)
    a1, e1, f1, _ = sb.add_project('alpha')
    a2, e2, f2, _ = sb.add_project('beta')
    d = 'commit messages follow Conventional Commits'
    for a, f in ((a1, f1), (a2, f2)):
        m = memory._empty(); m['entities'] = [_pref(d, kind='decision')]
        memory.save_memory(a, f, m)
    assert any('Conventional Commits' in r['text']
               for r in conventions.collect_conventions())


def test_an_unreviewed_lesson_needs_three_projects(monkeypatch, tmp_path):
    """Recurrence at scale is its own evidence — but two is not that scale, so
    the reviewed bar still means something."""
    sb = Sandbox(monkeypatch, tmp_path)
    projs = [sb.add_project(n) for n in ('alpha', 'beta', 'gamma')]
    text = 'always run the linter before committing anything'
    for a, _e, f, _x in projs[:2]:
        m = memory._empty(); m['entities'] = [_pref(text, status='pending')]
        memory.save_memory(a, f, m)
    assert conventions.collect_conventions() == []
    near = conventions.near_misses()
    assert any('linter' in n['text'] and 'needs 1 more' in n['why'] for n in near)

    a3, _e3, f3, _x3 = projs[2]
    m = memory._empty(); m['entities'] = [_pref(text, status='pending')]
    memory.save_memory(a3, f3, m)
    assert any('linter' in r['text'] for r in conventions.collect_conventions())


def test_pinning_a_near_miss_promotes_it_everywhere(monkeypatch, tmp_path):
    """Pin is the manual override the promotion rules already respect, so it is
    the one action that turns a near-miss into a convention at once — and it
    must reach BOTH mirrors of the graph. load_memory reads the working-dir
    copy first, so pinning only the encoded one leaves the old status to win
    the next read."""
    sb = Sandbox(monkeypatch, tmp_path)
    a1, e1, f1, _ = sb.add_project('alpha')
    a2, e2, f2, _ = sb.add_project('beta')
    actual = {e1: a1, e2: a2}
    # the sandbox cannot resolve an encoded folder back to a fake drive; this
    # is the same seam production resolves through paths.find_actual_path
    monkeypatch.setattr(conventions, '_actual',
                        lambda enc, folder: actual.get(enc, ''))
    text = 'never edit generated files by hand'
    for a, f in ((a1, f1), (a2, f2)):
        m = memory._empty(); m['entities'] = [_pref(text, status='pending')]
        memory.save_memory(a, f, m)
    assert conventions.collect_conventions() == []      # pending, only 2 projects

    assert conventions.pin_convention(text) == 2        # one lesson per project
    assert any('generated files' in r['text']
               for r in conventions.collect_conventions())
    for a, f in ((a1, f1), (a2, f2)):
        assert memory.load_memory(a, f)['entities'][0]['status'] == 'pinned'
        # and the encoded mirror agrees — otherwise the two disagree forever
        assert memory.load_memory('', f)['entities'][0]['status'] == 'pinned'


def test_lessons_under_a_second_account_are_collected(monkeypatch, tmp_path):
    """The scan read one account's projects dir, bound at import. A rule
    learned on the account you were not using could never reach the count."""
    sb = Sandbox(monkeypatch, tmp_path)
    a1, e1, f1, _ = sb.add_project('alpha')
    text = 'prefer ripgrep over grep on this machine'
    m = memory._empty(); m['entities'] = [_pref(text)]
    memory.save_memory(a1, f1, m)

    # a second account with its own projects root holding the same lesson
    alt = os.path.join(str(tmp_path), 'alt-account')
    other = os.path.join(alt, 'projects', '-D--code-beta')
    os.makedirs(os.path.join(other, '.archeus', 'memory'), exist_ok=True)
    m2 = memory._empty(); m2['entities'] = [_pref(text + ' always')]
    with open(os.path.join(other, '.archeus', 'memory', 'graph.json'),
              'w', encoding='utf-8') as fh:
        json.dump(m2, fh)
    monkeypatch.setattr('claude_sessions.config.all_config_dirs',
                        lambda: [('default', conventions._c.config_dir),
                                 ('alt', alt)])
    assert any('ripgrep' in r['text'] for r in conventions.collect_conventions())
