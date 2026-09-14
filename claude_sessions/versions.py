"""What version of Claude Code — or a plugin, or archeus itself — is
installed, what has been released, and updating it.

Five things worth knowing before changing this:

- **archeus's own update runs beside archeus, not inside it.** pip rewrites the
  console script (`Scripts/archeus.exe`) on every upgrade and Windows holds that
  file open while it is the running image, so an in-process install dies — and
  measurably worse than "dies": pip uninstalls the old package FIRST and then
  fails on the script, leaving nothing installed at all. `update_self()`
  therefore hands the install to a detached, windowless worker, which moves a
  locked script aside (a running image can be renamed, just not overwritten)
  and puts it back if the install fails. *Update now* installs immediately,
  with archeus still open; *install on quit* is the same worker told to wait for
  this PID first.

- **Nothing in that chain may run on `pythonw`.** The desktop shell does, so
  `sys.executable` is `pythonw.exe`, and a pythonw child writing to an inherited
  file handle gets `sys.stdout = None`: pip exits 1 having printed nothing, not
  even its traceback. Every spawn here goes through `proc.python_exe()`.

- **There is no official version-list endpoint.** The docs advertise
  `downloads.claude.ai/claude-code-releases/{latest,stable}/manifest.json`;
  both answer 404 today. The npm registry metadata for
  `@anthropic-ai/claude-code` is the only machine-readable list, and it carries
  the same `stable`/`latest` dist-tags Claude Code's own updater follows — so it
  is the source here, and a network failure is reported as a fact rather than
  guessed around.

- **A specific version can be pinned for Claude Code, not for a plugin.**
  `claude install <stable|latest|X.Y.Z>` takes a target; `claude plugin update`
  takes none, because the marketplace entry decides what "latest" is. The UI
  says so instead of offering a box that cannot work.

- **`claude plugin list --json` returns a bare ARRAY on 2.1.241**, not the
  `{"plugins":[…]}` object the docs describe — the same docs-versus-disk split
  already recorded for agent teams. Both shapes are accepted, disk first.

- **Reads never touch the network unless asked.** `released()` serves an hourly
  disk cache, so opening the screen costs nothing; `refresh=True` is what the
  user's explicit "check now" does.
"""

import json
import os
import re
import sys
import time

from . import config as _c
from . import jsonstore
from . import plugins
from . import proc

__all__ = ['installed_version', 'install_mode', 'local_versions', 'released',
           'status', 'update_claude', 'plugin_rows', 'update_plugin',
           'update_marketplaces', 'updates_menu',
           'self_installed', 'self_install_mode', 'self_released',
           'self_status', 'update_self', 'update_notice', 'console_scripts',
           'start_background_check', 'update_on_quit']

#: npm metadata for the published package. The `abbreviated` accept header keeps
#: this ~100KB instead of ~15MB: the full document carries every version's
#: complete manifest, and all we read is the version keys and the dist-tags.
NPM_URL = 'https://registry.npmjs.org/@anthropic-ai/claude-code'
NPM_ACCEPT = 'application/vnd.npm.install-v1+json'
CACHE_TTL = 3600
_TIMEOUT = 20

#: archeus publishes to PyPI from every v* tag (.github/workflows/release.yml),
#: so PyPI is both the release record AND the thing an update installs from —
#: unlike Claude Code, whose npm metadata is a stand-in for a missing endpoint.
SELF_PKG = 'archeus'
PYPI_URL = 'https://pypi.org/pypi/%s/json' % SELF_PKG
#: a day, not an hour: archeus releases are not hourly, and this check runs
#: unattended on a background thread rather than when a screen is opened.
SELF_TTL = 86400


def _cache_path():
    return os.path.join(_c.config_dir, 'archeus-versions.json')


def _update_log_path():
    """Where the detached upgrade worker writes. It has no console, so this
    file is the only record of a failed install."""
    return os.path.join(_c.config_dir, 'archeus-update.log')


def _self_cache_path():
    """A separate file from _cache_path(), deliberately: released() writes its
    whole document, so sharing one file would mean one fetch erasing the
    other's answer."""
    return os.path.join(_c.config_dir, 'archeus-self.json')


