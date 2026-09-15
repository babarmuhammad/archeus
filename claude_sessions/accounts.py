"""Multi-account manager — make running two (or more) Claude accounts easy.

Claude Code picks the account from its config dir (CLAUDE_CONFIG_DIR). Each
account = its own dir with its own login. archeus stores named accounts, lets
you switch the active one, and — the point — **launch a second account in a new
terminal with one key** so both run at the same time.
"""

import os
import subprocess

from . import config as _c
from .ui import menu, text_input, flash, confirm, _cls, pause, pager
from . import render


def _default_dir():
    return os.path.join(_c._USERPROFILE, '.claude')


def _accounts(s):
    """[(name, dir, is_active)] — always includes the built-in default account."""
    active = s.get('claude_config_dir', '') or ''
    out = [('default', '', not active)]                  # '' dir = ~/.claude
    for a in s.get('accounts', []):
        if isinstance(a, dict) and a.get('dir'):
            out.append((a.get('name', a['dir']), a['dir'],
                        os.path.expanduser(a['dir']) == os.path.expanduser(active)))
    return out


def _resolved(d):
    return os.path.expanduser(os.path.expandvars(d)) if d else _default_dir()


def _pick_harness():
    """Which CLI's logins to manage, asked only when there is a choice.

    The same rule the launch target strip and `harnessStrip` use: one CLI is
    not a choice, so a single-harness machine sees exactly the menu it always
    saw.
    """
    from . import harnesses
    hids = [h for h in harnesses.ids()
            if h == harnesses.DEFAULT
            or (h not in harnesses.disabled() and harnesses.exe(h))]
    if len(hids) < 2:
        return hids[0] if hids else harnesses.DEFAULT
    items = [(f"{harnesses.descriptor(h)['label']}  "
              f"{_c.C_DIM}{len(harnesses.homes(h))} login"
              f"{'' if len(harnesses.homes(h)) == 1 else 's'}{_c.C_RESET}", h)
             for h in hids]
    items.append(('Back', None))
    return menu(items, "LOGINS  /  which CLI")


def accounts_menu():
    from . import harnesses
    hid = _pick_harness()
    if hid:
        _homes_menu(hid)


def _homes_menu(hid):
    from . import harnesses
    from .config import load_settings
    label = harnesses.descriptor(hid)['label']
    claude = hid == harnesses.DEFAULT
    while True:
        s = load_settings()
        # Claude Code keeps its own reader: its rows carry an ACTIVE flag and a
        # synthetic default whose dir is '', and both the switch action and the
        # GUI's `resolved` field are written against that shape.
        rows = (_accounts(s) if claude
                else [(n, d, False) for n, d in harnesses.homes(hid)])
        built_in = '' if claude else harnesses.home_dir(hid)
        items = []
        for name, d, active in rows:
            dot = f"{_c.C_OK}●{_c.C_RESET}" if active else '○'
            loc = d or '~/.claude'
            tag = f"  {_c.C_OK}(active){_c.C_RESET}" if active else ''
            items.append((f"{dot} {name}  {_c.C_DIM}{render.trunc(loc, 40)}{_c.C_RESET}{tag}"
                          f"{_rotation_tag(d) if claude else ''}",
                          f'acct:{name}'))
        items += [(f"{'─' * _c.W}", None),
                  (f'＋  Add {"account" if claude else "login"}', '__add__')]
        if claude:
            items.append((f'⇄  Rotation  {_c.C_DIM}({_rotation_summary()}){_c.C_RESET}',
                          '__rotate__'))
            items.append(('⇄  Sync accounts  (level every account up)', '__sync__'))
        items.append(('Back', 'back'))
        sel = menu(items, f"{label.upper()}  /  LOGINS")
        if not sel or sel == 'back':
            return
        if sel == '__add__':
            _add_account(s, hid)
        elif sel == '__rotate__':
            _rotation_menu()
        elif sel == '__sync__':
            _sync_accounts()
        elif sel.startswith('acct:'):
            _account_actions(s, sel[5:], hid, built_in)


# ── account rotation ─────────────────────────────────────────
# The policy lives in rotate.py; this is only its terminal face. Same split
# skills.py uses: a non-interactive core the GUI's job threads can call, and a
# thin menu here — `ui.menu` is NOT bridged onto a job thread, so reaching it
# from one hangs rather than errors.

def _rotation_tag(d):
    """What a login row says about rotation: how full, and whether it is in."""
    from . import rotate
    try:
        pct = rotate.used_pct(d)
        out = '' if rotate.is_enabled(d) else f"  {_c.C_DIM}(out of rotation){_c.C_RESET}"
        if not pct:
            return out
        col = _c.C_ERR if rotate.spent(d) else _c.C_DIM
        return f"  {col}{pct:.0f}%{_c.C_RESET}{out}"
    except Exception:
        return ''


def _rotation_summary():
    from . import rotate
    try:
        m = rotate.mode()
        if m == 'off':
            return 'off'
        return f"{'automatic' if m == 'auto' else 'semi'}, switch at {rotate.threshold():.0f}%"
    except Exception:
        return '?'


