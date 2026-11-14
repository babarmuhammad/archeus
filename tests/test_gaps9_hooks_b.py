"""T-1349 · highest-risk test gaps in claude_sessions/hooks.py 1287-1318.

Slice: `_toggle_or_remove` (1287-1318) at tip 10d688c0, read again in the
worktree at pv20-fx87e. Selected branches, ranked (denial first, then
boundaries, then error paths):

 1. 1293-1294 — menu answers None, 'cancel' or an unknown value: no toggle,
    label, remove, confirm or flash happens.
 2. 1315-1316 — remove declined at confirm(danger=True): remove_hook never runs.
 3. 1317-1318 — remove that fails to write flashes 'Write failed', never
    'Hook removed'. The failure flash carries ok=False.
 4. 1295-1296 — toggle direction: state 'on' passes enabled False, 'off' True.
 5. 1296-1298 — toggle write failure flashes 'Write failed' once, no second
    action. The failure flash carries ok=False.
 6. 1287-1289 — malformed selector (no ':', a non-integer index) raises
    ValueError before any menu opens.
 7. 1299-1304 — label with state 'off' reads hooks_disabled; an index past the
    block end returns without a prompt or set_label.
 8. 1308-1312 — label defaults fall back to _hook_label and category_of; a
    blank name is saved as '' through set_label only. ESC on the
    Name or Category prompt (None from ui.text_input) cancels without saving.
 9. 1317 — remove with state 'off' passes enabled False, so the disabled block
    is the one that loses the entry.
10. 1305-1306 — the label path reads command keys from the selected entry only;
    another event's index is never used.

Seams: hooks.menu, hooks.text_input, hooks.confirm, hooks.flash,
hooks.set_hook_enabled, hooks.remove_hook, hooks.set_label, hooks._load and
hooks.label_of are recording fakes. No TUI, no real config, no subprocess.
"""

import copy
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import hooks

A = {'hooks': [{'type': 'command', 'command': 'echo alpha'}]}
B = {'hooks': [{'type': 'command', 'command': 'echo beta'}]}
C = {'hooks': [{'type': 'command', 'command': 'echo gamma'}]}

CFG = 'synthetic-cfg'


@pytest.fixture
def rig(monkeypatch):
    r = SimpleNamespace(log=[], menu_answer=None, texts=[], confirm_answer=True,
                        enabled_ok=True, removed_ok=True, doc={}, label_row={})

    def menu(items, title, **kw):
        r.log.append(('menu', title, [v for _, v in items]))
        return r.menu_answer

    def text_input(prompt, default=''):
        r.log.append(('text', prompt, default))
        if not r.texts:
            raise AssertionError('unexpected prompt: %s' % prompt)
        return r.texts.pop(0)

    def confirm(question, danger=False, **kw):
        r.log.append(('confirm', question, danger))
        return r.confirm_answer

    def flash(msg, ok=True, secs=0.8):
        r.log.append(('flash', msg, ok))

    def set_hook_enabled(event, index, enabled, cfgdir=None):
        r.log.append(('enable', event, index, enabled, cfgdir))
        return r.enabled_ok

    def remove_hook(event, index, enabled=True, cfgdir=None):
        r.log.append(('remove', event, index, enabled, cfgdir))
        return r.removed_ok

    def set_label(event, cmds, name=None, cat=None):
        r.log.append(('label', event, list(cmds), name, cat))
        return True

    def label_of(event, cmds):
        r.log.append(('label_of', event, list(cmds)))
        return dict(r.label_row)

    monkeypatch.setattr(hooks, 'menu', menu)
    monkeypatch.setattr(hooks, 'text_input', text_input)
    monkeypatch.setattr(hooks, 'confirm', confirm)
    monkeypatch.setattr(hooks, 'flash', flash)
    monkeypatch.setattr(hooks, 'set_hook_enabled', set_hook_enabled)
    monkeypatch.setattr(hooks, 'remove_hook', remove_hook)
    monkeypatch.setattr(hooks, 'set_label', set_label)
    monkeypatch.setattr(hooks, 'label_of', label_of)
    monkeypatch.setattr(hooks, '_load', lambda cfgdir=None: copy.deepcopy(r.doc))
    return r


def _effects(rig):
    return [e for e in rig.log if e[0] in ('enable', 'remove', 'label', 'confirm', 'flash')]


def _prompts(rig):
    return [e for e in rig.log if e[0] == 'text']


def _flashes(rig):
    return [e for e in rig.log if e[0] == 'flash']


@pytest.mark.parametrize('answer', [None, 'cancel', 'bogus', ''])
def test_menu_refusal_touches_nothing(rig, answer):
    rig.menu_answer = answer
    rig.doc = {'hooks': {'Stop': [A]}}
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert rig.log == [('menu', 'HOOK', ['toggle', 'label', 'remove', 'cancel'])]


def test_declined_remove_never_calls_remove_hook(rig):
    rig.menu_answer = 'remove'
    rig.confirm_answer = False
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert ('confirm', 'Remove this hook?', True) in rig.log
    assert not [e for e in rig.log if e[0] == 'remove']
    assert _flashes(rig) == []


