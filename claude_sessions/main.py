import os
import sys
import atexit
import subprocess

# waiver: config_dir here is the ACTIVE account for the whole TUI run, resolved
# once at startup on purpose — a launch must not change account mid-screen.
from .config import projects_dir, choice_file, config_dir, all_config_dirs
from .config import C_RESET, C_STAR, C_DIM, C_TITLE, C_BOLD, C_NAME
from .config import get_claude_exe, load_settings, save_settings
from .sessions import (get_session_info, load_recent_sessions, save_last_session,
                       format_age, scan_sessions, load_name, get_session_title)
from .ui import menu, launch_options_menu, pause, help_screen, settings_menu
from .session_menu import sessions_menu
from .mcp import mcp_status_line, global_claude_md_menu, mcp_servers, mcp_manager_menu
from .usage import usage_status_line
from .ui import _cls
from . import render
from . import store
from . import config as _c
from . import harnesses as _harnesses


def _workspace_status_cli():
    """`archeus workspace status` — resolve the project from cwd and print."""
    from .paths import encode_component
    from . import workspace
    cwd = os.path.abspath(os.getcwd())
    encoded = encode_component(cwd)
    proj_folder = os.path.join(projects_dir, encoded)
    if not os.path.isdir(proj_folder):
        proj_folder = None
    workspace.print_workspace_status(cwd, proj_folder)


def _recall_cli(query):
    """`archeus recall "<query>"` — print the task-relevant memory subgraph.
    This is the on-demand surface the CLAUDE.md micro-digest points Claude to."""
    from .paths import encode_component
    from . import recall
    cwd = os.path.abspath(os.getcwd())
    proj_folder = os.path.join(projects_dir, encode_component(cwd))
    if not os.path.isdir(proj_folder):
        proj_folder = None
    budget = load_settings().get('memory_budget', 600)
    r = recall.retrieve(cwd, proj_folder, query, budget)
    print(r['text'] if not r['empty'] else '(no relevant project memory)')


def _bg_scan_cli(project_path, proj_folder):
    """`archeus --bg-scan <path> <folder>` — detached memory worker: lessons
    scan, then (if enabled) incremental memory refresh — SEQUENTIALLY, so the
    two graph writers never clobber each other. Spawned headless by
    memory.spawn_background_worker; survives the TUI exiting to launch claude.
    Status/progress via the scan.lock marker."""
    import time as _time
    from . import memory, lessons
    from .config import log
    proj_folder = proj_folder or None
    memory._tls.silent = True                # headless Claude calls, no UI
    if not memory.acquire_scan_lock(project_path):
        return                               # another worker beat us to it
    name = os.path.basename(project_path.rstrip('\\/')) or project_path
    started, did_work, failed = _time.time(), '', ''
    try:
        st = load_settings()
        mem = memory.load_memory(project_path, proj_folder)
        if memory.refresh_on_open(project_path):
            # one call now does the graph, the CLAUDE.md block, the rules AND
            # the lessons — see memory.auto_cycle
            res = memory.auto_cycle(project_path, proj_folder, name, auto_cap=6)
            # report what actually happened. This used to discard the result and
            # say "Memory updated" even when the cycle had done nothing at all.
            bits = []
            if res.get('extracted'):
                bits.append(f"{res['extracted']} module(s)")
            if res.get('lessons'):
                bits.append(f"{res['lessons']} lesson(s)")
            if res.get('pending'):
                bits.append(f"{res['pending']} still queued")
            did_work = 'Memory updated — ' + ', '.join(bits) if bits else ''
        elif st.get('memory_lessons', 'prompt') == 'auto':
            # refresh is off but lesson learning is on — mine them on their own
            sids = lessons.pending_sids(proj_folder, mem)
            if sids:
                lessons.scan_sessions(project_path, proj_folder, sids)
                did_work = 'Lessons learned'
    except memory.MemoryBusy:
        return                              # another worker has it; not an error
    except Exception as e:
        log.exception('bg-scan worker failed')
        failed = str(e) or e.__class__.__name__
    finally:
        # This worker is detached and has NO interface of any kind — the badge
        # in the GUI only exists while that window is open, and the TUI has
        # already moved on (or exited to launch claude). A desktop notification
        # is the only way its result reaches anyone — INCLUDING when it fails,
        # which used to reach no one at all because the notify was gated on
        # having succeeded.
        try:
            from . import notify
            if failed:
                notify.job_finished(f'Memory update failed — {name}: {failed[:120]}',
                                    'error', _time.time() - started)
            elif did_work:
                notify.job_finished(f'{did_work} — {name}', 'done',
                                    _time.time() - started)
        except Exception:
            pass
        memory.clear_scan_lock(project_path)


def _hidden_projects_menu(grouped):
    """Archive projects out of the main list, and bring them back.

    Its own screen rather than a key over the project list because `menu()` has
    no hotkeys — every printable key goes to its search bar. Enter toggles the
    row under the cursor and the screen redraws, so hiding several is one visit.
    """
    from .config import hidden_projects, set_project_hidden
    while True:
        hidden = hidden_projects()
        items = [(f"{'☐' if enc in hidden else '☑'}  "
                  f"{os.path.basename(path) or path:<28}  {C_DIM}{path}{C_RESET}", enc)
                 for _m, path, enc, _pd, _od in grouped]
        sel = menu(items, "HIDE / RESTORE PROJECTS   (Enter toggles · ☐ = hidden)")
        if not sel:
            return
        set_project_hidden(sel, sel not in hidden)


def _harnesses_screen():
    """Which coding CLIs are here, and what archeus can do with each.

    The terminal half of the GUI's Harnesses page, and the same two questions:
    is it installed and where, and which surfaces work under it. The capability
    table is the point — everywhere else a gap greys one row and says why, and
    this is the one screen that shows them together.

    A menu of harnesses over a pager per harness, rather than one long dump:
    three CLIs times twenty-three capabilities is a screen nobody reads.
    """
    from . import harnesses as _h
    from .ui import pager
    while True:
        rows = []
        for hid in _h.ids():
            d = _h.descriptor(hid)
            exe = _h.exe(hid)
            mark = '●' if exe else '○'
            gaps = sum(1 for k in _h.CAPS if not _h.cap(hid, k)[0])
            note = (f"{gaps} of {len(_h.CAPS)} surfaces unavailable"
                    if exe else 'not installed')
            rows.append((f"{mark}  {d['label']:<14}  {C_DIM}{note}{C_RESET}", hid))
        sel = menu(rows, 'HARNESSES   (● installed · Enter for detail)')
        if not sel:
            return
        d = _h.descriptor(sel)
        exe = _h.exe(sel)
        lines = [f"binary              {exe or '(not found)'}",
                 f"home                {_h.home_dir(sel)}",
                 f"instructions file   {d['instructions_file']}",
                 f"effort scale        {', '.join(e or 'default' for e in d['efforts'])}",
                 '']
        if exe and d.get('doctor'):
            try:
                doc = _h.impl('doctor', sel)(_h.home_dir(sel)) or {}
            except Exception:
                doc = {}
            if doc.get('version'):
                lines.insert(0, 'version             %s%s' % (
                    doc['version'],
                    '   (%s available)' % doc['latest']
                    if doc.get('latest') and doc['latest'] != doc['version'] else ''))
            if doc.get('auth'):
                lines.insert(1, 'signed in           %s'
                             % ('yes' if doc['auth'] == 'ok' else 'no'))
        lines.append('WHAT WORKS HERE')
        for key, what in sorted(_h.CAPS.items()):
            ok, why = _h.cap(sel, key)
            lines.append('  %s %-18s %s' % ('+' if ok else '-', key,
                                            what if ok else why))
        pager([d['label']], lines, hint='Esc back')