def _ver_key(v):
    return tuple(int(p) for p in re.findall(r'\d+', v)[:4] or [0])


def installed_version():
    """'2.1.241', or '' when claude.exe is missing or does not answer."""
    exe = _c.get_claude_exe()
    if not exe:
        return ''
    r = proc.run([exe, '--version'], timeout=60)
    m = re.search(r'\d+\.\d+\.\d+[\w.+-]*', (getattr(r, 'stdout', '') or ''))
    return m.group(0) if m else ''


def install_mode():
    """'native' | 'npm' | 'other' | '' — which installer owns the binary.

    It decides what an update even means: the native build updates itself and
    accepts a version target, while an npm install has to be updated through
    npm and ignores `claude install`.
    """
    exe = _c.get_claude_exe()
    if not exe:
        return ''
    low = os.path.normcase(exe)
    if os.path.isdir(os.path.expanduser('~/.local/share/claude/versions')) \
            and os.path.normcase(os.path.expanduser('~/.local/bin')) in low:
        return 'native'
    if 'npm' in low or 'node_modules' in low:
        return 'npm'
    return 'other'


def local_versions():
    """Native builds already on disk, newest first — what a rollback can reach
    without a download."""
    d = os.path.expanduser('~/.local/share/claude/versions')
    try:
        vs = [e for e in os.listdir(d) if re.match(r'^\d+\.\d+\.\d+', e)]
    except OSError:
        return []
    return sorted(vs, key=_ver_key, reverse=True)


def released(refresh=False):
    """{'latest','stable','versions'(newest first),'fetched','error'}.

    Served from an hourly disk cache; `refresh=True` forces the fetch. A failed
    fetch keeps the cached list and reports the error next to it, because a
    stale answer with a note beats an empty screen.
    """
    cached = jsonstore.load(_cache_path(), {})
    fresh = (isinstance(cached, dict) and cached.get('versions')
             and time.time() - float(cached.get('fetched') or 0) < CACHE_TTL)
    if fresh and not refresh:
        return dict(cached, error='')
    # imported HERE, not at module level: urllib pulls ssl and http.client, and
    # this module is on the path of `archeus --version` and of the version
    # banner — neither of which fetches anything.
    import urllib.error, urllib.request
    try:
        req = urllib.request.Request(NPM_URL, headers={'Accept': NPM_ACCEPT})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            doc = json.loads(resp.read().decode('utf-8', 'ignore'))
    except (urllib.error.URLError, OSError, ValueError) as e:
        keep = dict(cached) if isinstance(cached, dict) else {}
        keep.setdefault('versions', [])
        return dict(keep, error=str(e)[:200])
    tags = doc.get('dist-tags') or {}
    vs = sorted((doc.get('versions') or {}), key=_ver_key, reverse=True)
    out = {'latest': str(tags.get('latest') or ''),
           'stable': str(tags.get('stable') or ''),
           'versions': vs[:60], 'fetched': time.time()}
    jsonstore.save(_cache_path(), out)
    return dict(out, error='')


def _channel():
    from . import hooks
    return str((hooks._load().get('autoUpdatesChannel') or '')) or 'latest'


def status(refresh=False):
    """The whole answer to "am I current?" in one dict — the payload both the
    TUI screen and the GUI page render."""
    cur = installed_version()
    rel = released(refresh=refresh)
    vs = rel.get('versions') or []
    behind = vs.index(cur) if cur in vs else -1
    target = rel.get(_channel()) or rel.get('latest') or ''
    return {'installed': cur, 'mode': install_mode(), 'channel': _channel(),
            'latest': rel.get('latest', ''), 'stable': rel.get('stable', ''),
            'behind': behind, 'current': bool(cur and target and cur == target),
            'target': target, 'versions': vs, 'local': local_versions(),
            'error': rel.get('error', ''),
            'fetched': rel.get('fetched', 0)}