@pytest.mark.parametrize('removed, message', [(True, 'Hook removed'), (False, 'Write failed')])
def test_remove_flashes_the_outcome_of_the_write(rig, removed, message):
    rig.menu_answer = 'remove'
    rig.removed_ok = removed
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert _flashes(rig)[-1][:2] == ('flash', message)


def test_remove_write_failure_is_flashed_as_a_failure(rig):
    rig.menu_answer = 'remove'
    rig.removed_ok = False
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert _flashes(rig) == [('flash', 'Write failed', False)]


@pytest.mark.parametrize('state, enabled', [('on', False), ('off', True)])
def test_toggle_maps_the_state_to_the_opposite_direction(rig, state, enabled):
    rig.menu_answer = 'toggle'
    hooks._toggle_or_remove(state + ':PreToolUse:2', CFG)
    assert _effects(rig) == [('enable', 'PreToolUse', 2, enabled, CFG),
                             ('flash', 'Toggled', True)]


def test_toggle_write_failure_flashes_once_and_stops(rig):
    rig.menu_answer = 'toggle'
    rig.enabled_ok = False
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert _effects(rig) == [('enable', 'Stop', 0, False, CFG),
                             ('flash', 'Write failed', False)]


@pytest.mark.parametrize('selector', ['Stop', 'on:Stop', 'on:Stop:x', 'on:Stop:', 'on:Stop:1:2'])
def test_malformed_selector_raises_before_the_menu(rig, selector):
    with pytest.raises(ValueError):
        hooks._toggle_or_remove(selector, CFG)
    assert rig.log == []


def test_label_off_state_reads_the_disabled_block(rig):
    rig.menu_answer = 'label'
    rig.doc = {'hooks': {'Stop': [A]}, 'hooks_disabled': {'Stop': [B]}}
    rig.texts = ['', '']
    hooks._toggle_or_remove('off:Stop:0', CFG)
    assert _prompts(rig)[0] == ('text', 'Name:', hooks._hook_label(B, 'Stop'))
    assert hooks._hook_label(B, 'Stop') != hooks._hook_label(A, 'Stop')


def test_label_index_past_the_block_end_returns_quietly(rig):
    rig.menu_answer = 'label'
    rig.doc = {'hooks': {'Stop': [A]}}
    hooks._toggle_or_remove('on:Stop:1', CFG)
    assert rig.log == [('menu', 'HOOK', ['toggle', 'label', 'remove', 'cancel'])]


def test_label_defaults_fall_back_to_the_hook_and_its_category(rig):
    rig.menu_answer = 'label'
    rig.doc = {'hooks': {'Stop': [A]}}
    rig.texts = ['named', 'filed']
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert _prompts(rig)[0] == ('text', 'Name:', hooks._hook_label(A, 'Stop'))
    assert _prompts(rig)[1] == ('text', 'Category:', hooks.category_of(A, 'Stop'))


def test_label_saved_values_override_the_defaults(rig):
    rig.menu_answer = 'label'
    rig.doc = {'hooks': {'Stop': [A]}}
    rig.label_row = {'name': 'mine', 'cat': 'Mine'}
    rig.texts = ['mine', 'Mine']
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert _prompts(rig)[0] == ('text', 'Name:', 'mine')
    assert _prompts(rig)[1] == ('text', 'Category:', 'Mine')


def test_blank_name_is_saved_as_empty_through_set_label_only(rig):
    rig.menu_answer = 'label'
    rig.doc = {'hooks': {'Stop': [A]}}
    rig.texts = ['', 'Filed']
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert _effects(rig) == [('label', 'Stop', hooks._cmd_keys(A), '', 'Filed'),
                             ('flash', 'Saved', True)]


def test_escape_on_the_name_prompt_leaves_the_saved_label_alone(rig):
    rig.menu_answer = 'label'
    rig.doc = {'hooks': {'Stop': [A]}}
    rig.label_row = {'name': 'mine', 'cat': 'Mine'}
    rig.texts = [None, 'Mine']
    hooks._toggle_or_remove('on:Stop:0', CFG)
    assert not [e for e in rig.log if e[0] == 'label']


def test_remove_in_the_off_state_targets_the_disabled_block(rig):
    rig.menu_answer = 'remove'
    hooks._toggle_or_remove('off:Stop:0', CFG)
    assert _effects(rig) == [('confirm', 'Remove this hook?', True),
                             ('remove', 'Stop', 0, False, CFG),
                             ('flash', 'Hook removed', True)]


def test_label_reads_command_keys_from_the_selected_entry_only(rig):
    rig.menu_answer = 'label'
    rig.doc = {'hooks': {'PreToolUse': [C], 'Stop': [A]}}
    rig.texts = ['', '']
    hooks._toggle_or_remove('on:Stop:0', CFG)
    keys = hooks._cmd_keys(A)
    assert ('label_of', 'Stop', keys) in rig.log
    assert ('label', 'Stop', keys, '', '') in rig.log
    assert not [e for e in rig.log if e[0] in ('label_of', 'label') and e[2] == hooks._cmd_keys(C)]
