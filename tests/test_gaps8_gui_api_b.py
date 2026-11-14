"""T-1346 — highest-risk uncovered branches of claude_sessions/gui_api.py
lines 2247-2319 (tip 6b1a30b8; re-located at the worktree tip, same lines):
_harness_homes_post and api_accounts_post.

Candidate list, denial and fail-closed first:
 1. 2259-2261  rename to empty, the harness label or a taken name: 'name unavailable', nothing saved
 2. 2274-2276  harness switch refused: no settings change, no save
 3. 2289-2293  harness call saves settings only when its inner result is ok
 4. 2264-2266  harness remove drops the row only, deletes no directory (control)
 5. 2250       non-dict rows are dropped from the homes list before any change
 6. 2252-2256  harness add defaults the dir under USERPROFILE and replaces a same-name row
 7. 2305-2307  Claude rename to 'default' or a taken name is refused
 8. 2312-2315  Claude remove clears claude_config_dir only when it pointed at the removed dir
 9. 2300-2302  PREMISE: switch to an unknown account name sets claude_config_dir to '' and returns ok
10. 2295-2296  PREMISE: add with an empty name creates a '.claude-' home instead of refusing

Closest existing tests: tests/test_gui_parity.py test_accounts_add_rename_remove
(Claude rename to 'default' only, over HTTP) and tests/test_gaps3_claude_sessions_accounts.py
(the TUI twin of premises 9 and remove-selection, at accounts.py, not gui_api.py).
Neither reaches the harness branches of _harness_homes_post.

Seams: config.load_settings and config.save_settings are replaced by an in-memory
dict, config._USERPROFILE points at tmp_path. No server, no real home, no subprocess,
no network.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import config
from claude_sessions import gui_api
from claude_sessions import harnesses as _harnesses


@pytest.fixture()
def store(monkeypatch, tmp_path):
    state = {'s': {'claude_config_dir': '', 'accounts': [], 'homes': {}}, 'saved': []}

    def load():
        return copy.deepcopy(state['s'])

    def save(st):
        state['saved'].append(copy.deepcopy(st))
        state['s'] = copy.deepcopy(st)

    monkeypatch.setattr(config, 'load_settings', load)
    monkeypatch.setattr(config, 'save_settings', save)
    monkeypatch.setattr(config, '_USERPROFILE', str(tmp_path))
    return state


HID = 'codex'
LABEL = _harnesses.descriptor(HID)['label']


# 2259-2261 — rename refused three ways, nothing persisted
def test_harness_rename_to_empty_label_or_taken_name_saves_nothing(store):
    store['s']['homes'] = {HID: [{'name': 'work', 'dir': '/x/a'},
                                 {'name': 'other', 'dir': '/x/b'}]}
    before = copy.deepcopy(store['s'])
    for new in ('', LABEL, 'other'):
        r = gui_api.api_accounts_post({}, {'hid': HID, 'action': 'rename',
                                           'name': 'work', 'new': new})
        assert r == {'ok': False, 'error': 'name unavailable'}, new
    assert store['s'] == before
    assert store['saved'] == []


# 2274-2276 — a harness switch is refused, no change and no save
def test_harness_switch_is_refused_without_setting_or_save(store):
    store['s']['claude_config_dir'] = '/x/claude'
    before = copy.deepcopy(store['s'])
    r = gui_api.api_accounts_post({}, {'hid': HID, 'action': 'switch', 'name': 'work'})
    assert r['ok'] is False and LABEL in r['error']
    assert store['s'] == before
    assert store['saved'] == []


# 2289-2293 — a harness call saves exactly once on success and never on refusal
def test_harness_call_saves_only_when_inner_result_is_ok(store, tmp_path):
    d = str(tmp_path / 'codex-work')
    r = gui_api.api_accounts_post({}, {'hid': HID, 'action': 'add',
                                       'name': 'work', 'dir': d})
    assert r == {'ok': True}
    assert len(store['saved']) == 1
    assert store['s']['homes'][HID] == [{'name': 'work', 'dir': d}]

    r = gui_api.api_accounts_post({}, {'hid': HID, 'action': 'rename',
                                       'name': 'work', 'new': 'work'})
    assert r == {'ok': False, 'error': 'name unavailable'}
    assert len(store['saved']) == 1


# 2264-2266 — remove drops the row and leaves the directory on disk
def test_harness_remove_drops_row_and_keeps_directory(store, tmp_path):
    kept = tmp_path / 'codex-work'
    kept.mkdir()
    (kept / 'auth.txt').write_text('x', encoding='utf-8')
    store['s']['homes'] = {HID: [{'name': 'work', 'dir': str(kept)},
                                 {'name': 'other', 'dir': '/x/other'}]}
    r = gui_api.api_accounts_post({}, {'hid': HID, 'action': 'remove', 'name': 'work'})
    assert r == {'ok': True}
    assert store['s']['homes'][HID] == [{'name': 'other', 'dir': '/x/other'}]
    assert (kept / 'auth.txt').read_text(encoding='utf-8') == 'x'


# 2250 — rows that are not dicts never survive a save
def test_harness_rows_that_are_not_dicts_are_dropped(store, tmp_path):
    store['s']['homes'] = {HID: ['junk', None, {'name': 'a', 'dir': '/x/a'}]}
    gui_api.api_accounts_post({}, {'hid': HID, 'action': 'add',
                                   'name': 'b', 'dir': str(tmp_path / 'b')})
    rows = store['s']['homes'][HID]
    assert rows == [{'name': 'a', 'dir': '/x/a'},
                    {'name': 'b', 'dir': str(tmp_path / 'b')}]


# 2252-2256 — add without a dir defaults under USERPROFILE; same name replaces
def test_harness_add_defaults_dir_and_replaces_same_name_row(store, tmp_path):
    store['s']['homes'] = {HID: [{'name': 'work', 'dir': '/x/old'}]}
    r = gui_api.api_accounts_post({}, {'hid': HID, 'action': 'add', 'name': 'work'})
    assert r == {'ok': True}
    default_dir = str(tmp_path / ('.%s-work' % HID))
    assert os.path.isdir(default_dir)
    assert store['s']['homes'][HID] == [{'name': 'work', 'dir': default_dir}]


# 2305-2307 — Claude rename to 'default' or a taken name is refused
def test_claude_rename_to_default_or_taken_name_is_refused(store):
    store['s']['accounts'] = [{'name': 'work', 'dir': '/x/w'},
                              {'name': 'other', 'dir': '/x/o'}]
    before = copy.deepcopy(store['s'])
    for new in ('default', 'other'):
        r = gui_api.api_accounts_post({}, {'action': 'rename', 'name': 'work', 'new': new})
        assert r == {'ok': False, 'error': 'name unavailable'}, new
    assert store['s'] == before
    assert store['saved'] == []


# 2312-2315 — Claude remove clears the selection only when it pointed at the removed dir
def test_claude_remove_clears_selection_only_when_it_pointed_at_removed_dir(store, tmp_path):
    w = str(tmp_path / 'acc-w')
    o = str(tmp_path / 'acc-o')
    store['s'] = {'claude_config_dir': w, 'accounts': [{'name': 'work', 'dir': w},
                                                       {'name': 'other', 'dir': o}],
                  'homes': {}}
    gui_api.api_accounts_post({}, {'action': 'remove', 'name': 'work'})
    assert store['s']['claude_config_dir'] == ''
    assert store['s']['accounts'] == [{'name': 'other', 'dir': o}]

    store['s'] = {'claude_config_dir': o, 'accounts': [{'name': 'work', 'dir': w},
                                                       {'name': 'other', 'dir': o}],
                  'homes': {}}
    gui_api.api_accounts_post({}, {'action': 'remove', 'name': 'work'})
    assert store['s']['claude_config_dir'] == o


# 2300-2302 — PREMISE: an unknown name must not silently switch to the default
@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/gui_api.py:2300-2302: switch to an unknown account name sets "
    "claude_config_dir to '' and returns ok:True instead of refusing"))
def test_switch_to_unknown_account_is_refused(store, tmp_path):
    w = str(tmp_path / 'acc-w')
    store['s']['claude_config_dir'] = w
    store['s']['accounts'] = [{'name': 'work', 'dir': w}]
    r = gui_api.api_accounts_post({}, {'action': 'switch', 'name': 'ghost'})
    assert r.get('ok') is False
    assert store['s']['claude_config_dir'] == w


# 2295-2296 — PREMISE: add with an empty name must refuse, not create '.claude-'
@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/gui_api.py:2295-2296: add with an empty name creates a "
    "'.claude-' home directory and persists a nameless row instead of refusing"))
def test_add_with_empty_name_refuses_and_creates_nothing(store, tmp_path):
    r = gui_api.api_accounts_post({}, {'action': 'add', 'name': ''})
    assert r.get('ok') is False
    assert not os.path.exists(str(tmp_path / '.claude-'))
    assert store['saved'] == []