def update_claude(target=''):
    """(ok, message). No target updates to the configured channel's latest; a
    target pins that exact version (or the literal 'stable'/'latest').

    An npm install is reported rather than attempted: `claude install` writes
    the native build, which would leave two Claude Codes on the machine and the
    npm one still first on PATH.
    """
    mode = install_mode()
    if mode == 'npm':
        return False, ('installed through npm — update it with '
                       '`npm install -g @anthropic-ai/claude-code@%s`'
                       % (target or 'latest'))
    target = (target or '').strip()
    if target and not re.match(r'^(stable|latest|\d+\.\d+\.\d+[\w.+-]*)$', target):
        return False, 'not a version: %s' % target[:40]
    args = ['install', target] if target else ['update']
    # a download plus a binary swap; the 120s default is not enough
    return plugins._claude_cli(args, timeout=900)


# ── archeus itself ─────────────────────────────────────────

def _source_version():
    """The version out of the checkout's pyproject.toml, for an archeus that is
    not an installed distribution at all (`python claude-sessions.py`).

    Parsed with a regex rather than tomllib: requires-python is >=3.10 and
    tomllib landed in 3.11.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, 'pyproject.toml'), encoding='utf-8') as f:
            m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
    except OSError:
        return ''
    return m.group(1) if m else ''


def _running_from_source():
    """Is the code in this process the working tree rather than an installed
    copy? A repository marker beside the package is the signal.

    It has to be the LAYOUT and not the metadata, because the metadata lies: one
    `pip install -e .` or one `setup.py build` leaves `<repo>/archeus.egg-info`
    behind, `importlib.metadata` finds it (the checkout is first on sys.path),
    and it reports whatever version it was built at, for ever. Nothing removes
    it and nothing updates it.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return any(os.path.exists(os.path.join(root, name))
               for name in ('pyproject.toml', 'setup.py', '.git'))


def _dist():
    """The installed archeus distribution — but ONLY when it is the one this
    process is actually running from, and only when it is INSTALLED at all.

    Two ways to be wrong, and both have happened:

    - a checkout early on sys.path shadows an installed copy, so
      `distribution()` finds the site-packages dist-info while the code actually
      running is the working tree;
    - the reverse, which is worse because it looks like a healthy install: a
      stale `archeus.egg-info` sitting IN the checkout. Measured here — a 2.2.0
      working tree called itself a 2.1.0 pip install, so the banner offered
      2.2.0, pip answered "Requirement already satisfied" about a site-packages
      copy this process was not running, and the restart showed 2.1.0 and
      offered the update again. That loop is what the user reported as "it
      installs, then tells me a new version is available".

    Same discipline as checkpoints.py: what is on disk decides, not what a
    record claims about it.
    """
    if _running_from_source():
        return None
    try:
        from importlib.metadata import distribution
        d = distribution(SELF_PKG)
    except Exception:
        return None
    try:
        here = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
        theirs = os.path.normcase(os.path.abspath(str(d.locate_file(__package__))))
    except Exception:
        return d
    return d if here == theirs else None


#: memoised because the banner asks for it twice a second (ui.menu re-polls
#: banner_fn every 0.5s) and resolving a distribution walks sys.path. Safe to
#: hold for the process lifetime for the one reason a derived constant usually
#: is NOT: the installed version cannot change under a running process — an
#: upgrade replaces this process rather than mutating it.
_SELF_VER = None


def self_installed():
    """'1.6.0' — the running archeus's version, or '' when it cannot be told."""
    global _SELF_VER
    if _SELF_VER is None:
        d = _dist()
        ver = ''
        if d is not None:
            try:
                ver = str(d.version or '')
            except Exception:
                ver = ''
        _SELF_VER = ver or _source_version()
    return _SELF_VER


def self_install_mode():
    """'pipx' | 'pip' | 'checkout' | '' — which installer owns archeus.

    The same job install_mode() does for Claude Code, and it exists for the same
    reason: it decides what an update even means. `pipx upgrade` and
    `pip install -U` are not interchangeable, and a checkout has to be told to
    `git pull` rather than have a release installed over the top of it.
    """
    d = _dist()
    if d is None:
        return 'checkout' if _source_version() else ''
    try:
        raw = d.read_text('direct_url.json') or ''
    except Exception:
        raw = ''
    if raw:
        try:
            if ((json.loads(raw).get('dir_info') or {}).get('editable')):
                return 'checkout'                      # pip install -e .
        except ValueError:
            pass
    try:
        loc = os.path.normcase(str(d.locate_file('')))
    except Exception:
        loc = ''
    home = os.environ.get('PIPX_HOME') or ''
    if home and loc.startswith(os.path.normcase(os.path.abspath(os.path.expanduser(home)))):
        return 'pipx'
    parts = loc.replace('\\', '/').split('/')
    if 'pipx' in parts and 'venvs' in parts:
        return 'pipx'
    return 'pip'


