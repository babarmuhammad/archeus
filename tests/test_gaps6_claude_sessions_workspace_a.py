"""T-1269: the ten highest-risk uncovered branches of claude_sessions/workspace.py,
source lines 162-228 (_empty_manifest, _migrate, load_manifest, _corrupt,
save_manifest) at worktree d429bf96.

Selected branches and the test that catches each one:
- 192 _migrate: an unknown newer schema must be refused, not relabelled current with
  safe_to_launch trusted (strict xfail, defect at 192).
- 189-191 _migrate: a half-populated old manifest fills absent nested fields and keeps
  recorded hashes, operations and unknown future keys.
- 162-180 _empty_manifest via _migrate: separate migrations never share mutable subtrees.
- 204-206 load_manifest: a top-level list, scalar or null is the _corrupt sentinel.
- 199-206 load_manifest: a corrupt first candidate hides nothing; the second copy is not used.
- 200-208 load_manifest: an unreadable first candidate returns _corrupt, writes and
  moves nothing, and reads no later candidate.
- 209 load_manifest: no candidate gives a fresh independent template and creates no directory.
- 223-224 save_manifest: an interrupted JSON write keeps the previous complete manifest
  (strict xfail, defect at 223: the live file is opened with 'w' before the dump).
- 220-227 save_manifest: a failed first destination falls through to the next candidate;
  all failures return False.
- 224-225 save_manifest: unknown keys and zero or False nested fields round-trip; an
  unserialisable manifest is never reported as saved.

Seams: builtins.open is wrapped only for the one path a test names, and the candidate
paths are real paths under tmp_path. No git, no subprocess, no real home or settings.
"""

import builtins
import errno
import json
import os

import pytest

from claude_sessions import workspace


def _manifest_path(root):
    return os.path.join(str(root), workspace.MANIFEST_DIR, workspace.MANIFEST_NAME)


def _put(root, text):
    p = _manifest_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return p


def test_a_newer_schema_is_refused_not_relabelled_current(tmp_path):
    newer = workspace.SCHEMA_VERSION + 98
    _put(tmp_path, json.dumps({'schema_version': newer, 'safe_to_launch': True,
                               'repo': {'head_sha': 'x'}}))
    got = workspace.load_manifest(str(tmp_path))
    assert got.get('_corrupt') or got['schema_version'] == newer


def test_a_half_populated_old_manifest_fills_gaps_and_keeps_recorded_data():
    old = {'schema_version': 0, 'repo': {'head_sha': 'abc'}, 'file_hashes': {'CLAUDE.md': 'h1'},
           'operations': {'scaffold': {'at': 5}}, 'future_key': {'x': 0}}
    m = workspace._migrate(json.loads(json.dumps(old)))
    assert m['repo'] == {'head_sha': 'abc', 'head_short': '', 'branch': ''}
    assert m['file_hashes'] == {'CLAUDE.md': 'h1'}
    assert m['operations'] == {'scaffold': {'at': 5}}
    assert m['future_key'] == {'x': 0}
    assert m['sessions'] == workspace._empty_manifest()['sessions']
    assert m['schema_version'] == workspace.SCHEMA_VERSION


def test_separate_migrations_do_not_share_default_subtrees():
    a = workspace._migrate({})
    a['repo']['head_sha'] = 'poisoned'
    a['sessions']['range_days'] = 9
    a['source_inputs'].append('x')
    b = workspace._migrate({})
    assert b['repo']['head_sha'] == ''
    assert b['sessions']['range_days'] == 0
    assert b['source_inputs'] == []


@pytest.mark.parametrize('text', ['[1, 2]', '5', 'null', '"text"'])
def test_a_non_object_top_level_is_the_corrupt_sentinel_not_a_safe_empty_manifest(tmp_path, text):
    p = _put(tmp_path, text)
    got = workspace.load_manifest(str(tmp_path))
    assert got.get('_corrupt') is True
    with open(p, encoding='utf-8') as f:
        assert f.read() == text