_MODE_LABELS = (
    ('off', 'Off — never change the account for me'),
    ('ask', 'Semi-automatic — start new work elsewhere, ask before moving a live session'),
    ('auto', 'Fully automatic — also open the successor session by itself'),
)


def _rotation_menu():
    """Mode, threshold, and which logins take part."""
    from . import rotate
    from .config import load_settings, save_settings
    while True:
        st = rotate.state()
        items = [(f"Mode: {_c.C_TITLE}{dict(_MODE_LABELS)[st['mode']]}{_c.C_RESET}", '__mode__'),
                 (f"Switch away at: {_c.C_TITLE}{st['threshold']:.0f}%{_c.C_RESET}"
                  f"  {_c.C_DIM}(100% is what blocks a call; this only stops archeus"
                  f" choosing the account){_c.C_RESET}", '__thr__'),
                 (f"{'─' * _c.W}", None)]
        for a in st['accounts']:
            mark = f"{_c.C_OK}✓{_c.C_RESET}" if a['enabled'] else '·'
            state = (f"{_c.C_ERR}spent{_c.C_RESET}" if a['spent']
                     else '' if not a['signed_in'] else f"{_c.C_DIM}{a['pct']:.0f}%{_c.C_RESET}")
            live = f"  {_c.C_OK}(live){_c.C_RESET}" if a['live'] else ''
            items.append((f"{mark} {a['name']}  {state}{live}", 'acct:' + a['resolved']))
        items += [(f"{'─' * _c.W}", None), ('Back', 'back')]
        sel = menu(items, 'ACCOUNTS  /  ROTATION')
        if not sel or sel == 'back':
            return
        s = load_settings()
        if sel == '__mode__':
            pick = menu([(lbl, key) for key, lbl in _MODE_LABELS] + [('Cancel', None)],
                        'ROTATION  /  MODE')
            if pick:
                s['rotate_mode'] = pick
                save_settings(s)
        elif sel == '__thr__':
            v = text_input('Switch away at what percent? (50-100)',
                           default=f"{st['threshold']:.0f}")
            try:
                s['rotate_threshold'] = float(v)
            except (TypeError, ValueError):
                flash('Not a number', ok=False, secs=1.4)
                continue
            save_settings(s)
        elif sel.startswith('acct:'):
            d = sel[5:]
            # compared through rotate's own normaliser, not `_resolved`: the
            # list is hand-editable and `~/.claude-work` and `C:\Users\…\
            # .claude-work` must be the same entry or a toggle adds a duplicate
            off = [x for x in (s.get('rotate_disabled') or [])
                   if isinstance(x, str) and rotate._norm(
                       _c.resolve_config_dir(x)) != rotate._norm(d)]
            if rotate.is_enabled(d):        # it was in — take it out
                off.append(d)
            s['rotate_disabled'] = off
            save_settings(s)


def _sync_accounts():
    """Show the per-account diff, then copy the missing items in.

    The diff is shown BEFORE anything is written: what reaches four more
    accounts here is hooks and plugins, which run code every turn.
    """
    from . import provision
    d = provision.diff()
    lines = provision.report(d)
    if d['clean']:
        pager(('ARCHEUS', 'ACCOUNTS', 'SYNC'), lines, hint='ESC back')
        return
    key = pager(('ARCHEUS', 'ACCOUNTS', 'SYNC'), lines,
                hint='a  apply to every account', extra_keys=('a',))
    if key != 'a':
        return
    if not confirm('Copy the missing items into every account?', danger=True):
        return

    def review(name, marketplace):
        from . import plugins
        return plugins.review_plugin(name, marketplace)

    done = provision.apply(d, review=review)
    out = ['  %s  %-12s %-12s %s' % ('OK ' if ok else 'ERR', acct, kind, detail)
           for acct, kind, detail, ok in done] or ['  Nothing to do.']
    pager(('ARCHEUS', 'ACCOUNTS', 'SYNC'), out, hint='ESC back')


def _add_account(s, hid=None):
    from . import harnesses
    from .config import save_settings
    hid = harnesses.descriptor(hid)['id']
    claude = hid == harnesses.DEFAULT
    label = harnesses.descriptor(hid)['label']
    name = text_input("Login name (e.g. work, personal):")
    if not name:
        return
    stem = '.claude' if claude else '.' + hid
    d = text_input(f"{harnesses.descriptor(hid)['home_env']} for this login:",
                   default=os.path.join(_c._USERPROFILE, f'{stem}-{name}'))
    if not d:
        return
    rd = _resolved(d)
    try:
        os.makedirs(rd, exist_ok=True)
    except Exception as e:
        flash(f"Could not create dir: {e}", ok=False, secs=2)
        return
    if claude:
        accts = [a for a in s.get('accounts', []) if a.get('name') != name]
        accts.append({'name': name, 'dir': d})
        s['accounts'] = accts
    else:
        homes = dict(s.get('homes') or {})
        rows = [r for r in (homes.get(hid) or [])
                if isinstance(r, dict) and r.get('name') != name]
        rows.append({'name': name, 'dir': d})
        homes[hid] = rows
        s['homes'] = homes
    save_settings(s)
    if confirm(f"Log in to '{name}' now? (opens {label})"):
        _login(d, hid)
    else:
        flash(f"Login '{name}' added — sign in later from its row", secs=1.6)