def self_released(refresh=False):
    """{'latest','fetched','error'} for the published archeus, read from PyPI.

    Daily disk cache, and a failed fetch keeps the cached answer with the error
    beside it — the same contract as released(), for the same reason: a stale
    answer with a note beats an empty screen.
    """
    cached = jsonstore.load(_self_cache_path(), {})
    fresh = (isinstance(cached, dict) and cached.get('latest')
             and time.time() - float(cached.get('fetched') or 0) < SELF_TTL)
    if fresh and not refresh:
        return dict(cached, error='')
    import urllib.error, urllib.request     # see released(), same reason
    try:
        req = urllib.request.Request(
            PYPI_URL, headers={'Accept': 'application/json', 'User-Agent': 'archeus'})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            doc = json.loads(resp.read().decode('utf-8', 'ignore'))
    except (urllib.error.URLError, OSError, ValueError) as e:
        keep = dict(cached) if isinstance(cached, dict) else {}
        keep.setdefault('latest', '')
        return dict(keep, error=str(e)[:200])
    out = {'latest': str((doc.get('info') or {}).get('version') or ''),
           'fetched': time.time()}
    jsonstore.save(_self_cache_path(), out)
    return dict(out, error='')


def self_status(refresh=False):
    """"Is archeus itself current?" in one dict — the payload the banner, the
    TUI screen and the GUI card all render."""
    cur = self_installed()
    rel = self_released(refresh=refresh)
    latest = rel.get('latest', '')
    behind = bool(cur and latest and _ver_key(latest) > _ver_key(cur))
    return {'installed': cur, 'mode': self_install_mode(), 'latest': latest,
            'update': behind, 'current': bool(cur and latest and not behind),
            'error': rel.get('error', ''), 'fetched': rel.get('fetched', 0)}


def update_notice():
    """The one-line "archeus N is out" banner, or ''.

    CACHE ONLY — never a fetch. `ui.menu()` re-polls `banner_fn()` every 0.5
    seconds, so a network call on this path would be a stall twice a second,
    which is the same rule `repos.state(refresh=False)` follows.
    """
    cached = jsonstore.load(_self_cache_path(), {})
    latest = str((cached or {}).get('latest') or '')
    cur = self_installed()
    if not (latest and cur) or _ver_key(latest) <= _ver_key(cur):
        return ''
    mode = (_c.load_settings().get('auto_update') or 'notify')
    tail = ('installing when you quit' if mode == 'auto'
            else 'Updates ▸ Update archeus')
    return (f"  {_c.C_WARN}archeus {latest} available{_c.C_RESET}  "
            f"{_c.C_DIM}(you have {cur} — {tail}){_c.C_RESET}")


_bg_started = False


def start_background_check():
    """Refresh the PyPI answer once, on a daemon thread, if today's is stale.

    No re-poll loop (unlike usage.py's): archeus's published version cannot
    change in a way this process can act on while it runs, so one TTL-gated call
    per launch is the whole job. `self_released()` is already TTL-gated, so this
    is a no-op on every launch inside the day.
    """
    global _bg_started
    import threading
    if (_c.load_settings().get('auto_update') or 'notify') == 'off':
        return
    if _bg_started:
        return
    _bg_started = True

    def _work():
        try:
            self_released()
        except Exception:
            pass          # a version check must never be why archeus misbehaves

    threading.Thread(target=_work, daemon=True).start()


def update_on_quit():
    """Called at exit: install a pending update when the user asked for that.

    Reads the cache only — the same discipline as update_notice(), and for a
    stronger reason here: this runs during shutdown, where a hanging socket
    would be an archeus that will not close.
    """
    if (_c.load_settings().get('auto_update') or 'notify') != 'auto':
        return False, ''
    if not update_notice():
        return False, ''
    return update_self(defer=True)