def test_a_corrupt_first_candidate_does_not_fall_back_to_the_valid_second_copy(tmp_path):
    project = tmp_path / 'project'
    folder = tmp_path / 'folder'
    _put(project, '{"truncated": ')
    _put(folder, json.dumps({'schema_version': workspace.SCHEMA_VERSION,
                             'repo': {'head_sha': 'second'}}))
    got = workspace.load_manifest(str(project), str(folder))
    assert got.get('_corrupt') is True
    assert got['repo']['head_sha'] == ''


def test_an_unreadable_first_candidate_returns_corrupt_and_reads_nothing_else(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    folder = tmp_path / 'folder'
    first = _put(project, json.dumps({'schema_version': workspace.SCHEMA_VERSION}))
    second = _put(folder, json.dumps({'schema_version': workspace.SCHEMA_VERSION,
                                      'repo': {'head_sha': 'second'}}))
    opened = []
    real = builtins.open

    def deny(file, *a, **k):
        name = os.fspath(file)
        opened.append(name)
        if name == first:
            raise PermissionError(errno.EACCES, 'synthetic denial', name)
        return real(file, *a, **k)
    monkeypatch.setattr(builtins, 'open', deny)

    got = workspace.load_manifest(str(project), str(folder))
    assert got.get('_corrupt') is True
    assert second not in opened
    assert os.path.exists(first) and os.path.exists(second)
    assert not [f for f in os.listdir(project / workspace.MANIFEST_DIR) if 'corrupt-' in f]


def test_no_candidate_gives_a_fresh_template_and_creates_nothing(tmp_path):
    project = tmp_path / 'project'
    folder = tmp_path / 'folder'
    a = workspace.load_manifest(str(project), str(folder))
    b = workspace.load_manifest(str(project), str(folder))
    assert a == workspace._empty_manifest()
    a['repo']['head_sha'] = 'changed'
    assert b['repo']['head_sha'] == ''
    assert not project.exists()
    assert not folder.exists()


def test_an_interrupted_write_keeps_the_previous_complete_manifest(tmp_path):
    good = workspace._empty_manifest()
    good['repo']['head_sha'] = 'kept'
    assert workspace.save_manifest(str(tmp_path), good)

    broken = workspace._empty_manifest()
    broken['unserialisable'] = object()
    assert workspace.save_manifest(str(tmp_path), broken) is False

    got = workspace.load_manifest(str(tmp_path))
    assert got.get('_corrupt') is not True
    assert got['repo']['head_sha'] == 'kept'


def _block_dir(manifest_path):
    # a plain file where the manifest folder should be: makedirs fails, the write never starts
    os.makedirs(os.path.dirname(os.path.dirname(manifest_path)), exist_ok=True)
    with open(os.path.dirname(manifest_path), 'w', encoding='utf-8') as f:
        f.write('not a folder')


def test_a_failed_first_destination_falls_through_and_all_failures_report_false(tmp_path):
    project = tmp_path / 'project'
    folder = tmp_path / 'folder'
    other = tmp_path / 'other'
    first = _manifest_path(project)
    second = _manifest_path(folder)
    m = workspace._empty_manifest()
    m['repo']['head_sha'] = 'second'

    _block_dir(first)
    assert workspace.save_manifest(str(project), m, str(folder)) is True
    assert not os.path.exists(first)
    with open(second, encoding='utf-8') as f:
        assert json.load(f)['repo']['head_sha'] == 'second'

    _block_dir(_manifest_path(other))
    assert workspace.save_manifest(str(other), m, str(project)) is False
    assert not os.path.exists(_manifest_path(other))


def test_unknown_keys_and_zero_false_fields_round_trip_and_unserialisable_is_never_saved(tmp_path):
    m = workspace._empty_manifest()
    m['sessions'] = {'analyzed_count': 0, 'first_ts': 0, 'last_ts': 0, 'range_days': 0}
    m['safe_to_launch'] = False
    m['freshness_score'] = 0
    m['x_future'] = {'flag': False, 'n': 0, 'items': []}
    assert workspace.save_manifest(str(tmp_path), m) is True
    got = workspace.load_manifest(str(tmp_path))
    for key in ('sessions', 'safe_to_launch', 'freshness_score', 'x_future'):
        assert got[key] == m[key]

    assert workspace.save_manifest(str(tmp_path / 'fresh'), {'bad': object()}) is False