def _account_actions(s, name, hid=None, built_in=''):
    from . import harnesses
    from .config import save_settings
    hid = harnesses.descriptor(hid)['id']
    claude = hid == harnesses.DEFAULT
    if claude:
        d = '' if name == 'default' else next(
            (a['dir'] for a in s.get('accounts', []) if a.get('name') == name), '')
        removable = name != 'default'
    else:
        d = next((dd for n, dd in harnesses.homes(hid) if n == name), '')
        removable = d != built_in
    acts = []
    # Only Claude Code has an ACTIVE login, because only Claude Code is a CLI
    # archeus itself calls — the statusline, memory extraction and provisioning
    # all resolve `config.config_dir`. Every Codex and pi subprocess archeus
    # spawns already takes a home, so which one a SESSION uses is the launch
    # window's question and there is nothing here to switch.
    if claude:
        acts.append(('Switch active account (this archeus)', 'switch'))
    acts += [('Open in NEW terminal (run in parallel)', 'parallel'),
             ('Log in / re-login here', 'login')]
    if removable:
        acts.append(('Rename', 'rename'))
        acts.append(('Remove from list', 'remove'))
    acts.append(('Cancel', 'cancel'))
    act = menu(acts, f"LOGIN  /  {name}")
    if act == 'switch':
        s['claude_config_dir'] = d
        save_settings(s)
        flash(f"Active account → {name}. Restart archeus to fully apply.", secs=2)
    elif act == 'parallel':
        _open_terminal(d, name, hid)
    elif act == 'login':
        _login(d, hid)
    elif act == 'rename':
        new = text_input("New login name:", default=name)
        if not new or new == name:
            return
        taken = ([a.get('name') for a in s.get('accounts', [])] + ['default']
                 if claude else [n for n, _dd in harnesses.homes(hid)])
        if new in taken:
            flash(f"Name '{new}' already in use", ok=False, secs=1.8)
            return
        if claude:
            for a in s.get('accounts', []):
                if a.get('name') == name:
                    a['name'] = new
        else:
            homes = dict(s.get('homes') or {})
            for r in (homes.get(hid) or []):
                if isinstance(r, dict) and r.get('name') == name:
                    r['name'] = new
            s['homes'] = homes
        save_settings(s)
        flash(f"Renamed '{name}' → '{new}' (its directory is unchanged)", secs=1.8)
    elif act == 'remove':
        if claude:
            s['accounts'] = [a for a in s.get('accounts', []) if a.get('name') != name]
            if os.path.expanduser(s.get('claude_config_dir', '')) == os.path.expanduser(d):
                s['claude_config_dir'] = ''
        else:
            homes = dict(s.get('homes') or {})
            homes[hid] = [r for r in (homes.get(hid) or [])
                          if isinstance(r, dict) and r.get('name') != name]
            s['homes'] = homes
        save_settings(s)
        flash(f"Removed '{name}' (its directory on disk is untouched)", secs=1.8)


#: alias — the implementation moved to config.py so the GUI can install a
#: plugin into one account without importing the TUI (accounts.py imports ui).
def _env_for(d, hid=None):
    """'' means the DEFAULT home of *hid*, not the active one."""
    from . import harnesses
    resolved = _resolved(d) if hid in (None, harnesses.DEFAULT) else (
        d or harnesses.home_dir(hid))
    return _c.account_env(resolved)


def _login(d, hid=None):
    from . import harnesses
    argv = harnesses.login_argv(hid)
    label = harnesses.descriptor(hid)['label']
    if not argv:
        flash(f"{label} not found", ok=False, secs=1.6)
        return
    _cls()
    print(f"\n  Opening {label} under {_resolved(d) if hid in (None, harnesses.DEFAULT) else d}")
    # Claude Code has no login subcommand — you start it and type /login —
    # while `codex login` is the whole flow and exits on its own.
    print("  Use /login to sign in, then exit to return.\n" if not argv[1:]
          else "  Follow the sign-in, then close this when it is done.\n")
    try:
        subprocess.call(argv, env=_env_for(d, hid))
    except Exception as e:
        print(f"\n  Failed: {e}")
        pause("\n  Press Enter…")


def _open_terminal(d, name, hid=None):
    """Launch this CLI for one home in a NEW terminal window so it runs
    alongside the current one (the easy 'two accounts at once')."""
    from . import harnesses, proc
    argv = harnesses.login_argv(hid)
    label = harnesses.descriptor(hid)['label']
    if not argv:
        flash(f"{label} not found", ok=False, secs=1.6)
        return
    _p, err = proc.spawn_terminal(argv, env=_env_for(d, hid),
                                  title=f'{label} [{name}]')
    if err:
        flash(f"Could not open terminal: {err}", ok=False, secs=2)
    else:
        flash(f"Opened a new terminal running {label} as '{name}'", secs=1.8)