#: the main menu's own rows, hoisted to module scope so a test can read them.
#: [(label, key, gui_route)] — a blank route means the row has no GUI
#: counterpart, and `test_every_main_menu_row_has_a_gui_counterpart` requires a
#: comment on the line saying why. Same idiom session_menu.ACTIONS already uses;
#: this is a hoist of the list that was already there, not a second copy of it.
MAIN_ACTIONS = [
    ('📂  Open new project by path…',        '__open_path__',        '/api/state'),
    ('🔍  Search all sessions',              '__search_all__',       '/api/search-index'),
    ('📦  Hide / restore projects',           '__hidden_projects__',  '/api/project/hide'),
    ('⚙  Usage stats',                       '__usage_stats__',      '/api/usage/daily'),
    ('⚙  MCP servers',                       '__mcp__',              '/api/mcp'),
    ('⚙  Agents',                            '__agents__',           '/api/agents/library'),
    ('⚙  Skills',                            '__skills__',           '/api/skills'),
    ('⚙  Hooks',                             '__hooks__',            '/api/hooks'),
    ('⚙  Updates (Claude Code + plugins)',   '__updates__',          '/api/versions'),
    ('⚙  Global CLAUDE.md  /  MCP Analysis', '__global_claude_md__', '/api/global-claude-md'),
    ('⚙  Accounts (switch / run 2 at once)', '__accounts__',         '/api/accounts'),
    ('⚙  Harnesses (which CLIs, and their setup)', '__harnesses__',  '/api/harness/setup'),
    ('⚙  Logs (what archeus did, what failed)', '__logs__',        '/api/logs'),
    ('⚙  Settings',                          '__settings__',         '/api/settings'),
    ('?  Help',                              '__help__',             ''),   # the GUI's help page is generated in the browser from SECTIONS/TABS — there is nothing for it to fetch
]

#: the same five sections the GUI sidebar has, as [(label, [keys])] pointing
#: INTO MAIN_ACTIONS. Fourteen flat rows under the project list read as a wall
#: and buried the three that operate on the list itself; five submenus is the
#: GUI's answer and the two surfaces are gated to move together.
#:
#: Keys rather than rows, so MAIN_ACTIONS stays the one table carrying a row's
#: label and its GUI route — the parity gate reads it and would have no way to
#: check a copy. Keyed by LABEL, never by index, for the reason the sidebar's
#: collapsed set was: reordering the sections must not silently open a
#: different one.
#: The five must be the GUI's five, IN ORDER — `test_the_five_sections_are_the_
#: ones_the_gui_sidebar_has` reads the labels out of the served page rather than
#: restating them, so this table and `app.js`'s SECTIONS move in one commit.
#: `Accounts` became `Harnesses` when the GUI's did: a login is one CLI's, so
#: the question the section answers is "which tool", and "which account" is one
#: screen inside it. The KEYS are free — the gate compares labels — which is why
#: the agents and hooks rows can stay under Library here while the GUI puts
#: their pages behind the Claude Code tab: the TUI has no two-level strip to put
#: them behind, and inventing one to satisfy a gate that does not ask for it
#: would be a screen written for a test.
MAIN_SECTIONS = [
    ('Context',   ['__global_claude_md__', '__mcp__']),
    ('Library',   ['__agents__', '__skills__', '__hooks__']),
    ('Activity',  ['__usage_stats__', '__logs__']),
    ('Harnesses', ['__harnesses__', '__accounts__']),
    ('Settings',  ['__settings__', '__updates__']),
]
#: menu key -> the capability it needs, pointing INTO MAIN_ACTIONS by key for
#: the reason MAIN_SECTIONS does: that table stays the one carrying a row's
#: label and its GUI route, and a fourth column there would be a fourth thing
#: three unpack sites and a parity gate have to agree about. Same keys as the
#: GUI's NAV field — `harnesses.CAPS` is where they are declared.
MAIN_CAPS = {
    '__mcp__':              'mcp',
    '__agents__':           'agents',
    '__skills__':           'skills',
    '__hooks__':            'hooks',
    '__updates__':          'versions',
    '__usage_stats__':      'usage',
    '__accounts__':         'accounts',
}


def _cap_of_row(key, cfgdir=None):
    """(ok, why) for a main-menu row on the account in front of the user.

    Dimmed and still selectable, exactly as the GUI greys a nav row: pressing it
    says what is missing and where it works. A row that disappears teaches
    nothing, and one that errors reads as a bug in archeus.
    """
    from .harnesses import cap, of
    need = MAIN_CAPS.get(key or '')
    return cap(of(cfgdir)['id'], need) if need else (True, '')


#: rows that stay ON the main menu. The first three act on the project list the
#: menu is already showing — burying "open a folder" one level down would put a
#: submenu between the user and the reason they opened archeus — and `?` is the
#: same door the GUI moved Help to. test_surface_parity fails a MAIN_ACTIONS key
#: that is in neither this set nor a section.
MAIN_TOP = ['__open_path__', '__search_all__', '__hidden_projects__', '__help__']


def _dim_unavailable(label, key):
    ok, _why = _cap_of_row(key)
    return label if ok else f"{C_DIM}{label}{C_RESET}"


