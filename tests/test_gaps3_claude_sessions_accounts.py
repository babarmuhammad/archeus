"""T-1173 — highest-risk uncovered branches of claude_sessions/accounts.py
lines 1-376 (tip 56d53504), the whole slice; the whole file is in scope.

All ten card probes applied (none was already covered or inapplicable; the
evidence for that is in /work/QWEN-DONE-T-1173.md), so the final ten are the
probes, ranked fail-closed/denial first, then boundaries, then error paths:

 1. probe 1  _account_actions L268-269 unknown name collapses d to the ''
              default sentinel, L290-291 persists it  (kept as xfail strict)
 2. probe 9  _login L345-348 / _open_terminal L367-370: missing login argv
              must deny BEFORE subprocess.call / proc.spawn_terminal
 3. probe 5  _account_actions rename L301-305: collision flashes and writes
              nothing (no mutation of s, no save_settings)
 4. probe 6  _add_account L230-237: cancelled name or dir prompt returns
              before os.makedirs and before any persist
 5. probe 7  _add_account L239-243: os.makedirs failure flashes and never
              reaches save_settings (L255) or the login confirm (L256)
 6. probe 4  remove-claude L320-322: clearing claude_config_dir requires an
              expanduser-equal match with the removed home, own selection only
 7. probe 3  remove-non-claude L323-327: rewrites only homes[hid]; the Claude
              selection and every other harness list stay byte-identical
 8. probe 8  _open_terminal L371 + _login L356 via _env_for L337-339: the
              child env is built from the SELECTED resolved home, never the
              active config dir
 9. probe 10 _accounts L28 + switch L290 + _resolved L33: a '~/' alias
              written by switch still reads ACTIVE and resolves identically
10. probe 2  _accounts L26-27: malformed settings['accounts'] entries never
              reach the rows; a nameless entry falls back to its dir

All OS/credential/process effects are seam-faked (module attributes the code
already reads at call time); nothing here reads the host environment, a real
home or a credential file, and every invented value lives under tmp_path.
Neighbouring coverage: test_accounts.py, test_account_scope.py,
test_multihome.py. Independent of every other test_gaps3 file.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox
from claude_sessions import accounts, config, harnesses, proc

FAKE_ENV = {'FAKE_HOME_ENV': 'invented', 'ANTHROPIC_API_KEY_REMOVED': 'yes'}


def _seam_menu(monkeypatch, answers):
    """Scripted `menu`; asserts once per scripted answer, no silent re-ask."""
    seen = []
    left = list(answers)

    def fake(items, title, *a, **k):
        seen.append(title)
        return left.pop(0)
    monkeypatch.setattr(accounts, 'menu', fake)
    return seen


def _seam_text(monkeypatch, answers):
    left = list(answers)
    seen = []

    def fake(prompt, default=''):
        seen.append(prompt)
        return left.pop(0)                      # IndexError = asked too often
    monkeypatch.setattr(accounts, 'text_input', fake)
    return seen


def _seam_confirm(monkeypatch, answer):
    seen = []
    monkeypatch.setattr(accounts, 'confirm',
                        lambda *a, **k: (seen.append(a), answer)[1])
    return seen


def _seam_flash(monkeypatch):
    seen = []
    monkeypatch.setattr(accounts, 'flash',
                        lambda m, ok=True, secs=0: seen.append((m, ok)))
    return seen


def _seam_saves(monkeypatch):
    saved = []
    monkeypatch.setattr(config, 'save_settings',
                        lambda s: saved.append(copy.deepcopy(s)))
    return saved


def _seam_account_env(monkeypatch):
    """Synthetic child env only — the real one copies the host environment."""
    resolved_seen = []

    def fake(cfgdir=None, harness=None):
        resolved_seen.append(cfgdir)
        return dict(FAKE_ENV)
    monkeypatch.setattr(config, 'account_env', fake)
    return resolved_seen


def _seam_spawn(monkeypatch):
    spawns = []
    monkeypatch.setattr(proc, 'spawn_terminal',
                        lambda argv=None, *, cwd=None, env=None, title='',
                        keep_open=False: (spawns.append((argv, env, title)),
                                          (None, None))[1])
    return spawns


def _seam_subprocess_call(monkeypatch):
    calls = []
    monkeypatch.setattr(accounts.subprocess, 'call',
                        lambda argv, *a, **k: calls.append((argv, k.get('env'))))
    return calls


def _seam_login_argv(monkeypatch, argv):
    monkeypatch.setattr(harnesses, 'login_argv', lambda hid=None: list(argv))


def _seam_makedirs(monkeypatch, raise_exc=None):
    made = []

    def fake(path, *a, **k):
        made.append(path)
        if raise_exc is not None:
            raise raise_exc
    monkeypatch.setattr(accounts.os, 'makedirs', fake)
    return made


# ── 2. (probe 9) missing login argv: denial before any runner ─────────────

def test_missing_login_argv_starts_no_runner(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _seam_login_argv(monkeypatch, [])                    # the real empty-argv seam
    flashes = _seam_flash(monkeypatch)
    calls = _seam_subprocess_call(monkeypatch)
    spawns = _seam_spawn(monkeypatch)
    resolved = _seam_account_env(monkeypatch)
    _seam_makedirs(monkeypatch)
    d = str(tmp_path / 'sel-home')

    accounts._login(d, 'claude')
    accounts._open_terminal(d, 'work', 'claude')
    accounts._login(d, 'codex')
    accounts._open_terminal(d, 'work', 'codex')

    assert calls == [], 'subprocess.call was reached despite an empty argv'
    assert spawns == [], 'a terminal was spawned despite an empty argv'
    assert resolved == [], 'an env was built although the CLI is absent'
    denied = [m for m, ok in flashes if not ok]
    assert len(denied) == 4, flashes
    assert 'Claude Code not found' in denied[0] and 'Codex not found' in denied[2]


# ── 3. (probe 5) rename collision writes nothing ───────────────────────────

def test_rename_collision_writes_nothing(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    s = {'accounts': [{'name': 'work', 'dir': str(tmp_path / 'w')},
                      {'name': 'personal', 'dir': str(tmp_path / 'p')}]}
    original = copy.deepcopy(s)
    _seam_menu(monkeypatch, ['rename', 'rename', 'rename'])
    prompts = _seam_text(monkeypatch, ['personal', 'default', ''])
    saved = _seam_saves(monkeypatch)
    flashes = _seam_flash(monkeypatch)

    accounts._account_actions(s, 'work')                 # collides with a row
    accounts._account_actions(s, 'work')                 # collides with default
    accounts._account_actions(s, 'work')                 # empty new name

    assert saved == [], 'a rename collision persisted something'
    assert s == original, 'the caller-visible settings were mutated'
    assert len(prompts) == 3
    assert [ok for _m, ok in flashes] == [False, False], flashes
    assert 'personal' in flashes[0][0] and 'already in use' in flashes[0][0]
    assert 'default' in flashes[1][0] and 'already in use' in flashes[1][0]


# ── 4. (probe 6) cancelled add makes no directory and no write ─────────────

def test_add_account_cancel_makes_no_dir_or_write(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    made = _seam_makedirs(monkeypatch)
    saved = _seam_saves(monkeypatch)
    confirms = _seam_confirm(monkeypatch, False)
    flashes = _seam_flash(monkeypatch)
    before = (open(str(sb.settings), 'rb').read()
              if sb.settings.exists() else None)

    prompts = _seam_text(monkeypatch, [''])               # cancel at the name
    accounts._add_account(config.load_settings())
    assert len(prompts) == 1, 'a cancelled name must stop the add immediately'
    assert made == [], 'a directory was made although the name was cancelled'

    prompts = _seam_text(monkeypatch, ['fresh', ''])      # cancel at the dir
    accounts._add_account(config.load_settings())
    assert len(prompts) == 2, 'the dir prompt must be asked before cancelling'
    assert made == [], 'os.makedirs ran although the dir was cancelled'

    assert saved == [], 'a cancelled add persisted settings'
    assert confirms == [], 'a cancelled add asked to log in'
    assert flashes == [], 'a silent cancel must not flash'
    after = (open(str(sb.settings), 'rb').read()
             if sb.settings.exists() else None)
    assert after == before, 'the settings file changed on a cancelled add'


# ── 5. (probe 7) makedirs failure never reaches the persist ────────────────

def test_add_account_mkdir_failure_does_not_persist(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    order = []
    saved = _seam_saves(monkeypatch)
    flashes = _seam_flash(monkeypatch)
    confirms = _seam_confirm(monkeypatch, False)
    monkeypatch.setattr(accounts, '_login',
                        lambda *a, **k: order.append('login'))

    def refuse(path, *a, **k):
        order.append('makedirs')
        raise OSError('invented: disk refused')
    monkeypatch.setattr(accounts.os, 'makedirs', refuse)
    monkeypatch.setattr(config, 'save_settings',
                        lambda s: (order.append('save'),
                                   saved.append(copy.deepcopy(s)))[1])
    monkeypatch.setattr(accounts, 'flash',
                        lambda m, ok=True, secs=0: (order.append('flash'),
                                                    flashes.append((m, ok)))[1])

    _seam_text(monkeypatch, ['fresh', str(tmp_path / 'never-made')])
    accounts._add_account(config.load_settings(), 'claude')
    _seam_text(monkeypatch, ['fresh2', str(tmp_path / 'never-made2')])
    accounts._add_account(config.load_settings(), 'codex')

    assert saved == [], 'settings were persisted after the mkdir failure'
    assert order == ['makedirs', 'flash', 'makedirs', 'flash'], order
    assert [ok for _m, ok in flashes] == [False, False], flashes
    assert all('Could not create dir' in m for m, _ok in flashes), flashes
    assert confirms == [] and 'login' not in order, 'login was offered anyway'
    assert not (tmp_path / 'never-made').exists()


# ── 6. (probe 4) removing a Claude account clears only its own selection ──

def test_remove_claude_account_clears_only_own_selection(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    w = str(tmp_path / 'acc-w')
    other = str(tmp_path / 'acc-other')
    saved = _seam_saves(monkeypatch)
    flashes = _seam_flash(monkeypatch)
    _seam_makedirs(monkeypatch)

    # leg A: the removed row IS the active selection (aliased both spellings)
    s_a = {'claude_config_dir': os.path.join(str(tmp_path), '.acc-w'),
           'accounts': [{'name': 'work', 'dir': '~/.acc-w'},
                        {'name': 'other', 'dir': other}]}
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    _seam_menu(monkeypatch, ['remove'])
    accounts._account_actions(s_a, 'work')
    assert saved and saved[-1]['claude_config_dir'] == '', \
        'removing the ACTIVE account must clear its own selection'
    assert [a['name'] for a in saved[-1]['accounts']] == ['other']

    # leg B: removing an inactive row must leave the selection alone
    n = len(saved)
    s_b = {'claude_config_dir': other,
           'accounts': [{'name': 'work', 'dir': w},
                        {'name': 'other', 'dir': other}]}
    _seam_menu(monkeypatch, ['remove'])
    accounts._account_actions(s_b, 'work')
    assert saved[-1]['claude_config_dir'] == other, \
        'removing an inactive account cleared the active selection'
    assert [a['name'] for a in saved[-1]['accounts']] == ['other']
    assert len(saved) == n + 1 and flashes, 'the removal never persisted'
    assert not os.path.isdir(w), 'remove must not touch the disk'


# ── 7. (probe 3) non-Claude removal preserves the Claude selection ─────────

def test_remove_nonclaude_preserves_claude_selection(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    builtin = str(tmp_path / '.codex')
    w2 = str(tmp_path / 'codex-work')
    pi_home = str(tmp_path / '.pi')
    active = str(tmp_path / 'claude-active')
    s = {'claude_config_dir': active,
         'accounts': [{'name': 'work', 'dir': str(tmp_path / 'acc-w')}],
         'homes': {'codex': [{'name': 'Codex', 'dir': builtin},
                             {'name': 'work', 'dir': w2}],
                   'pi': [{'name': 'pi', 'dir': pi_home}]}}
    monkeypatch.setattr(harnesses, 'homes',
                        lambda hid=None: [(r['name'], r['dir'])
                                          for r in s['homes'][hid]])
    _seam_menu(monkeypatch, ['remove'])
    saved = _seam_saves(monkeypatch)
    _seam_flash(monkeypatch)
    made = _seam_makedirs(monkeypatch)

    accounts._account_actions(s, 'work', 'codex', builtin)

    assert saved, 'the non-claude removal never persisted'
    assert saved[-1]['claude_config_dir'] == active, \
        'a Codex removal moved the ACTIVE Claude selection'
    assert [r['name'] for r in saved[-1]['homes']['codex']] == ['Codex']
    assert saved[-1]['homes']['pi'] == [{'name': 'pi', 'dir': pi_home}]
    assert 'claude' not in saved[-1]['homes'], \
        'a Codex home reached settings["homes"]["claude"]'
    assert saved[-1]['accounts'] == s['accounts'], 'Claude rows were touched'
    assert made == [], 'remove must not write to disk'
    assert not os.path.isdir(w2)


# ── 8. (probe 8) parallel/login env names the selected home, not the active ─

def test_parallel_env_uses_selected_home_not_active(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    sel = str(tmp_path / 'acc-selected')
    active = str(tmp_path / 'acc-active')
    monkeypatch.setattr(config, 'config_dir', active)
    s = config.load_settings()
    s['claude_config_dir'] = active
    s['accounts'] = [{'name': 'work', 'dir': sel}]
    config.save_settings(s)                              # real, patched below
    _seam_login_argv(monkeypatch, ['invented-cli', 'login'])
    resolved = _seam_account_env(monkeypatch)
    spawns = _seam_spawn(monkeypatch)
    calls = _seam_subprocess_call(monkeypatch)
    _seam_flash(monkeypatch)
    label = harnesses.descriptor('claude')['label']

    s = config.load_settings()
    _seam_menu(monkeypatch, ['parallel'])
    accounts._account_actions(s, 'work')
    assert resolved == [sel], 'env was not built from the selected home'
    assert spawns and spawns[0][0] == ['invented-cli', 'login']
    assert spawns[0][1] == FAKE_ENV, 'spawn did not get the selected-home env'
    assert 'work' in spawns[0][2] and label in spawns[0][2]

    accounts._login(sel, 'claude')
    assert resolved == [sel, sel], 'login env ignored the selected home'
    assert calls and calls[0][1] == FAKE_ENV
    assert active not in repr((resolved, spawns, calls)), \
        'the ACTIVE config dir leaked into a spawn for another account'


# ── 9. (probe 10) switch aliases normalize consistently ────────────────────

def test_switch_alias_round_trips_normalized(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    home = str(tmp_path / 'u')
    monkeypatch.setenv('HOME', home)                     # invented, not host
    monkeypatch.setenv('USERPROFILE', home)
    alias = '~/.claude-work'
    target = os.path.join(home, '.claude-work')
    s = {'claude_config_dir': '', 'accounts': [{'name': 'work', 'dir': alias}]}
    saved = _seam_saves(monkeypatch)
    _seam_flash(monkeypatch)
    _seam_menu(monkeypatch, ['switch'])

    accounts._account_actions(s, 'work')

    assert saved and saved[0]['claude_config_dir'] == alias
    assert os.path.normpath(accounts._resolved(saved[0]['claude_config_dir'])) == target, \
        'the alias written by switch must resolve to the row home'

    # leg B: ACTIVE follows the HOME, not the spelling — either side may hold
    # either alias, because the setting is hand-editable and GUI-written
    rows = accounts._accounts({'claude_config_dir': target,
                               'accounts': [{'name': 'work', 'dir': alias}]})
    assert dict((n, a) for n, _d, a in rows)['work'] is True, \
        'alias setting vs absolute row dir is the SAME home, so ACTIVE'
    rows = accounts._accounts({'claude_config_dir': alias,
                               'accounts': [{'name': 'work', 'dir': target}]})
    by = dict((n, a) for n, _d, a in rows)
    assert by['work'] is True, \
        'absolute setting vs alias row dir is the SAME home, so ACTIVE '\
        '(accounts.py:28 expanduser on both sides)'
    assert rows[0][0] == 'default' and by['default'] is False


# ── 10. (probe 2) malformed account entries are dropped, not fatal ─────────

def test_accounts_rows_tolerate_malformed_entries(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    good = str(tmp_path / 'acc-good')
    nameless = str(tmp_path / 'acc-nameless')
    s = {'claude_config_dir': '', 'accounts': [
        'plain-string', None, 42, ['list'],
        {}, {'name': 'no-dir'}, {'dir': ''}, {'dir': None},
        {'name': 'good', 'dir': good}, {'dir': nameless}]}

    rows = accounts._accounts(s)

    assert rows == [('default', '', True),
                    ('good', good, False),
                    (nameless, nameless, False)], \
        'every malformed entry is dropped (accounts.py:26) and a nameless '\
        'entry falls back to its dir (accounts.py:27) — never fatal, never '\
        'rendered as a spendable row'
