"""T-1178 · highest-risk uncovered branches of `claude_sessions/hooks.py` 651-942.

Card T-1178, tip 56d53504, slice `claude_sessions/hooks.py:651-942` inclusive.
Definitions and imports outside the slice (`_is_ours`, `jsonstore.load`,
`config.write_json_atomic`, `config.all_config_dirs`, `TEMPLATES`) are read-only
context; every asserted branch sits inside the slice, including the two
accessors whose bodies cross the endpoints. The ten final selected branches, in
`verify` order (fail-closed / denial first, then boundaries, then error paths):

 1. 651-652 + 678-679 + 692 — a non-list `hooks.StopFailure` is refused by
    `install_limit_hook` (False) and reported clean by `uninstall_limit_hook`
    (True) with ZERO writes, so a malformed block can never be rewritten empty.
 2. 742 — `_load(..., expect=dict)`: a settings.json holding valid JSON of the
    WRONG type is quarantined by `jsonstore` before `install_limit_hook`
    read-modify-writes it, so the user's file survives as `<name>.corrupt-<ts>`.
 3. 683-684 + 692 + 697-699 — a LIVE third-party `limit_hook.py` is not ours:
    `limit_hook_installed` stays False, `uninstall_limit_hook` leaves it
    byte-identical and writes nothing, and our own entry is added beside it.
 4. 684-689 — `uninstall_limit_hook` with OURS and a foreign sibling inside the
    SAME entry keeps the entry and the sibling (`entry['hooks'] = kept`) instead
    of removing the whole entry.
 5. 712 + 720 + 733 + 746 — `across_accounts`/`account_dirs`: the fan-out walks
    the deduped account list once per DISTINCT dir, hands each call its own
    `cfgdir`, and never touches the import-bound `settings_path`.
 6. 749-750 — `_count` counts ENTRIES and treats a non-list block value as zero
    rather than counting its characters.
 7. 753-756 + 785-787 + 833-839 — hostile entry/command types: non-dict hooks
    dropped, odd command values stringified, and the snippet boundary at 45/46
    characters.
 8. 861-862 — `_label_key`: `None` and `''` are the same event, two commands are
    never one command, and an empty command list is a distinct key.
 9. 903-913 — `rekey_label` moves the whole row (name AND category), leaves the
    other event's row alone, and refuses to invent a row it did not find.
10. 875-892 — `set_label`: a blank field clears only itself, a row with nothing
    left is dropped rather than stored empty, and no other hook's label moves.

Seams faked before any entrypoint reaches the host: `config.load_settings` /
`config.save_settings` (archeus's own settings, where `hook_labels` live),
`config.all_config_dirs` / `config._USERPROFILE` (account discovery),
`hooks.settings_path` (the cfgdir=None answer, pinned to a decoy inside
tmp_path) and `config.write_json_atomic` (the one writer, spied on). No real
credential is read, no subprocess is started, nothing is written outside
tmp_path, and no test imports another test_gaps3 file.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import config, hooks, jsonstore        # noqa: E402

# ── seams ────────────────────────────────────────────────────

DECOY_NAME = 'DECOY-settings.json'


def _wire(monkeypatch, tmp_path):
    """Spy the one writer, and pin every fallback path inside tmp_path.

    `hooks._save` is the only writer of Claude Code's settings.json and it
    funnels through `config.write_json_atomic`, so the recorded call list is
    what makes "refused" distinguishable from "refused and then truncated the
    file anyway". `hooks.settings_path` (the cfgdir=None answer, bound at
    import) is aimed at a decoy file: a lost `cfgdir` shows up as a file that
    must not exist rather than as a write into the real ~/.claude.
    """
    writes = []
    real = config.write_json_atomic
    inside = os.path.normcase(os.path.abspath(str(tmp_path))) + os.sep

    def spy(path, obj, *a, **kw):
        ap = os.path.normcase(os.path.abspath(str(path)))
        # Only this test's own tree is of interest: a background writer from an
        # earlier test (the failover proxy, the stats cache) also funnels through
        # here, into archeus's own session state directory, and must not be
        # mistaken for a write this test caused.
        if ap.startswith(inside):
            writes.append((ap, obj))
        return real(path, obj, *a, **kw)

    monkeypatch.setattr(config, 'write_json_atomic', spy)
    # archeus-events.jsonl is written beside archeus.json by jsonstore's
    # quarantine report, and `hook_labels` live in that same file
    monkeypatch.setattr(config, 'settings_file', str(tmp_path / 'archeus.json'))
    monkeypatch.setattr(hooks, 'settings_path', str(tmp_path / DECOY_NAME))
    return writes


def _home(tmp_path, name, content='{}'):
    """One fake account home with a seeded settings.json -> (dir, path)."""
    d = tmp_path / name
    d.mkdir()
    p = d / 'settings.json'
    p.write_text(content, encoding='utf-8')
    return str(d), p


def _raw(p):
    with open(str(p), 'rb') as f:
        return f.read()


def _fake_archeus_settings(monkeypatch, initial=None):
    """archeus's own settings (where `hook_labels` live) held in memory.

    Returns the store: `data` is the saved dict, `saves` counts the calls, so a
    function that "found nothing" can be caught actually writing anyway.
    """
    store = {'data': dict(initial or {}), 'saves': 0}

    def load_settings():
        return json.loads(json.dumps(store['data']))

    def save_settings(s):
        store['data'] = json.loads(json.dumps(s))
        store['saves'] += 1
        return True

    monkeypatch.setattr(config, 'load_settings', load_settings)
    monkeypatch.setattr(config, 'save_settings', save_settings)
    return store


def _ours_hook_cmd():
    """The command this installation writes for the rotation hook."""
    return hooks._limit_hook_command()


def _foreign_script(tmp_path, name='limit_hook.py'):
    """A third-party hook script that EXISTS on disk, so `_is_ours` must reject
    it by path rather than by the missing-file rule that covers a moved
    archeus checkout."""
    d = tmp_path / 'company'
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text('# not archeus, and it is alive', encoding='utf-8')
    return str(p)


# ── 1 · fail closed on a malformed StopFailure block ─────────

def test_a_malformed_stopfailure_block_is_refused_both_ways_and_never_rewritten(
        monkeypatch, tmp_path):
    """hooks.py:651-652, 678-679, 692.

    `hooks.StopFailure` written by hand as a bare string (or a dict) is the one
    shape that turns a repair into an erase: `install_limit_hook` would
    `entries.append(...)` straight into it, and `uninstall_limit_hook` would
    iterate its characters. Both guards, plus the `if changed` hinge on the
    final save, are what keep the file — and the `permissions` block Claude
    Code owns — intact.
    """
    writes = _wire(monkeypatch, tmp_path)
    d, p = _home(tmp_path, 'acct', json.dumps(
        {'hooks': {'StopFailure': 'rate_limit'},
         'permissions': {'allow': ['keep-me']}, 'outputStyle': 'x'}))
    before = _raw(p)

    assert hooks.install_limit_hook(cfgdir=d) is False      # 651-652
    assert hooks.uninstall_limit_hook(cfgdir=d) is True      # 678-679
    assert hooks.limit_hook_installed(cfgdir=d) is False
    assert writes == [], 'a refused write still touched settings.json'
    assert _raw(p) == before, 'the malformed block was rewritten, not refused'
    assert json.loads(_raw(p).decode('utf-8'))['permissions']['allow'] == ['keep-me']


# ── 2 · a wrong-typed settings file is moved aside first ─────

def test_a_settings_file_of_the_wrong_type_is_moved_aside_before_the_rewrite(
        monkeypatch, tmp_path):
    """hooks.py:742 (`expect=dict`), reached through `install_limit_hook`.

    `[]` is valid JSON, so a reader that only catches parse errors hands `list`
    to `s.setdefault` (an AttributeError mid-install) or — the destructive
    variant, and the reason `expect` is a parameter at all — a plain `{}`
    default that the following `_save` writes back as the user's whole
    settings.json minus everything they had.
    """
    writes = _wire(monkeypatch, tmp_path)
    original = '[{"hooks": [], "matcher": "rate_limit"}]'
    d, p = _home(tmp_path, 'acct', original)

    assert hooks.install_limit_hook(cfgdir=d) is True

    moved = [n for n in os.listdir(d) if '.corrupt-' in n]
    assert len(moved) == 1, 'the unreadable file was not moved aside'
    assert _raw(os.path.join(d, moved[0])) == original.encode('utf-8'), \
        'the user\'s settings were emptied instead of preserved'
    assert jsonstore.last_corruption.get(os.path.abspath(str(p))) \
        == os.path.join(d, moved[0]), 'the quarantine was never reported'
    now = json.loads(_raw(p).decode('utf-8'))
    assert isinstance(now, dict) and len(now['hooks']['StopFailure']) == 1
    assert [w[0] for w in writes] == [os.path.normcase(os.path.abspath(str(p)))]


# ── 3 · a live foreign limit_hook.py is not ours ─────────────

def test_a_live_foreign_limit_hook_is_never_claimed_and_is_left_alone(
        monkeypatch, tmp_path):
    """hooks.py:683-684, 692, 697-699 (through `_is_ours`, hooks.py:401-411).

    `limit_hook.py` is not a private name. Someone else's hook that still
    resolves on disk must not read as installed (the UI would then offer
    "Remove" for a hook archeus does not own) and must not be deletable:
    `uninstall_limit_hook` has to report True having written NOTHING, and our
    own hook has to land in a SEPARATE entry beside it.
    """
    writes = _wire(monkeypatch, tmp_path)
    theirs = {'type': 'command', 'command': '"python" "%s"' % _foreign_script(tmp_path),
              'timeout': 3}
    foreign_entry = {'matcher': 'rate_limit', 'hooks': [theirs]}
    d, p = _home(tmp_path, 'acct', json.dumps(
        {'hooks': {'StopFailure': [foreign_entry]}, 'permissions': {'allow': ['x']}}))
    before = _raw(p)

    assert hooks.limit_hook_installed(cfgdir=d) is False      # 697-699
    assert hooks.uninstall_limit_hook(cfgdir=d) is True       # 683-684, 692
    assert writes == [] and _raw(p) == before, 'a foreign hook was edited or removed'

    assert hooks.install_limit_hook(cfgdir=d) is True
    after = json.loads(_raw(p).decode('utf-8'))
    entries = after['hooks']['StopFailure']
    assert len(entries) == 2, 'our hook replaced the foreign entry'
    assert entries[0]['hooks'] == [theirs], 'the foreign hook was rewritten'
    assert 'limit_hook.py' in entries[1]['hooks'][0]['command']
    assert _foreign_script(tmp_path) not in entries[1]['hooks'][0]['command']
    assert hooks.limit_hook_installed(cfgdir=d) is True


# ── 4 · uninstall keeps the sibling hooks of the same entry ──

def test_uninstalling_the_limit_hook_keeps_the_foreign_hooks_of_the_same_entry(
        monkeypatch, tmp_path):
    """hooks.py:684-689 — the `kept` non-empty arm (`entry['hooks'] = kept`).

    Claude Code allows several commands under one matcher entry, and a user who
    adds their own command beside ours would have it deleted by the
    entry-removal arm (`entries.remove(entry)`, 689) if the filter ever dropped
    the "some hooks survived" distinction. The surviving sibling must come back
    out byte-identical, with the entry's own `matcher` still on it.
    """
    writes = _wire(monkeypatch, tmp_path)
    ours = {'type': 'command', 'command': _ours_hook_cmd(), 'timeout': 20}
    sibling = {'type': 'command', 'command': '"node.exe" "/opt/theirs/notify.js"',
               'timeout': 5}
    keep_event = {'SessionEnd': [{'hooks': [{'type': 'command',
                                              'command': 'echo bye'}]}]}
    doc = {'hooks': {'StopFailure': [{'matcher': 'rate_limit',
                                      'hooks': [sibling, ours]}], **keep_event}}
    d, p = _home(tmp_path, 'acct', json.dumps(doc))

    assert hooks.limit_hook_installed(cfgdir=d) is True
    assert hooks.uninstall_limit_hook(cfgdir=d) is True

    after = json.loads(_raw(p).decode('utf-8'))
    assert after['hooks']['StopFailure'] == [{'matcher': 'rate_limit',
                                              'hooks': [sibling]}], \
        'the whole entry went with our hook'
    assert after['hooks']['SessionEnd'] == keep_event['SessionEnd']
    assert hooks.limit_hook_installed(cfgdir=d) is False
    assert [w[0] for w in writes] == [os.path.normcase(os.path.abspath(str(p)))]

    assert hooks.uninstall_limit_hook(cfgdir=d) is True       # already gone
    assert len(writes) == 1, 'a no-op uninstall rewrote the file'


# ── 5 · the account fan-out and the import-bound default ─────

def test_the_account_fan_out_walks_the_deduped_list_once_and_only_writes_those_dirs(
        monkeypatch, tmp_path):
    """hooks.py:712, 720, 733, 746 — `account_dirs` / `across_accounts`.

    Two account rows naming ONE folder is the ordinary result of importing
    Claude Code's own account list, and a fan-out that walks it raw calls the
    writer twice against one file (and would report a key that is not an
    account). The other half is 746/712: a call that loses its `cfgdir` falls
    back to `settings_path`, the attribute bound at import — which on a real
    machine is whichever account happened to be active, and is exactly the bug
    this file exists for.
    """
    writes = _wire(monkeypatch, tmp_path)
    default = tmp_path / '.claude'
    shared = tmp_path / 'shared'
    work = tmp_path / 'work'
    for p in (default, shared, work):
        p.mkdir()
    monkeypatch.setattr(config, '_USERPROFILE', str(tmp_path))
    monkeypatch.setattr(config, 'load_settings', lambda: {'accounts': [
        {'name': 'shared', 'dir': str(shared)},
        {'name': 'shared-copy', 'dir': str(shared) + os.sep},      # same folder
        {'name': 'work', 'dir': str(work)},
    ]})

    assert hooks.account_dirs() == [('default', str(default)),
                                    ('shared', str(shared)),
                                    ('work', str(work))]

    seen = []

    def probe(cfgdir=None, tag=None):
        seen.append(cfgdir)
        return tag

    assert hooks.across_accounts(probe, tag='t') == {'default': 't',
                                                     'shared': 't', 'work': 't'}
    assert seen == [str(default), str(shared), str(work)], \
        'an account was visited twice, or with someone else\'s dir'

    assert hooks.across_accounts(hooks.install_limit_hook) == {
        'default': True, 'shared': True, 'work': True}
    for p in (default, shared, work):
        entries = json.loads(_raw(p / 'settings.json').decode('utf-8'))['hooks']['StopFailure']
        assert len(entries) == 1, f'{p.name} got the rotation hook twice'
        assert 'limit_hook.py' in entries[0]['hooks'][0]['command']
    assert [w[0] for w in writes] == [
        os.path.normcase(os.path.abspath(str(p / 'settings.json')))
        for p in (default, shared, work)]
    assert not os.path.exists(os.path.join(str(tmp_path), DECOY_NAME)), \
        'the import-bound settings_path was written while naming accounts'
    assert hooks.across_accounts(hooks.limit_hook_installed) == {
        'default': True, 'shared': True, 'work': True}


# ── 6 · counting a disabled block that is not shaped right ───

def test_counting_a_block_counts_entries_and_ignores_values_that_are_not_lists():
    """hooks.py:749-750.

    `_count` has no test anywhere in tests/ and no caller inside hooks.py, so
    both of its branches are unreached: the `isinstance(v, list)` guard (drop
    it and `'junk'` counts as 4 "hooks", and `None` raises TypeError in the
    middle of a screen) and the `(block or {})` guard for an account with no
    `hooks` block at all. An entry counts once whatever its nested hooks are,
    because the manager lists and indexes entries, not commands.
    """
    assert hooks._count(None) == 0                            # 750, `(block or {})`
    assert hooks._count({}) == 0
    two_entries = {'Stop': [{'hooks': [{'command': 'a'}, {'command': 'b'}]},
                           {'hooks': [{'command': 'c'}]}]}
    assert hooks._count(two_entries) == 2, 'nested hooks were counted, not entries'
    assert hooks._count({'Stop': 'junk', 'PreToolUse': None,      # 750, isinstance
                         'SessionStart': {'a': 1}, 'StopFailure': 7}) == 0
    assert hooks._count({'Stop': ['not-a-dict', {'hooks': []}]}) == 2


# ── 7 · hostile entries and command types ────────────────────

def test_hostile_entry_and_command_types_stay_out_of_the_crash_path(
        monkeypatch, tmp_path):
    """hooks.py:753-756, 785-787, 833-839.

    settings.json is hand-edited and community hooks put anything in it: a
    `hooks` list of loose strings, a `command` that is a number or a list. The
    `isinstance(h, dict)` filter on 756 and the `str()` on 755 are what stop
    every surface that labels a hook — both TUI rows, the GUI payload, the
    installed check — dying on a third party's file. The snippet on 838-839 is
    a column width, so its 45/46 boundary is asserted on both sides.
    """
    _fake_archeus_settings(monkeypatch)
    entry = {'hooks': ['junk', 7, None, {'command': None}, {'command': 42},
                      {'command': ['echo', 'hi']}, {}]}

    # a dict with no `command` still contributes the empty command it declares
    assert hooks._entry_commands(entry) == ['None', '42', "['echo', 'hi']", '']
    assert all(isinstance(c, str) for c in hooks._cmd_keys(entry))
    assert hooks._cmd_keys({'hooks': [{'type': 'command'}]}) == ['']
    assert hooks.derived_label(entry, 'Stop') == 'None'       # first command, no template

    assert hooks._hook_label({'hooks': []}, 'Stop') == '(empty)'
    whole = 'echo ' + 'x' * 40                                # exactly 45 characters
    assert len(whole) == 45
    assert hooks.derived_label({'hooks': [{'command': whole}]}, 'Stop') == whole
    cut = 'echo ' + 'y' * 41                                  # 46, one past the budget
    out = hooks.derived_label({'hooks': [{'command': cut}]}, 'Stop')
    assert out == cut[:44] + '…' and len(out) == 45, out


# ── 8 · the label key cannot bleed across events or commands ─

def test_a_hook_label_never_leaks_to_another_event_or_another_command_split(
        monkeypatch, tmp_path):
    """hooks.py:861-862 — `_label_key`, the only thing separating one hook's
    name from every other hook's.

    Two commands must not read as one command (drop the `\x00` joiner and
    `['a','b']` equals `['ab']`, so naming one hook renames the other), and
    `event or ''` must fold `None` and `''` together: the TUI passes the event
    it came from, other callers pass nothing, and a name the user typed would
    otherwise show on one surface and not the other.
    """
    store = _fake_archeus_settings(monkeypatch)
    cmds = ['/opt/theirs/tool-run.js']
    key = hooks._label_key

    assert hooks.set_label(None, cmds, name='careful', cat='Mine') is True
    assert hooks.label_of('', cmds) == {'name': 'careful', 'cat': 'Mine'}
    assert hooks.label_of(None, cmds) == {'name': 'careful', 'cat': 'Mine'}
    assert hooks.label_of('Stop', cmds) == {}, 'a name bled across events'
    assert hooks.label_of(None, ['car', 'eful']) == {}
    assert hooks.label_of(None, ['/opt/theirs/tool-run.jsX']) == {}

    assert key('Stop', ['a', 'b']) != key('Stop', ['ab'])
    assert key('Stop', None) == key('Stop', [])
    assert key(None, cmds) == key('', cmds)
    assert key('Stop', cmds) != key('PreToolUse', cmds)

    entry = {'hooks': [{'type': 'command', 'command': cmds[0]}]}
    assert hooks._hook_label(entry, None) == 'careful'
    assert hooks._hook_label(entry, 'Stop') != 'careful'
    assert hooks.category_of(entry, None) == 'Mine'
    assert store['saves'] == 1


# ── 9 · a re-key carries the whole row, or does nothing ──────

def test_rekeying_a_label_moves_the_whole_row_and_invents_nothing(
        monkeypatch, tmp_path):
    """hooks.py:903-913.

    `migrate.repair_commands` rewrites a dead script path on every start, so
    this is the only thing standing between a reinstall and the user losing what
    they called their hooks. Losing the `cat` half is silent, and losing the
    `if not row: return False` guard on 906 is worse than a no-op: it writes an
    empty row under the new key, which then reads back as a named hook in the
    GUI payload. The other event's row — same commands, different moment — must
    not move with it.
    """
    store = _fake_archeus_settings(monkeypatch)
    old = ['/opt/old/limit-run.js']
    new = ['/opt/new/limit-run.js']
    bystander = ['/opt/other.js']
    assert hooks.set_label('StopFailure', old, name='rotate me', cat='My rules')
    assert hooks.set_label('StopFailure', bystander, name='keep', cat='Other')
    assert hooks.set_label('Stop', old, name='a different moment')
    saves_before = store['saves']

    assert hooks.rekey_label('StopFailure', old, new) is True

    labels = store['data']['hook_labels']
    assert labels[hooks._label_key('StopFailure', new)] == {'name': 'rotate me',
                                                            'cat': 'My rules'}
    assert hooks._label_key('StopFailure', old) not in labels, 'copied, not moved'
    assert labels[hooks._label_key('Stop', old)] == {'name': 'a different moment'}
    assert labels[hooks._label_key('StopFailure', bystander)] == {'name': 'keep',
                                                                  'cat': 'Other'}

    assert store['saves'] == saves_before + 1, 'the move did not save'

    assert hooks.rekey_label('StopFailure', new, new) is False      # 903-904
    assert hooks.rekey_label('StopFailure', ['/never/labelled.js'],
                             ['/wherever.js']) is False              # 906-907
    assert store['saves'] == saves_before + 1, 'a rekey that found nothing still saved'
    assert not [k for k, v in store['data']['hook_labels'].items() if not v], \
        'an empty label row was invented'


# ── 10 · clearing one label field keeps the rest ─────────────

def test_clearing_one_label_field_keeps_the_other_field_and_the_other_hooks(
        monkeypatch, tmp_path):
    """hooks.py:875-892 — the `is not None` pair (882/884), the empty-field
    filter (886) and the drop-rather-than-empty branch (890).

    Renaming a hook must not file it somewhere else, and un-filing it must not
    rename it; both are one missing `is not None` away from being clobbered,
    because the row is rewritten whole. A row with nothing left has to go from
    `hook_labels` entirely: an empty dict left behind is what makes a hook read
    as "named" to a surface that only asks whether a row exists. And clearing
    one hook's name must leave its neighbour's row alone — `labels` is
    round-tripped through a dict copy, so a whole-block overwrite is invisible
    until another hook has lost its name.
    """
    store = _fake_archeus_settings(monkeypatch)
    mine = ['/opt/theirs/mine-run.js']
    neighbour = ['/opt/theirs/other-run.js']
    assert hooks.set_label('Stop', mine, name='alpha', cat='family-a') is True
    assert hooks.set_label('Stop', neighbour, name='beta', cat='family-b') is True

    assert hooks.set_label('Stop', mine, cat='family-z') is True   # 882: name=None
    labels = store['data']['hook_labels']
    assert labels[hooks._label_key('Stop', mine)] == {'name': 'alpha',
                                                      'cat': 'family-z'}

    assert hooks.set_label('Stop', mine, name='   ') is True       # 883, 886
    labels = store['data']['hook_labels']
    assert labels[hooks._label_key('Stop', mine)] == {'cat': 'family-z'}, \
        'blanking the name took the category with it'
    assert labels[hooks._label_key('Stop', neighbour)] == {'name': 'beta',
                                                          'cat': 'family-b'}, \
        'another hook\'s label moved'

    assert hooks.set_label('Stop', mine, name='', cat='') is True
    labels = store['data']['hook_labels']
    assert hooks._label_key('Stop', mine) not in labels, 'an empty row was left behind'
    assert not [k for k, v in labels.items() if not v]
    assert labels[hooks._label_key('Stop', neighbour)] == {'name': 'beta',
                                                          'cat': 'family-b'}
    assert hooks.label_of('Stop', mine) == {}
    assert hooks._hook_label({'hooks': [{'type': 'command',
                                         'command': neighbour[0]}]},
                            'Stop') == 'beta'