def run():
    # `archeus --help` / `-h` / `help` — FIRST: a released package must answer
    # the one thing a new user types, and it must never start a UI to do it.
    if len(sys.argv) >= 2 and sys.argv[1] in ('--help', '-h', 'help'):
        from .cli import print_help
        print_help()
        return
    if len(sys.argv) >= 2 and sys.argv[1] in ('--version', '-V'):
        from .cli import print_version
        print_version()
        return
    # `archeus workspace status` — scriptable, no TUI
    if sys.argv[1:3] == ['workspace', 'status']:
        _workspace_status_cli()
        return
    # `archeus recall "<query>"` — scriptable, no TUI
    if len(sys.argv) >= 3 and sys.argv[1] == 'recall':
        _recall_cli(' '.join(sys.argv[2:]))
        return
    # `archeus statusline` — Claude Code's statusLine command. Reads one JSON
    # payload on stdin, prints one line. Runs on every conversation turn, so it
    # is dispatched FIRST-ish and must never touch the TUI.
    if len(sys.argv) >= 2 and sys.argv[1] == 'statusline':
        from .statusline import main as _sl
        sys.exit(_sl(sys.argv[2:]))
    # `archeus sync-accounts [--yes|--dry-run]` — level every account up to
    # what the user has actually provisioned. Shows the diff before writing.
    if len(sys.argv) >= 2 and sys.argv[1] == 'sync-accounts':
        from .provision import main as _sync
        sys.exit(_sync(sys.argv[2:]))
    # `archeus review [--staged|--branch BASE] [--min-confidence N] [path]`
    if len(sys.argv) >= 2 and sys.argv[1] == 'review':
        from .review import review_cli
        sys.exit(review_cli(sys.argv[2:]))
    # detached background memory worker (spawned, not user-facing)
    if len(sys.argv) >= 3 and sys.argv[1] == '--bg-scan':
        _bg_scan_cli(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '')
        return
    # detached model-failover proxy (spawned by failover.ensure_running)
    # argv[3] is the provider profile the daemon serves — passed at spawn rather
    # than looked up, because this branch runs BEFORE migrate_settings below and
    # may be reading a settings file that predates the profile list.
    if len(sys.argv) >= 2 and sys.argv[1] == '--failover-serve':
        from .failover import serve_cli
        sys.exit(serve_cli(sys.argv[2] if len(sys.argv) > 2 else 0,
                           sys.argv[3] if len(sys.argv) > 3 else ''))
    # detached translating gateway (spawned by gateway.ensure_running)
    if len(sys.argv) >= 2 and sys.argv[1] == '--gateway-serve':
        from .gateway import serve_cli as _gw
        sys.exit(_gw(sys.argv[2] if len(sys.argv) > 2 else 0,
                     sys.argv[3] if len(sys.argv) > 3 else ''))
    if len(sys.argv) >= 2 and sys.argv[1] == '--failover-stop':
        from .config import provider_profiles
        from .failover import stop_running
        msgs = [stop_running(p)[1] for p in provider_profiles()]
        print('; '.join(msgs) if msgs else 'no provider profiles configured')
        sys.exit(0)

    # ── one-time settings migrations ──────────────────────────────
    # HERE, below every scriptable dispatch above: `archeus statusline` runs
    # on every conversation turn and must never pay for a settings write, and
    # __main__.py deliberately routes it before this module is even imported.

    # FIRST of the three, because it moves the settings file the other two
    # then read. `pending()` is two stat calls once it has run.
    try:
        from . import migrate as _migrate
        if _migrate.pending():
            _moved, _failed = _migrate.run()
            if _failed:
                from .config import log as _log
                _log.warning('rename migration left %d item(s) behind: %s',
                             len(_failed), _failed[0][0])
        # UNGATED, and that is the fix rather than an oversight: a hook or a
        # statusline records an absolute path into the environment that installed
        # it, and everything that kills those paths — uninstalling the previous
        # package from its own pipx venv, a renamed checkout, a rebuilt
        # environment — happens AFTER the migration has run and closed its flag.
        # Repairing only during the migration meant repairing at the one moment
        # when nothing was broken yet.
        _migrate.repair_commands()
        # the second pass: what the path move could not reach. It carries its own
        # flag and returns immediately once that is set, so this is one settings
        # read on every later start.
        _swept, _sfailed = _migrate.sweep()
        if _sfailed:
            from .config import log as _log
            _log.warning('rename sweep left %d item(s) behind: %s',
                         len(_sfailed), _sfailed[0][0])
        # Printed rather than logged, and printed EVERY start until each is acted
        # on: what they name is the difference between a working install and one
        # that deletes itself on the user's next tidy-up — and, for the other two,
        # a setting or a plugin that has silently done nothing since the rename.
        # They live HERE rather than inside the one-time sweep because a notice
        # printed once, during a migration nobody is watching, is not a notice.
        for _warn in (_migrate.coinstalled_warning(), _migrate.stale_env_warning(),
                      _migrate.stale_plugin_warning()):
            if not _warn:
                continue
            # `from .config import C_RESET` HERE would make C_RESET a local of
            # run(), which every nested closure below then resolves from this
            # scope instead of the module — unbound on every start where this
            # branch does not run, which is all of them once the user has acted.
            # Reading the colours off the module at use time is also the rule
            # statusline.py learned: `from .config import C_WARN as _WARN` froze
            # the palette at import and apply_theme could never move it.
            from . import config as _cfg
            print(f'{_cfg.C_WARN}!{_cfg.C_RESET} {_warn}\n')
    except Exception:
        pass          # a migration must never be the reason archeus won't start
    try:
        from .config import migrate_settings
        _s, _changed = migrate_settings(load_settings())
        if _changed:
            save_settings(_s)
    except Exception:
        pass          # a migration must never be the reason archeus won't start
    try:
        # the private skill library moves into <account>/skills, which is the
        # only place Claude Code reads. Guarded by its own settings flag, so
        # this is one listdir on every later start.
        from .skills import migrate_library
        migrate_library()
    except Exception:
        pass

    # ── is archeus itself out of date? ──────────────────────────
    # ABOVE the interface pick, so the GUI gets it too — that branch returns.
    # BELOW the scriptable dispatches above, so `archeus statusline` (every
    # conversation turn) never starts a thread or reads this setting.
    # The check is a daemon thread and every reader takes its cache; the install
    # is deferred to exit, because pip cannot rewrite the console script of the
    # process running from it.
    from . import versions as _versions
    _versions.start_background_check()
    atexit.register(_versions.update_on_quit)

    # ── and is the MODEL list out of date? ────────────────────────
    # Same thread discipline, same TTL gate, same silence on failure. This is
    # what puts a model released last week into the launch picker without a
    # archeus release; nothing downstream fetches, they all read its cache.
    from . import models as _models
    _models.refresh_in_background()

    # ── interface pick: --gui / --tui flags beat the ui_mode setting ──
    if '--gui' in sys.argv[1:] or (
            '--tui' not in sys.argv[1:]
            and load_settings().get('ui_mode') == 'gui'):
        from .gui import run_gui
        run_gui()
        return

    # ── UTF-8 console ─────────────────────────────────────────────
    if os.name == 'nt':      # POSIX terminals are already UTF-8
        os.system('chcp 65001 >nul 2>&1')
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    # Alternate screen buffer + hidden cursor for the whole TUI session.
    # Restored before claude.exe takes the console (atexit = safety net).
    render.screen_init()
    atexit.register(render.screen_restore)

    # ── background memory, in the TUI too ─────────────────────────
    # Same daemon-thread pass the GUI runs. It had exactly one caller, in
    # run_gui, so "keep this project's memory updated automatically" silently
    # meant "while the GUI window is open" — a TUI user's opted-in projects were
    # only ever refreshed by the one-shot spawn when they happened to open one.
    # Below the --gui branch, which returns, so this starts once per interface.
    try:
        from .gui_api import start_auto_memory_scheduler
        start_auto_memory_scheduler()
    except Exception:
        pass          # background memory must never be why the TUI won't start

    # ── claude.exe availability check ─────────────────────────────
    if not get_claude_exe():
        _cls()
        print(f"\n  {C_TITLE}{C_BOLD}claude.exe not found{C_RESET}\n")
        print(f"  archeus could not locate Claude Code. Checked:")
        print(f"    - %USERPROFILE%\\.local\\bin\\claude.exe")
        print(f"    - PATH (claude / claude.exe)")
        print(f"    - settings override (~/.claude/archeus.json)\n")
        print(f"  Install Claude Code:  https://docs.anthropic.com/claude-code")
        print(f"  Or set the path in Settings (⚙) after continuing.\n")
        pause("  Press Enter to continue anyway...")

    # ── discover projects ─────────────────────────────────────────

    # Every known home, not just the active account, so sessions started under
    # another account — or under another CLI entirely — stay reachable here.
    entries = store.all_projects()

    if not entries:
        _cls()
        print(f"  No Claude sessions found.\n  Scanned: {projects_dir}")
        pause("\n  Press Enter to exit...")
        sys.exit(0)

    W = 62

    # Same real path can show up under several accounts (each account has its
    # own <cfgdir>/projects/<encoded> folder). Collapse those into ONE row —
    # default account wins as primary, other accounts' sessions are merged in
    # and highlighted once the project is opened (see sessions_menu below).
    from .context_inject import _account_name_for
    _acct_order = {d: i for i, (_n, d) in enumerate(all_config_dirs())}
    _groups = {}   # encoded_name -> {'path', 'dirs': set(acct_dir), 'mtime'}
    for mtime, actual, name, acct_dir in entries:
        g = _groups.setdefault(name, {'path': actual, 'dirs': set(), 'mtime': mtime})
        g['dirs'].add(acct_dir)
        g['mtime'] = max(g['mtime'], mtime)
    grouped = []   # [(mtime, path, encoded_name, primary_dir, [other_dirs...])]
    for name, g in _groups.items():
        dirs_sorted = sorted(g['dirs'], key=lambda d: _acct_order.get(d, 999))
        grouped.append((g['mtime'], g['path'], name, dirs_sorted[0], dirs_sorted[1:]))
    grouped.sort(reverse=True, key=lambda r: r[0])

    _default_acct_dir = all_config_dirs()[0][1]
    all_recent = load_recent_sessions(5)

    def _build_items():
        """(visible projects, visible recents, menu rows).

        Rebuilt on every pass of the loop below, because hiding a project
        changes what belongs in the menu — and the `__proj_N__` / `__quickresume_N__`
        values index the FILTERED lists, so they are returned together with it.
        """
        from .config import hidden_projects
        hidden  = hidden_projects()
        visible = [g for g in grouped if g[2] not in hidden]
        recent  = [s for s in all_recent if s.get('encoded_name', '') not in hidden]

        project_items = []
        for i, (_, p, _n, primary_dir, other_dirs) in enumerate(visible):
            if other_dirs:
                names = ', '.join(_account_name_for(d) for d in other_dirs)
                tag = f"  {C_DIM}[+{names}]{C_RESET}"
            elif primary_dir != _default_acct_dir:
                tag = f"  {C_DIM}[{os.path.basename(primary_dir)}]{C_RESET}"
            else:
                tag = ''
            project_items.append((f"{os.path.basename(p) or p:<28}  {p}{tag}", f'__proj_{i}__'))

        qr_items = []
        for i, sess in enumerate(recent):
            lr_proj    = os.path.basename(sess['project_path']) or sess['project_path']
            sid        = sess['session_id']
            _enc       = sess.get('encoded_name', '')
            pf         = store.project_folder(sess.get('cfgdir'), _enc) if _enc else ''
            jsonl      = store.transcript_path(pf, sid)
            # Session name: manual rename > AI transcript title > preview > id.
            lr_name    = (load_name(pf, sid) or get_session_title(jsonl)
                          or sess.get('preview', '') or sid[:8] + '…')
            lr_age     = format_age(sess['timestamp'])
            star = '★' if i == 0 else '☆'
            # callable label → re-laid-out on every draw (adapts to resize)
            label = (lambda star=star, proj=lr_proj, nm=lr_name, age=lr_age:
                     render.cols(
                         [f"{C_STAR}{star}{C_RESET}", proj,
                          f"{C_NAME}{nm}{C_RESET}",
                          f"{C_DIM}({age.strip()}){C_RESET}"],
                         [3, 18, None, 7],
                         aligns=['left', 'left', 'left', 'right']))
            qr_items.append((label, f"__quickresume_{i}__"))

        rows = (qr_items + [(f"{'─' * W}", None)] + project_items) if qr_items \
            else project_items
        rows = rows + [(f"{'─' * W}", None)] + \
            [(_dim_unavailable(label, key), key)
             for label, key, _route in MAIN_ACTIONS
             if key in MAIN_TOP and key != '__help__'] + \
            [(f"⚙  {label}…", f'__sec_{label}__') for label, _keys in MAIN_SECTIONS] + \
            [(label, key) for label, key, _route in MAIN_ACTIONS
             if key == '__help__']
        if len(visible) < len(grouped):
            rows = rows + [(f"{C_DIM}  {len(grouped) - len(visible)} project(s) hidden"
                            f"{C_RESET}", None)]
        return visible, recent, rows

    # ── main loop ─────────────────────────────────────────────────

    _EMPTY_OPTS = {'effort': '', 'model': '', 'perm': '', 'name': '', 'worktree': '',
                   'agent': '', 'cfgdir': '', 'max_thinking': '', 'subagent_model': '',
                   'provider': '', 'provider_model': ''}
    path = encoded_name = proj_folder = choice = None
    opts = dict(_EMPTY_OPTS)

    def _banner():
        """Plan usage, plus the update notice when there is one. menu() splits
        this on newlines, so two facts stack rather than compete for one row."""
        lines = [x for x in (_versions.update_notice(), usage_status_line()) if x]
        return '\n'.join(lines)

    while True:
        visible, recent, full_items = _build_items()
        sel = menu(full_items, "SELECT PROJECT",
                   footer_fn=mcp_status_line, banner_fn=_banner)
        if not sel:
            sys.exit(0)

        opts = dict(_EMPTY_OPTS)   # fresh each iteration (launch_options_menu may have returned None on ESC)

        # A section row is not an action: it opens the submenu and then hands
        # the chosen key to the SAME dispatch chain below, so every branch there
        # is untouched by the regrouping. A one-row section skips the menu — a
        # list of one is a keystroke spent on nothing.
        if sel and sel.startswith('__sec_'):
            label = sel[len('__sec_'):-2]
            keys = dict(MAIN_SECTIONS)[label]
            # in the SECTION's order, not the table's: the table is ordered by
            # the history of the menu it used to be, and reading its order back
            # out put `Updates` above `Settings` inside Settings
            labels = {key: lbl for lbl, key, _route in MAIN_ACTIONS}
            sub_items = [(_dim_unavailable(labels[k], k), k)
                         for k in keys if k in labels]
            sel = (sub_items[0][1] if len(sub_items) == 1
                   else menu(sub_items, label.upper()))
            if not sel:
                continue

        # a row whose capability this account's CLI does not have says so and
        # goes back, rather than opening a screen that can only be empty
        if sel:
            _ok, _why = _cap_of_row(sel)
            if not _ok:
                from .ui import flash
                flash(_why)
                continue

        if sel and sel.startswith('__quickresume_'):
            idx  = int(sel[len('__quickresume_'):-2])
            sess = recent[idx]
            path         = sess['project_path']
            encoded_name = sess['encoded_name']
            sess_cfgdir  = sess.get('cfgdir') or config_dir
            opts['cfgdir'] = sess_cfgdir if sess_cfgdir != config_dir else ''
            proj_folder  = store.project_folder(sess_cfgdir, encoded_name)
            choice       = f"resume:{sess['session_id']}"

        elif sel == '__open_path__':
            from .ui import path_input
            from .paths import encode_component
            p = path_input("Open Claude in which folder?  (TAB to complete)")
            if not p:
                continue
            path = os.path.abspath(p)
            encoded_name = encode_component(path)
            proj_folder  = os.path.join(projects_dir, encoded_name)
            project_name = os.path.basename(path) or path
            # The project SCREEN, like __proj_ below — opening a folder is how
            # you reach its sessions and memory, not a shortcut to one launch.
            choice, foreign_dir = sessions_menu(scan_sessions(proj_folder),
                                                proj_folder, project_name, path)
            if not choice:
                continue
            if foreign_dir:
                opts['cfgdir'] = foreign_dir if foreign_dir != config_dir else ''

        elif sel == '__search_all__':
            from .search import global_search
            hit = global_search(entries)
            if not hit:
                continue
            _, path, encoded_name, sid, acct_dir = hit
            opts['cfgdir'] = acct_dir if acct_dir != config_dir else ''
            proj_folder = store.project_folder(acct_dir, encoded_name)
            choice      = f"resume:{sid}"

        elif sel == '__usage_stats__':
            from .stats import usage_dashboard
            usage_dashboard(entries)
            continue

        elif sel == '__mcp__':
            mcp_manager_menu()
            continue

        elif sel == '__agents__':
            from .agents import agents_menu
            agents_menu(None)
            continue

        elif sel == '__skills__':
            from .skills import skills_menu
            skills_menu(None)
            continue

        elif sel == '__hooks__':
            from .hooks import hooks_menu
            hooks_menu()
            continue

        elif sel == '__updates__':
            from .versions import updates_menu
            updates_menu()
            continue

        elif sel == '__global_claude_md__':
            global_claude_md_menu()
            continue

        elif sel == '__accounts__':
            from .accounts import accounts_menu
            accounts_menu()
            continue

        elif sel == '__harnesses__':
            _harnesses_screen()
            continue

        elif sel == '__settings__':
            settings_menu()
            continue

        elif sel == '__logs__':
            from .events import logs_screen
            logs_screen()
            continue

        elif sel == '__hidden_projects__':
            _hidden_projects_menu(grouped)
            continue

        elif sel == '__help__':
            help_screen()
            continue

        elif sel and sel.startswith('__proj_'):
            idx = int(sel[len('__proj_'):-2])
            _, path, encoded_name, primary_dir, other_dirs = visible[idx]
            opts['cfgdir'] = primary_dir if primary_dir != config_dir else ''
            proj_folder  = store.project_folder(primary_dir, encoded_name)

            sessions = scan_sessions(proj_folder)
            extra_accounts = [(_account_name_for(d), store.project_folder(d, encoded_name))
                              for d in other_dirs] or None

            project_name = os.path.basename(path) or path
            choice, foreign_dir = sessions_menu(sessions, proj_folder, project_name, path,
                                                extra_accounts=extra_accounts)
            if not choice:
                continue
            if foreign_dir:
                opts['cfgdir'] = foreign_dir if foreign_dir != config_dir else ''

        # Launch options (skip for terminal); ESC = back to main menu
        if choice == 'terminal':
            break
        settings = load_settings()
        proj_def = settings.get('project_defaults', {}).get(encoded_name or '', {})
        from .agents import list_all_agent_names, sync_project_agents
        from .sessions import load_session_agents

        # Library agents are selected at PROJECT level ('g' in the sessions
        # menu) and live in <project>/.claude/agents/. They apply to every
        # launch of the project, so the launch flow just reflects + re-syncs
        # the current project selection rather than prompting per session.
        chosen_refs = load_session_agents(proj_folder).get('__project__', []) if proj_folder else []

        try:
            from . import recall
            mem_line = recall.memory_status_line(path, proj_folder, settings)
        except Exception:
            mem_line = ''
        # per-launch account choice. For a NEW session pre-select the ACTIVE
        # account (what the user expects to create under); for resume the field
        # is read-only and just reflects the account the session lives under, so
        # pre-select that. Sorting decides the picker's default (index 0).
        project_cfgdir = os.path.abspath(opts.get('cfgdir') or config_dir)
        preselect = os.path.abspath(config_dir) if choice == 'new' else project_cfgdir
        acct_opts = []
        try:
            from .accounts import _accounts
            accs = _accounts(settings)
            if len(accs) > 1:
                def _abs(dd):
                    return (os.path.expanduser(os.path.expandvars(dd)) if dd
                            else os.path.expanduser('~/.claude'))
                acct_opts = [(n, _abs(dd)) for n, dd, a in accs]
                acct_opts.sort(key=lambda t: os.path.abspath(t[1]) != preselect)
        except Exception:
            acct_opts = []
        opts = launch_options_menu(
            os.path.basename(path) or path,
            defaults={
                'effort':     proj_def.get('effort', settings.get('default_effort', '')),
                'model':      proj_def.get('model', settings.get('default_model', '')),
                'permission': proj_def.get('permission', settings.get('default_permission', '')),
                'max_thinking':   proj_def.get('max_thinking', settings.get('default_max_thinking', '')),
                'subagent_model': proj_def.get('subagent_model', settings.get('default_subagent_model', '')),
            },
            is_new=(choice == 'new'),
            agents=list_all_agent_names(path),
            selected_session_agents=chosen_refs,
            memory_status=mem_line,
            account_opts=acct_opts,
        )
        if opts is None:
            choice = None
            continue
        # launch_options_menu's account picker only shows (and can only set
        # cfgdir) when the user has explicitly added extra accounts — without
        # that picker it always returns cfgdir=''. Don't let that blank out
        # the project's real account when one was already resolved above.
        if not opts.get('cfgdir') and project_cfgdir != os.path.abspath(config_dir):
            opts['cfgdir'] = project_cfgdir
        # Re-sync in case the project .claude/agents/ drifted; safe no-op when
        # the selection already matches. Inline --agents is avoided because its
        # JSON overruns the Windows command line for real agents.
        sync_project_agents(path, chosen_refs,
                            routed=bool(opts.get('provider')))
        # Remember per-project launch choices
        if encoded_name:
            settings.setdefault('project_defaults', {})[encoded_name] = {
                'effort': opts['effort'], 'model': opts['model'],
                'permission': opts['perm'],
                'max_thinking': opts.get('max_thinking', ''),
                'subagent_model': opts.get('subagent_model', ''),
            }
            save_settings(settings)
        # ── which backend this session runs on ───────────────────
        # The profile list is LOCAL, so offering it reaches nothing and cannot
        # fail. Only the second step — a live OmniRoute catalogue — can, and it
        # is the only part inside a try. The whole block used to be, so an
        # unreachable backend made the picker vanish and the session opened on
        # Anthropic with nothing anywhere saying so.
        _profs = _c.provider_profiles(settings)
        if _profs:
            _pv_opts = [('○  Anthropic (your account)', '')]
            _pv_opts += [('●  %s  %s' % (p['name'], p.get('model') or ''), p['id'])
                         for p in _profs]
            _pid = menu(_pv_opts, "PROVIDER")
            if _pid:
                opts['provider'] = _pid
                prof = _c.provider_profile(_pid, settings)
                opts['provider_model'] = _pick_provider_model(prof)
        break

    if choice == 'terminal':
        opts = {'effort': '', 'model': '', 'perm': '', 'name': '', 'worktree': '', 'agent': ''}
    opts.setdefault('agent', '')
    opts.setdefault('agents_json', '')
    opts.setdefault('max_thinking', '')
    opts.setdefault('subagent_model', '')
    opts.setdefault('provider', '')
    opts.setdefault('provider_model', '')

    # Persist last session for quick-resume (resume/fork only)
    if choice and choice not in ('terminal', 'new', 'continue'):
        sid = choice.split('::')[1] if '::' in choice else \
              (choice.split(':')[1] if ':' in choice else '')
        if sid:
            save_last_session(path, encoded_name, sid, cfgdir=opts.get('cfgdir') or config_dir)

    # Validate action format before handing to the bat launcher
    valid = (
        choice in ('terminal', 'new', 'continue')
        or (choice.startswith('resume:') and len(choice) > 7)
        or (choice.startswith('fork:') and len(choice) > 5)
        or (choice.startswith('resume-named::') and '::' in choice[14:])
    )
    if not valid:
        _cls()
        print(f"\n  Cannot launch: unrecognized session action {choice!r}.")
        print("  Expected one of: terminal, new, continue, resume:<id>,")
        print("  fork:<id>, resume-named:<id>::<name>.")
        print("\n  Nothing was launched and nothing was changed. This is a bug in")
        print("  archeus rather than something you did — please report it with")
        print("  the action shown above:")
        print("  https://github.com/babarmuhammad/archeus/issues")
        pause("\n  Press Enter to exit...")
        sys.exit(1)
    # '|' is the choice-file delimiter. Strip it from user-typed fields
    # (name/worktree) rather than aborting — only path/config_dir we can't fix.
    opts['name']     = opts['name'].replace('|', '')
    opts['worktree'] = opts['worktree'].replace('|', '')
    opts['agent']    = opts.get('agent', '').replace('|', '')
    if '|' in f"{path}{encoded_name or ''}{config_dir}{opts.get('cfgdir', '')}":
        _cls()
        bad = [lbl for lbl, v in (('project path', path),
                                  ('session folder name', encoded_name or ''),
                                  ('config dir', config_dir),
                                  ('account config dir', opts.get('cfgdir', '')))
               if '|' in (v or '')]
        print("\n  Cannot launch: a '|' character appears in the "
              + ' and the '.join(bad) + '.')
        print("  archeus hands the launch options to the new console as a")
        print("  '|'-separated line, so a '|' inside a path would split it apart.")
        print("\n  Fix: rename the folder to remove the '|' — Windows permits it in")
        print("  a path but very little tooling handles it — or move the project.")
        pause("\n  Press Enter to exit...")
        sys.exit(1)

    # cmd reads the choice file in the ANSI codepage — keep bat-bound
    # name/worktree ASCII-safe (direct launch is unaffected).
    if os.environ.get('ARCHEUS_BAT') == '1':
        opts['name']     = opts['name'].encode('ascii', 'ignore').decode()
        opts['worktree'] = opts['worktree'].encode('ascii', 'ignore').decode()

    # Leave the alt screen before anything else owns the console
    render.screen_restore()

    with open(choice_file, 'w', encoding='utf-8', newline='') as f:
        f.write(build_choice_line(path, encoded_name, choice, opts) + '\r\n')

    # Launch is unified in Python: the bat re-invokes this script with --launch
    # (so it can pass big --agents JSON the cmd choice-file can't hold), and the
    # pipx/standalone path launches inline here.
    if os.environ.get('ARCHEUS_BAT') != '1':
        _direct_launch(path, encoded_name, choice, opts)


