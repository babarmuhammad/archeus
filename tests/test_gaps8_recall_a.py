"""T-1337: the highest-risk uncovered branches of claude_sessions/recall.py
lines 332-393 inclusive, at tip 6b1a30b8. Fail-closed and denial first, then
boundaries, then error paths.

Selected branches (source line, probe):
1. fold_hits 375-382, 389-393  unreadable sidecar: False, sidecar kept, graph unchanged
2. fold_hits 372-373           no sidecar: False, graph unchanged, nothing created
3. hits_pending 347-350        missing sidecar reads as 0
4. _log_hits 355-356           no names: no sidecar created
5. _log_hits 363-364           write failure swallowed, the prompt is not blocked (control)
6. _log_hits 362               None and blank names are not written
7. _log_hits 361, hits_pending 348  appends accumulate; blank lines do not count
8. fold_hits 384-386           counts add to existing hits
9. fold_hits 387-388           lesson gets last_used = session_counter; other types do not
10. _log_hits 362              PREMISE: a newline in an entity name splits it into two counted names
"""

import builtins
import copy
import os

import pytest

from claude_sessions import recall


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    p = str(tmp_path / 'mem' / recall.HITS_LOG)
    monkeypatch.setattr(recall, 'hits_log_path', lambda project_path, proj_folder: p)
    return p


def _entity(name, type_='component', **extra):
    e = {'name': name, 'type': type_, 'hits': 0}
    e.update(extra)
    return e


def _mem(*entities, counter=0):
    return {'entities': list(entities), 'session_counter': counter}


def test_fold_keeps_an_unreadable_sidecar_and_the_graph(sidecar, monkeypatch):
    recall._log_hits('', '', ['Parser'])
    real_open = builtins.open

    def unreadable(path, *args, **kwargs):
        if os.fspath(path) == sidecar:
            raise OSError('unreadable')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(recall, 'open', unreadable, raising=False)
    mem = _mem(_entity('Parser'))
    assert recall.fold_hits('', '', mem) is False
    assert mem['entities'][0]['hits'] == 0
    assert os.path.isfile(sidecar)


def test_fold_without_a_sidecar_changes_nothing(sidecar):
    mem = _mem(_entity('Parser', hits=3), counter=9)
    before = copy.deepcopy(mem)
    assert recall.fold_hits('', '', mem) is False
    assert mem == before
    assert not os.path.exists(sidecar)


def test_hits_pending_is_zero_without_a_sidecar(sidecar):
    assert recall.hits_pending('', '') == 0


def test_no_names_creates_no_sidecar(sidecar):
    recall._log_hits('', '', [])
    recall._log_hits('', '', None)
    assert not os.path.exists(sidecar)
    assert not os.path.isdir(os.path.dirname(sidecar))


def test_a_failed_sidecar_write_is_swallowed(tmp_path, monkeypatch):
    blocker = tmp_path / 'blocker'
    blocker.write_text('a file where a folder should be', encoding='utf-8')
    monkeypatch.setattr(recall, 'hits_log_path',
                        lambda project_path, proj_folder: str(blocker / 'mem' / recall.HITS_LOG))
    recall._log_hits('', '', ['Parser'])
    assert blocker.read_text(encoding='utf-8') == 'a file where a folder should be'


def test_none_and_blank_names_are_not_written(sidecar):
    recall._log_hits('', '', [None, '', 'Parser', '', None])
    with open(sidecar, encoding='utf-8') as f:
        assert f.read() == 'Parser\n'


def test_prompts_append_and_only_non_blank_lines_count(sidecar):
    recall._log_hits('', '', ['Parser', 'Lexer'])
    recall._log_hits('', '', ['Parser'])
    assert recall.hits_pending('', '') == 3
    recall._log_hits('', '', [' '])
    assert recall.hits_pending('', '') == 3


def test_fold_adds_counts_to_existing_hits(sidecar):
    recall._log_hits('', '', ['Parser', 'Parser'])
    mem = _mem(_entity('Parser', hits=4))
    assert recall.fold_hits('', '', mem) is True
    assert mem['entities'][0]['hits'] == 6
    assert not os.path.exists(sidecar)


def test_fold_stamps_last_used_on_lessons_only(sidecar):
    recall._log_hits('', '', ['Use small commits', 'Parser'])
    lesson = _entity('Use small commits', 'lesson')
    component = _entity('Parser', 'component')
    mem = _mem(lesson, component, counter=7)
    recall.fold_hits('', '', mem)
    assert lesson['hits'] == 1 and lesson['last_used'] == 7
    assert component['hits'] == 1 and 'last_used' not in component


def test_entity_name_with_a_newline_gets_its_hit(sidecar):
    name = 'Parser\nHelper'
    recall._log_hits('', '', [name])
    mem = _mem(_entity(name))
    recall.fold_hits('', '', mem)
    assert mem['entities'][0]['hits'] == 1