def update_self(restart=False, defer=False, wait=0):
    """(ok, message). Hands the upgrade to a detached, WINDOWLESS worker.

    By default the install happens NOW, with archeus still open: the worker
    moves the console script aside if this process has it locked (a running
    image can be renamed, never overwritten) and pip writes a fresh one. The
    running process keeps the code it loaded — a restart is what picks the new
    version up — but the install itself no longer waits on anything.

    *defer* is the other half: wait for this PID to exit first. That is what
    "install on quit" means, and what *restart* needs, since relaunching while
    the old process is still up would be two archeuses.

    What it must NOT do is open a console. The worker may block on our pid, so a
    terminal for it was a window that took the foreground and then showed
    "Waiting for archeus to exit..." until the user quit — read, reasonably,
    as the update having hung. It is detached with its output in a log file.

    *wait* (seconds) makes this call BLOCK on the worker and report what
    actually happened, instead of reporting that a worker was started. Only
    useful without *defer*, and only for a caller that can afford to wait — the
    GUI job thread can, the TUI menu cannot.

    Both instructions travel in the ENVIRONMENT rather than in argv, so the
    command line stays exactly what __main__'s --self-update dispatch parses.

    A checkout is reported rather than overwritten, exactly as update_claude()
    reports an npm install instead of installing the native build over it.
    """
    mode = self_install_mode()
    if mode == 'checkout':
        return False, 'running from a checkout — update it with `git pull`'
    if not mode:
        return False, 'archeus is not an installed package — nothing to update'
    py = proc.python_exe()          # never pythonw: pip dies with no stdout
    upgrade = (['pipx', 'upgrade', SELF_PKG] if mode == 'pipx' else
               [py, '-m', 'pip', 'install', '-U', SELF_PKG])
    # `-m claude_sessions`, not `-c <script>`: a script argument carrying
    # newlines or quotes is a quoting hazard on every platform. __main__
    # dispatches --self-update before it imports anything else, so the waiting
    # process never holds a lazy import of the package pip is about to replace.
    argv = ([py, '-m', 'claude_sessions', '--self-update',
             str(os.getpid() if (defer or restart) else 0)] + upgrade)
    env = dict(os.environ)
    latest = str((jsonstore.load(_self_cache_path(), {}) or {}).get('latest') or '')
    env['ARCHEUS_UPDATE_TO'] = latest
    env['ARCHEUS_FREE'] = json.dumps(console_scripts())
    if restart:
        # `-m claude_sessions` again rather than sys.argv[0]: the console script
        # is the file pip is about to replace. `--gui` is forced when the
        # command line has no arguments of its own, because the only caller of
        # restart is the GUI and a detached TUI would come back invisible.
        tail = [a for a in sys.argv[1:]] or ['--gui']
        if '--gui' not in tail:
            tail.append('--gui')
        # sys.executable here, NOT python_exe(): the desktop app runs on
        # pythonw precisely so it has no console window, and relaunching it
        # on python.exe would bring it back with one.
        env['ARCHEUS_RELAUNCH'] = json.dumps(
            [sys.executable, '-m', 'claude_sessions'] + tail)
    p, err = proc.spawn_detached(argv, env=env, log=_update_log_path())
    if not p:
        return False, err or 'could not start the update worker'
    if restart:
        return True, 'Installing — archeus will close and come back'
    if defer:
        return True, 'Update staged — it installs when you close archeus'
    if wait:
        try:
            rc = p.wait(timeout=wait)
        except Exception:
            return True, 'Still installing in the background — see the update log'
        if rc:
            return False, _last_update_error() or (
                'the install failed — see %s' % _update_log_path())
        return True, ('Installed %s — restart archeus to use it' % latest
                      if latest else 'Installed — restart archeus to use it')
    return True, 'Installing in the background — restart archeus to use it'