def _pick_provider_model(prof):
    """The model id for a session on *prof*, or its configured default.

    The two kinds get different pickers because they have different amounts of
    truth available: OmniRoute publishes a live catalogue, a generic
    Anthropic-shaped server publishes nothing, so offering a menu there would
    mean inventing its contents.

    Only the catalogue fetch can fail, and failing it falls back to the
    profile's own model rather than to Anthropic — the user has already said
    which backend they want by this point."""
    if not prof:
        return ''
    default = prof.get('model') or ''
    if (prof.get('kind') or '') != 'omniroute':
        from .ui import text_input
        return text_input('Model id', default) or default
    try:
        from . import omniroute as _om
        models = _om.list_models(prof.get('base_url', ''), prof.get('api_key', ''))
    except Exception:
        models = []
    if not models:
        return default
    from . import omniroute as _om
    opts = [('◉  auto/coding (dynamic router)', _om.AUTO_MODEL)]
    opts += [(f'●  {lbl}', mid) for mid, lbl in models]
    return menu(opts, 'MODEL  /  %s' % prof['name']) or default


def build_choice_line(path, encoded_name, choice, opts):
    """v8 choice-file line. Sentinel '-' for empty fields: cmd's for /f
    collapses consecutive delimiters, which silently shifted fields in the
    old 5-field format. v3 added config_dir; v4 the --agent name; v5 a path
    to a temp JSON file of selected subagents (--agents); v6 the launch-economy
    env values (MAX_THINKING_TOKENS, CLAUDE_CODE_SUBAGENT_MODEL); v7 the routed
    model; v8 splits that into the PROFILE and the model within it.

    Each of v7 and v8 exists because a field was genuinely missing, not for
    symmetry: the bat launcher round-trips the whole launch through this line,
    so a pick the line cannot carry is silently dropped and the session runs on
    Anthropic while the picker said otherwise. v7 carried a model id and no
    backend identity, which is the same hole one level up."""
    def sv(x):
        return str(x).replace('|', '') if x else '-'
    return '|'.join(['v8', path, encoded_name or '-', choice,
                     sv(opts['effort']), sv(opts['model']), sv(opts['perm']),
                     sv(opts['name']), sv(opts['worktree']),
                     sv(opts.get('cfgdir') or config_dir),
                     sv(opts.get('agent', '')), sv(opts.get('agents_json', '')),
                     sv(opts.get('max_thinking', '')),
                     sv(opts.get('subagent_model', '')),
                     sv(opts.get('provider', '')),
                     sv(opts.get('provider_model', ''))])


