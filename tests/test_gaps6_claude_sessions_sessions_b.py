"""T-1287: claude_sessions/sessions.py:295-432 at 6bbd3b44; same current slice.

Selected probes (not coverage measurements), closest assertion and gap:
304 traversal refusal: test_sessions.py:95 roundtrips only valid sid.
396 corrupt update preservation: :95 does not corrupt provider metadata.
432 interrupted add-dir save: :102 roundtrips extra paths without faults.
309 selected deletion: :95 has no sibling or missing-file deletion check.
378 agent merge/False propagation: test_tui_memory.py:65 has no sibling/False.
398 explicit direct provider: test_sessions.py:45 tests message shape only.
414 exact recorded identity: test_providers.py:628 does not test prefix collision
    or assert inference is never called for recorded sessions.
389 wrong JSON types: test_tui_memory.py:58 checks broken tags only, not all readers.
337 edit tool composition: test_tui_memory.py:27 has Edit/Write counts but no
    MultiEdit, notebook paths or malformed outer content.
425 add-dir comments: test_sessions.py:102 tests extra-paths, not add-dirs.
"""

import builtins
import io
import json
import os

import pytest

from claude_sessions import sessions as s


def test_name_traversal_refused_before_open(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(s, 'open', lambda p, *a, **k: opened.append(p) or io.StringIO(),
                        raising=False)
    try:
        s.save_name(str(tmp_path / 'project'), os.path.join('..', 'other'), 'name')
    except ValueError:
        pass
    assert opened == []


def test_corrupt_provider_update_refuses_sibling_loss(monkeypatch, tmp_path):
    p = tmp_path / 'session-providers.json'
    old = b'{"sibling": "remote", "broken":'
    p.write_bytes(old)
    writes = []
    monkeypatch.setattr(s._c, 'write_json_atomic', lambda *a: writes.append(a) or True)
    assert s.save_session_provider(str(tmp_path), 'new', 'direct') is False
    assert writes == [] and p.read_bytes() == old


def test_interrupted_add_dir_save_preserves_prior_bytes(monkeypatch, tmp_path):
    p = tmp_path / 'add-dirs.txt'
    p.write_bytes(b'old-directory\n')

    def interrupted(*a):
        raise OSError('replace interrupted')

    monkeypatch.setattr(s._c.os, 'replace', interrupted)
    assert s.save_add_dirs(str(tmp_path), ['new-directory']) is False
    assert p.read_bytes() == b'old-directory\n'
    assert [x.name for x in tmp_path.iterdir()] == ['add-dirs.txt']


def test_empty_name_deletes_selected_once_not_sibling(monkeypatch, tmp_path):
    selected = tmp_path / 'one.name'
    sibling = tmp_path / 'two.name'
    selected.write_text('one', encoding='utf-8')
    sibling.write_text('two', encoding='utf-8')
    removed = []
    real_remove = os.remove

    def remove(path):
        removed.append(path)
        real_remove(path)

    monkeypatch.setattr(s.os, 'remove', remove)
    s.save_name(str(tmp_path), 'one', '')
    s.save_name(str(tmp_path), 'one', '')
    assert removed == [str(selected)]
    assert sibling.read_text(encoding='utf-8') == 'two'


@pytest.mark.parametrize('refs', [[], ['replacement']])
def test_agent_update_preserves_other_refs_and_false(monkeypatch, tmp_path, refs):
    (tmp_path / 'session-agents.json').write_text(
        json.dumps({'one': ['old'], '__new__': ['shared'], 'two': ['other']}), encoding='utf-8')
    writes = []
    monkeypatch.setattr(s._c, 'write_json_atomic', lambda *a: writes.append(a) or False)
    assert s.save_session_agents(str(tmp_path), 'one', refs) is False
    expected = {'__new__': ['shared'], 'two': ['other']}
    if refs:
        expected['one'] = refs
    assert writes == [(str(tmp_path / 'session-agents.json'), expected)]


def test_direct_provider_is_record_not_deletion(monkeypatch, tmp_path):
    (tmp_path / 'session-providers.json').write_text(
        '{"one":"remote","two":"other"}', encoding='utf-8')
    writes = []
    monkeypatch.setattr(s._c, 'write_json_atomic', lambda *a: writes.append(a) or False)
    assert s.save_session_provider(str(tmp_path), 'one', None) is False
    assert writes == [(str(tmp_path / 'session-providers.json'), {'one': '', 'two': 'other'})]


def test_exact_provider_record_prevents_inference(monkeypatch):
    inferred = []
    monkeypatch.setattr(s, '_used_provider', lambda st: inferred.append(st) or True)
    rec = {'s': '', 's-extra': 'remote'}
    assert s.resolve_provider(rec, 's', {}) is False
    assert s.resolve_provider(rec, 's-extra', {}) is True
    assert inferred == []
    state = {'models': ['remote']}
    assert s.resolve_provider(rec, 's-ex', state) is True
    assert inferred == [state]


@pytest.mark.parametrize('payload', ['[]', 'null', '"value"', '{broken'])
def test_bad_metadata_reads_leave_bytes_untouched(monkeypatch, tmp_path, payload):
    monkeypatch.setattr(s._c, 'write_json_atomic', lambda *a: pytest.fail('reader wrote'))
    for filename, reader in [('tags.json', s.load_tags),
                             ('session-agents.json', s.load_session_agents),
                             ('session-providers.json', s.load_session_providers)]:
        p = tmp_path / filename
        p.write_text(payload, encoding='utf-8')
        assert reader(str(tmp_path)) == {}
        assert p.read_text(encoding='utf-8') == payload


def test_changed_files_counts_only_supported_tool_blocks(monkeypatch, tmp_path):
    a, b = str(tmp_path / 'a'), str(tmp_path / 'b')
    blocks = [{'type': 'tool_use', 'name': n, 'input': {'file_path': a}}
              for n in ('Edit', 'Write', 'MultiEdit', 'Read', 'Bash')]
    blocks += [None, {'type': 'text', 'file_path': a},
               {'type': 'tool_use', 'name': 'NotebookEdit', 'input': {'notebook_path': b}}]
    calls = []

    def records(path, **kwargs):
        calls.append((path, kwargs))
        return iter([{'message': {'content': 'not a block list'}},
                     {'message': {'content': blocks}}])

    monkeypatch.setattr(s._t, 'iter_json', records)
    assert s.session_changed_files('synthetic') == [(a, 3), (b, 1)]
    assert calls == [('synthetic', {'prefilter': ('file_path', 'notebook_path')})]


def test_add_dirs_exact_comments_blank_and_no_creation(tmp_path):
    missing = tmp_path / 'missing'
    assert s.load_add_dirs(None) == []
    assert s.load_add_dirs(str(missing)) == [] and not missing.exists()
    p = tmp_path / 'add-dirs.txt'
    raw = b'#comment\n\n  \nfirst\n  #indented\n second \n'
    p.write_bytes(raw)
    assert s.load_add_dirs(str(tmp_path)) == ['first', '#indented', 'second']
    assert p.read_bytes() == raw