def console_scripts():
    """The files pip would rewrite that THIS process might have locked.

    Only ever `<name>.exe` for our own distribution: the worker moves what this
    names out of the way, so it must not be able to name an interpreter. On
    POSIX nothing is locked and this is simply empty of effect.
    """
    import shutil
    out = []
    d = os.path.dirname(sys.executable or '')
    for cand in (sys.argv[0] if sys.argv else '', shutil.which(SELF_PKG) or '',
                 os.path.join(d, SELF_PKG + '.exe'),
                 os.path.join(d, 'Scripts', SELF_PKG + '.exe')):
        if not cand:
            continue
        cand = os.path.abspath(cand)
        if (os.path.basename(cand).lower() == SELF_PKG + '.exe'
                and os.path.isfile(cand) and cand not in out):
            out.append(cand)
    return out


def _last_update_error():
    """The line pip failed on, for a message the user can act on. The log is the
    worker's only voice — it has no console by design."""
    try:
        with open(_update_log_path(), encoding='utf-8', errors='replace') as f:
            lines = [ln.strip() for ln in f.read().splitlines()[-40:] if ln.strip()]
    except OSError:
        return ''
    for ln in reversed(lines):
        if ln.startswith('ERROR') or 'Error' in ln or ln.startswith('Failed'):
            return ln[:200]
    return lines[-1][:200] if lines else ''


# ── plugins ──────────────────────────────────────

def plugin_rows():
    """[{key,name,marketplace,version,available,outdated,scope,ref}] —
    every installed plugin joined to what its marketplace currently offers.

    Read entirely off disk, deliberately, and that is the whole finding here:

    - `claude plugin list --available --json` returns ONLY the official
      catalogue. Both of this machine's user marketplaces were absent from it,
      so a CLI-driven comparison silently reports "not checked" for exactly the
      plugins a user added themselves.
    - `git -C <clone> rev-parse HEAD` fails on those clones with *detected
      dubious ownership* (they are owned by BUILTIN\\Administrators), so the sha
      is read out of `.git` directly — the same thing the statusline already
      does for the branch, and for the same reason.

    `outdated` is None when the marketplace says nothing comparable, because
    "no answer" and "up to date" are different answers.
    """
    entries = _marketplace_entries()
    rows = []
    for p in plugins.installed():
        e = entries.get(p['key']) or {}
        avail, ref = _entry_version(e)
        cur = p['version'] or p['sha']
        rows.append({
            'key': p['key'], 'name': p['name'], 'marketplace': p['marketplace'],
            'version': p['version'], 'sha': p['sha'], 'scope': p.get('scope', ''),
            'available': avail, 'ref': ref,
            'outdated': (None if not (avail and cur)
                         else not _same_version(cur, avail, p['sha'])),
        })
    return rows


def _marketplace_entries(cfg_dir=None):
    """{'<plugin>@<marketplace>': manifest entry} from every registered
    marketplace's own `.claude-plugin/marketplace.json`."""
    out = {}
    for mkt in plugins.known_marketplaces(cfg_dir):
        root = mkt.get('path') or ''
        doc = plugins._read_json(
            os.path.join(root, '.claude-plugin', 'marketplace.json'), {})
        for e in (doc.get('plugins') or []) if isinstance(doc, dict) else []:
            if not isinstance(e, dict) or not e.get('name'):
                continue
            e = dict(e, _root=root)
            out['%s@%s' % (e['name'], mkt['name'])] = e
    return out


def _entry_version(entry):
    """(available, ref) for one marketplace entry.

    An entry either declares a `version`, or names a git source: a `sha` for a
    pinned subdirectory plugin, or `source: './'` for a plugin that IS its
    marketplace repo — in which case the clone's own HEAD is the version on
    offer, because that is what an update would install.
    """
    if not entry:
        return '', ''
    src = entry.get('source')
    src = src if isinstance(src, dict) else {'source': src}
    ver = str(entry.get('version') or '')
    ref = str(src.get('ref') or '')
    if ver:
        return ver, ref
    sha = str(src.get('sha') or '')
    if sha:
        return sha[:12], ref
    if str(src.get('source') or '').strip() in ('./', '.', ''):
        return _clone_head(entry.get('_root') or ''), ref
    return '', ref