def parse_choice_line(line):
    """Parse any choice-file version → (path, encoded_name, choice, opts).
    opts always has effort/model/perm/name/worktree/agent/agents_json/cfgdir
    + max_thinking/subagent_model/provider."""
    t = line.rstrip('\r\n').split('|')
    def g(i):
        v = t[i] if i < len(t) else ''
        return '' if v == '-' else v
    opts = {'effort': '', 'model': '', 'perm': '', 'name': '',
            'worktree': '', 'agent': '', 'agents_json': '', 'cfgdir': '',
            'max_thinking': '', 'subagent_model': '', 'provider': '',
            'provider_model': ''}
    if t and t[0] == 'v8':
        path, enc, choice = g(1), g(2), g(3)
        opts.update(effort=g(4), model=g(5), perm=g(6), name=g(7),
                    worktree=g(8), cfgdir=g(9), agent=g(10), agents_json=g(11),
                    max_thinking=g(12), subagent_model=g(13), provider=g(14),
                    provider_model=g(15))
    elif t and t[0] == 'v7':
        # field 14 was a MODEL id, with no backend named. Read it as the model
        # on the active profile: that is what it meant when it was written, and
        # a v7 line can be sitting in %TEMP% at the moment of upgrade.
        path, enc, choice = g(1), g(2), g(3)
        opts.update(effort=g(4), model=g(5), perm=g(6), name=g(7),
                    worktree=g(8), cfgdir=g(9), agent=g(10), agents_json=g(11),
                    max_thinking=g(12), subagent_model=g(13),
                    provider_model=g(14))
        if opts['provider_model']:
            _act = _c.active_provider()
            opts['provider'] = _act['id'] if _act else ''
    elif t and t[0] == 'v6':
        path, enc, choice = g(1), g(2), g(3)
        opts.update(effort=g(4), model=g(5), perm=g(6), name=g(7),
                    worktree=g(8), cfgdir=g(9), agent=g(10), agents_json=g(11),
                    max_thinking=g(12), subagent_model=g(13))
    elif t and t[0] == 'v5':
        path, enc, choice = g(1), g(2), g(3)
        opts.update(effort=g(4), model=g(5), perm=g(6), name=g(7),
                    worktree=g(8), cfgdir=g(9), agent=g(10), agents_json=g(11))
    elif t and t[0] == 'v4':
        path, enc, choice = g(1), g(2), g(3)
        opts.update(effort=g(4), model=g(5), perm=g(6), name=g(7),
                    worktree=g(8), cfgdir=g(9), agent=g(10))
    elif t and t[0] == 'v3':
        path, enc, choice = g(1), g(2), g(3)
        opts.update(effort=g(4), model=g(5), perm=g(6), name=g(7),
                    worktree=g(8), cfgdir=g(9))
    elif t and t[0] == 'v2':
        path, enc, choice = g(1), g(2), g(3)
        opts.update(effort=g(4), model=g(5), perm=g(6), name=g(7), worktree=g(8))
    else:   # legacy 5-field: path|enc|action|effort|model
        path, enc, choice = g(0), g(1), g(2)
        opts.update(effort=g(3), model=g(4))
    return path, enc, choice, opts


def launch_from_choice():
    """Read the choice file and launch claude (invoked by the bat as --launch)."""
    try:
        with open(choice_file, 'r', encoding='utf-8') as f:
            line = f.read()
    except Exception:
        return
    try:
        os.remove(choice_file)
    except Exception:
        pass
    path, enc, choice, opts = parse_choice_line(line)
    _direct_launch(path, enc, choice, opts)


def build_launch_command(path, encoded_name, choice, opts):
    """Pure launch assembly shared by the TUI and GUI paths. Returns
    (args, env, proj_folder): the claude.exe argv, the child environment,
    and the account project folder. args is None when choice == 'terminal'
    (caller opens a plain shell) — and raises RuntimeError if claude.exe
    can't be found."""
    from .sessions import read_extra_paths, load_add_dirs

    # config dir: from the choice line (bat path) else whichever account the
    # rotation policy elects — which is the active one unless it has run out, so
    # with rotation off, or nothing spent, this is the module default it always
    # was. An EXPLICIT cfgdir always wins: picking an account in the launch
    # window is a decision, not a preference to be second-guessed.
    from . import rotate
    cfgdir = opts.get('cfgdir') or rotate.elect()
    proj_folder = store.project_folder(cfgdir, encoded_name) if encoded_name else None

    # Pins the home explicitly — overriding any ambient one archeus itself was
    # launched under — and pops the key that would shadow that home's login.
    # Both are per harness, which is why this is `account_env` and not two
    # lines: `CLAUDE_CONFIG_DIR` means nothing to Codex, and clearing
    # `ANTHROPIC_API_KEY` for it would be clearing the wrong one.
    from .config import account_env
    env = account_env(cfgdir)
    # OpenTelemetry export, if configured. archeus already owns the launch
    # environment, so this is the natural place for it — and it is the step from
    # a personal tool to one a team can point at a shared backend.
    from .config import otel_env
    # one read, two consumers: otel_env() would otherwise load it again, and the
    # fallback/autocompact flags below need the same dict
    settings = load_settings()
    env.update(otel_env(settings))
    extra = read_extra_paths(proj_folder)
    if extra:
        env['PATH'] = ';'.join(extra) + ';' + env.get('PATH', '')

    if choice == 'terminal':
        return None, env, proj_folder

    # ── which CLI is being launched ───────────────────────────
    # Everything ABOVE this line is archeus's: the project folder, the extra
    # PATH, the telemetry, the home. Everything BELOW it is Claude Code's flag
    # vocabulary, down to the last one — so a second harness gets its own short
    # builder rather than a branch per flag through a hundred and forty lines.
    #
    # The project's extra directories are archeus's too, and they were on the
    # wrong side of it: `load_add_dirs` ran a hundred lines below this return,
    # so `codex.launch_argv` read an `add_dirs` nothing ever set. A project's
    # extra dirs applied under Claude Code and vanished under Codex, silently.
    # The same argument covers the per-project system prompt, which pi takes as
    # `--append-system-prompt`.
    opts = dict(opts)
    opts.setdefault('add_dirs',
                    [x for x in load_add_dirs(proj_folder) if os.path.isdir(x)])
    _sp = os.path.join(proj_folder, 'system-prompt.txt') if proj_folder else ''
    if _sp and os.path.exists(_sp):
        opts.setdefault('system_prompt_file', _sp)
    d = _harnesses.of(cfgdir)
    if d['id'] != _harnesses.DEFAULT:
        exe = _harnesses.exe(d['id'])
        if not exe:
            raise RuntimeError('%s not found' % d['label'])
        argv = _harnesses.impl('launch_argv', d['id'])(exe, choice, opts, path)
        return argv, env, proj_folder

    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    # launch-economy env: cap thinking tokens / route subagents to a cheap model
    if opts.get('max_thinking'):
        env['MAX_THINKING_TOKENS'] = str(opts['max_thinking'])
    if opts.get('subagent_model'):
        env['CLAUDE_CODE_SUBAGENT_MODEL'] = opts['subagent_model']

    claude = get_claude_exe()
    if not claude:
        raise RuntimeError('claude.exe not found')

    args = [claude]
    if choice == 'continue':
        args += ['-c']
    elif choice.startswith('resume:'):
        args += ['-r', choice[7:]]
    elif choice.startswith('resume-named::'):
        args += ['-r', choice[14:].split('::', 1)[0]]
    elif choice.startswith('fork:'):
        args += ['-r', choice[5:], '--fork-session']
    # 'new' → no extra args

    if opts['effort']:
        args += ['--effort', opts['effort']]
    # Routed session: merge this PROFILE's env overrides + use the picked model.
    # The profile is resolved from the id the picker chose, never from whatever
    # is globally active — two sessions may be running on two backends.
    prof = _c.provider_profile(opts.get('provider', ''), settings)
    provider_model = (opts.get('provider_model') or
                      (prof or {}).get('model') or '') if prof else ''
    if prof:
        from .omniroute import prepare_launch
        pv_env, _warn = prepare_launch(provider_model, prof)
        env.update(pv_env)
    # ONE --model flag. The provider's model wins when there is one: it names a
    # model that backend serves, while opts['model'] is an Anthropic id the
    # backend cannot resolve. Both used to be emitted and the right one won only
    # because Claude Code's parser takes the later occurrence.
    launch_model = provider_model or opts['model']
    if launch_model:
        args += ['--model', launch_model]
    # Which backend a session ran on is RECORDED, not inferred. _used_provider
    # reads it back off the transcript's model ids, which cannot tell an
    # Anthropic model served THROUGH a provider from a direct run — sessions.py
    # says so itself. We know the answer here.
    #
    # A new session's id is ours to choose (`--session-id`), which is the only
    # way to have one before Claude Code has written a line; a resume keeps the
    # id it is resuming. A fork mints its own and `-c` picks one we have not
    # seen, so those two keep falling back to the inference.
    launched_sid = ''
    if choice == 'new':
        import uuid
        launched_sid = str(uuid.uuid4())
        args += ['--session-id', launched_sid]
    elif choice.startswith('resume:'):
        launched_sid = choice[7:]
    elif choice.startswith('resume-named::'):
        launched_sid = choice[14:].split('::', 1)[0]
    if launched_sid and proj_folder:
        from .sessions import save_session_provider
        save_session_provider(proj_folder, launched_sid,
                              prof['id'] if prof else '')
    # `auto` is dropped where the classifier cannot run — with a provider in
    # play the model is whatever that backend served, and the classifier is a
    # SEPARATE request that would go to the same base URL. The model check reads
    # the provider model when there is one, because that is the model the
    # session will actually be on.
    from .config import effective_perm
    perm = effective_perm(opts['perm'], provider_model or opts['model'],
                          provider_model)
    if perm:
        args += ['--permission-mode', perm]
    # Model fallback chain for an overloaded primary. Unrelated to failover.py,
    # which retries a DIFFERENT free-tier model through archeus's own proxy;
    # this is Claude Code's own retry against the Anthropic API.
    fbs = [m for m in (settings.get('launch_fallback_models') or []) if m]
    if fbs:
        args += ['--fallback-model', ','.join(fbs)]
    if settings.get('launch_autocompact'):
        args += ['--autocompact', settings['launch_autocompact']]
    if opts.get('agent'):
        args += ['--agent', opts['agent']]
    # Selected library agents are NOT passed inline (--agents JSON overruns the
    # Windows command line). They're copied into <project>/.claude/agents/ by
    # sync_project_agents at selection time, where Claude auto-discovers them.
    if choice == 'new':
        if opts['name']:
            args += ['-n', opts['name']]
        if opts['worktree'] == '*':
            args += ['-w']
        elif opts['worktree']:
            args += ['-w', opts['worktree']]
    # both resolved above the harness dispatch, so every CLI gets them
    if opts.get('system_prompt_file'):
        args += ['--system-prompt-file', opts['system_prompt_file']]
    if opts.get('add_dirs'):
        args += ['--add-dir', *opts['add_dirs']]
    # An opening message for an INTERACTIVE session — `claude "<text>"` submits
    # it as the first turn and leaves you in the session. It is last because it
    # is the CLI's positional argument, and it is the whole mechanism behind
    # starting a `/loop` from archeus: a loop is session-scoped, so there is
    # nothing to start except a session that begins by typing it.
    if opts.get('prompt'):
        args += [str(opts['prompt'])]
    return args, env, proj_folder