def _clone_head(root):
    """The marketplace clone's HEAD sha, 12 chars, read out of `.git` without
    running git — see plugin_rows for why running it is not an option."""
    try:
        head = open(os.path.join(root, '.git', 'HEAD'), encoding='utf-8').read().strip()
    except OSError:
        return ''
    if not head.startswith('ref:'):
        return head[:12]
    ref = head[4:].strip()
    try:
        with open(os.path.join(root, '.git', *ref.split('/')), encoding='utf-8') as f:
            return f.read().strip()[:12]
    except OSError:
        pass
    try:
        with open(os.path.join(root, '.git', 'packed-refs'), encoding='utf-8') as f:
            for line in f:
                sha, _, name = line.strip().partition(' ')
                if name == ref:
                    return sha[:12]
    except OSError:
        pass
    return ''


def _same_version(cur, avail, sha=''):
    """Installed and offered describe the same thing. Two shapes meet here: a
    semver (`4.8.4` vs `v4.8.4`) and a git sha, which the installed side stores
    truncated to 12 characters while a manifest carries all 40."""
    cur, avail = cur.strip(), avail.strip()
    if cur == avail or cur.lstrip('v') == avail.lstrip('v'):
        return True
    for a, b in ((cur, avail), (avail, cur), (sha, avail), (avail, sha)):
        if a and b and len(a) >= 7 and b.startswith(a):
            return True
    return False


def update_plugin(key, cfgdir=None):
    """`claude plugin update <key> -y`. There is no version target: the
    marketplace entry decides what latest is, and -y is required off a TTY."""
    key = (key or '').strip()
    if not key:
        return False, 'No plugin given'
    return plugins._claude_cli(['plugin', 'update', key, '-y'], timeout=600,
                               cfgdir=cfgdir)


def update_marketplaces(name='', cfgdir=None):
    """Refresh marketplace metadata — what makes an `available` version move."""
    args = ['plugin', 'marketplace', 'update'] + ([name] if name else [])
    return plugins._claude_cli(args, timeout=600, cfgdir=cfgdir)


# ── the screen ───────────────────────────────────────────────

def _row(st):
    if not st['installed']:
        return 'claude.exe not found'
    if st['error']:
        return '%s   (could not reach the registry: %s)' % (st['installed'], st['error'])
    if st['current']:
        return '%s   up to date on the %s channel' % (st['installed'], st['channel'])
    behind = ('%d release%s behind' % (st['behind'], '' if st['behind'] == 1 else 's')
              if st['behind'] > 0 else 'update available')
    return '%s → %s   (%s)' % (st['installed'], st['target'] or '?', behind)


def _self_row(sst):
    if not sst['installed']:
        return 'version unknown'
    if sst['error']:
        return '%s   (could not reach PyPI: %s)' % (sst['installed'], sst['error'])
    if sst['update']:
        return '%s → %s   (update available)' % (sst['installed'], sst['latest'])
    if sst['current']:
        return '%s   up to date' % sst['installed']
    return sst['installed']


def _models_row(mst):
    """One line for the model catalogue: how many, how fresh, or that the
    picker is running on the bundled floor."""
    if not mst['live']:
        return (f"{_c.C_DIM}not fetched — the picker is showing "
                f"archeus's bundled list{_c.C_RESET}")
    age = mst['age']
    when = ('just now' if age < 90 else
            f"{int(age // 60)}m ago" if age < 5400 else
            f"{int(age // 3600)}h ago" if age < 172800 else
            f"{int(age // 86400)}d ago")
    return (f"{mst['count']} from Anthropic across {mst['families']} families  "
            f"{_c.C_DIM}(checked {when}){_c.C_RESET}")