def _direct_launch(path, encoded_name, choice, opts):
    """Launch claude.exe (or a terminal) directly. Single launch path for
    both the bat (--launch) and pipx/standalone flows."""
    render.screen_restore()   # idempotent — console must be clean for claude

    try:
        args, env, proj_folder = build_launch_command(path, encoded_name, choice, opts)
    except RuntimeError:
        _cls()
        print(f"\n  ✘ claude.exe not found — cannot launch.")
        pause("\n  Press Enter to exit...")
        sys.exit(1)

    if args is None:   # choice == 'terminal'
        # In THIS window, not a new one — the TUI is exiting to hand the
        # console over. `shell=True` here passed a string to cmd for no reason;
        # the list form cannot be reinterpreted.
        subprocess.call(['cmd', '/k'] if os.name == 'nt'
                        else [os.environ.get('SHELL') or '/bin/sh'],
                        cwd=path, env=env)
        return

    try:
        from . import workspace
        workspace.update_manifest(path, proj_folder, 'launch', choice=choice,
                                  opts={k: opts.get(k) for k in ('effort', 'model', 'perm')})
    except Exception:
        pass

    _cls()
    print(f"  Location: {path}")
    print(f"  Action:   {choice}")
    print(f"  {'-' * 42}\n")
    import time as _time
    _launch_t = _time.time()
    try:
        subprocess.call(args, cwd=path, env=env)
    except Exception as e:
        print(f"\n  ✘ Launch failed: {e}")
        pause("\n  Press Enter to exit...")
        sys.exit(1)

    # context-loss insurance: log what this session did (goal + files touched)
    # so the next session can recall it even after /compact
    try:
        from . import health
        if proj_folder and os.path.isdir(proj_folder):
            newest = max((f for f in os.listdir(proj_folder) if f.endswith('.jsonl')),
                         key=lambda f: os.path.getmtime(os.path.join(proj_folder, f)),
                         default=None)
            if newest and os.path.getmtime(os.path.join(proj_folder, newest)) >= _launch_t:
                health.append_session_log(path, proj_folder, newest[:-6])
    except Exception:
        pass