def updates_menu():
    """Versions of archeus, of Claude Code and of every installed plugin, and
    updating any of them. A plugin can only be moved to whatever its marketplace
    offers, so the version prompt is offered for Claude Code alone."""
    from .ui import menu, flash, text_input, confirm
    from . import config as cfg

    from . import models as _mods

    refresh = False
    while True:
        st = status(refresh=refresh)
        sst = self_status(refresh=refresh)
        mst = _mods.status()
        mnotes = _mods.notices()
        refresh = False
        rows = plugin_rows()
        W = 62
        items = [(_c.C_NAME + 'archeus    ' + _c.C_RESET + _self_row(sst), None)]
        if sst['mode']:
            items.append((f"{_c.C_DIM}  installed via {sst['mode']}{_c.C_RESET}", None))
        if sst['update']:
            items.append((f"⬆  Update archeus to {sst['latest']}", '__self__'))
        items.append((f"{'─' * W}", None))
        items.append((_c.C_NAME + 'Claude Code  ' + _c.C_RESET + _row(st), None))
        if st['mode'] and st['mode'] != 'native':
            items.append((f"{_c.C_DIM}  installed via {st['mode']}{_c.C_RESET}", None))
        items += [(f"{'─' * W}", None), ('↻  Check for new releases now', '__check__')]
        if st['installed'] and not st['current'] and st['target']:
            items.append((f"⬆  Update to {st['target']} (latest on {st['channel']})", '__latest__'))
        items.append(('#  Install a specific version…', '__pin__'))
        for v in [v for v in st['local'] if v != st['installed']][:4]:
            items.append((f"{_c.C_DIM}↩  Roll back to {v} (already on disk){_c.C_RESET}",
                          '__pin__:' + v))
        items.append((f"{'─' * W}", None))
        for r in rows:
            if r['outdated']:
                tag = f"{_c.C_WARN}{r['available']} available{_c.C_RESET}"
            elif r['outdated'] is False:
                tag = f"{_c.C_DIM}current{_c.C_RESET}"
            else:
                tag = f"{_c.C_DIM}marketplace says nothing{_c.C_RESET}"
            items.append((f"{r['name']}  {_c.C_DIM}{r['marketplace']}"
                          f"  {r['version'] or '?'}{_c.C_RESET}  {tag}",
                          'plug:' + r['key']))
        if not rows:
            items.append((f"{_c.C_DIM}(no plugins installed){_c.C_RESET}", None))
        items += [(f"{'─' * W}", None),
                  ('↻  Refresh every marketplace', '__mkt__')]
        items.append((f"{'─' * W}", None))
        items.append((_c.C_NAME + 'Models       ' + _c.C_RESET + _models_row(mst), None))
        for note in mnotes:
            items.append((f"  {_c.C_WARN}⚠{_c.C_RESET}  {note}", None))
        items.append(('↻  Refresh the model catalogue now', '__models__'))

        sel = menu(items, 'UPDATES  /  ' + os.path.basename(cfg.config_dir))
        if not sel:
            return
        if sel == '__self__':
            ok, msg = update_self()
            flash(msg, ok=ok, secs=4)
        elif sel == '__check__':
            refresh = True
        elif sel == '__models__':
            flash('Asking Anthropic what it offers…', secs=0.4)
            r = _mods.fetch(refresh=True)
            n = len(r.get('models') or [])
            flash(r.get('error') or f'{n} models', ok=not r.get('error'), secs=3)
        elif sel == '__mkt__':
            flash('Refreshing marketplaces…', secs=0.4)
            ok, msg = update_marketplaces()
            flash(msg or ('Refreshed' if ok else 'Failed'), ok=ok, secs=2.5)
        elif sel == '__latest__':
            _run_claude_update('')
        elif sel == '__pin__':
            v = text_input('Version (exact, or stable / latest)', st['latest'] or '')
            if v:
                _run_claude_update(v.strip())
        elif sel.startswith('__pin__:'):
            _run_claude_update(sel.split(':', 1)[1])
        elif sel.startswith('plug:'):
            key = sel.split(':', 1)[1]
            if confirm(f'Update {key} to what its marketplace offers?'):
                flash(f'Updating {key}…', secs=0.4)
                ok, msg = update_plugin(key)
                flash(msg or ('Updated — restart Claude Code to apply'
                              if ok else 'Failed'), ok=ok, secs=3)


def _run_claude_update(target):
    """Claude Code replaces its own binary here, so the message is worth
    reading: a failure is usually a locked file (a session still running) and
    says so."""
    from .ui import flash
    flash('Updating Claude Code%s… this can take a minute'
          % (f' to {target}' if target else ''), secs=0.6)
    ok, msg = update_claude(target)
    flash(msg or ('Updated' if ok else 'Update failed'), ok=ok, secs=4)
