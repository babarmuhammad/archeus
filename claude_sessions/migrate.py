"""One-time move of claudectl's on-disk state onto archeus's names.

This is the ONLY module that still knows the old name, and that is the point:
everywhere else the rename was a substitution, so nothing anywhere has to carry
a "read the old name too" fallback forever.

What it moves, and why each one is here rather than left behind:

  ~/.claude/claudectl.json          the settings file — accounts, per-project
                                    launch defaults, theme, every memory knob
  ~/.claude/claudectl-agents/       the agent library
  ~/.claude/claudectl-skills/       the skill library
  <cfgdir>/claudectl-*.json{,l}     the caches: stats, versions, models, loops,
                                    repo state, activity, the event log
  <project>/.claudectl/             the memory graph, snapshots, plan, logs
  <cfgdir>/projects/<enc>/.claudectl/   the mirror of the same
  <project>/.claude/rules/claudectl-mem-*.md      generated memory rules
  <project>/.claude/.claudectl-*.json             the agent index and manifest

Three rules shape it:

**It never deletes.** Every step is `os.replace` onto a destination that does
not exist; if one is already there the step is skipped, not overwritten. A run
that dies halfway leaves a working install of both halves rather than a hole.

**It matches the SHAPE, not a list.** `claudectl*` in a config dir is ours by
construction, and enumerating the eight cache filenames would go stale the
first time a ninth was added — the same reasoning `gui_api._managed_path_ok`
already applies to managed directories.

**It reads the OLD settings file directly** to find the other accounts.
`config.all_config_dirs()` cannot be used: it reads the *new* settings file,
which does not exist yet, so it would report one account and silently skip
every other account's caches and projects.
"""

import json
import os
import re
import time

from . import config as _c
from . import store

#: the only place both names are written down. Everywhere else the rename was a
#: substitution, so `NEW` is spelled out here rather than derived from
#: `store.WORKDIR` — a `.lstrip('.')` would be shorter and would read as though
#: the two facts were related, which they are not.
OLD = 'claudectl'
NEW = 'archeus'
OLD_WORKDIR = '.' + OLD
NEW_WORKDIR = '.' + NEW

#: settings key gating the whole thing. Declared in config._DEFAULT_SETTINGS,
#: because load_settings() parks undeclared keys under `_unknown` — they would
#: round-trip on save but read back as absent, so this would run on every start.
#:
#: It is a plain "has this been done" boolean and NOT `migrated_from`, which is
#: only set when something actually moved. Gating on the record instead would
#: mean a clean install never writes one, so it re-walks every account on every
#: launch forever.
FLAG = 'brand_migrated'

#: gate for the SECOND pass. The first one moves PATHS, and three things that
#: carry the old name are not paths: the sentinels inside a CLAUDE.md, the OS
#: scheduler's own entry names, and whatever the user typed into a shell profile.
#: It needs its own key because `brand_migrated` is already True on every install
#: this has to reach — re-opening that flag would re-run the whole move against a
#: machine that finished it months ago.
SWEEP_FLAG = 'brand_sweep'

#: `~/.claude/claudectl.json`, whatever config.settings_file now says. Derived
#: rather than hardcoded so the two cannot drift apart.
OLD_SETTINGS = os.path.join(os.path.dirname(_c.settings_file), OLD + '.json')


def _move(src, dst, moved, failed):
    """Move *src* onto *dst*, merging rather than clobbering or giving up.

    `os.replace` moves a directory as happily as a file when both are on one
    volume, which every pair here is — they are siblings. So the fast path is
    one syscall.

    The slow path exists because **the destination can already be there before
    the migration ever runs**, and not from a half-finished earlier attempt.
    Claude Code starts this package's hooks (`logbash_hook`, `memdirty_hook`)
    and its statusline in the course of ordinary work, and every one of them
    writes through `store.workdir`. Install the new version, let a hook fire
    once before opening the UI, and `<project>/.archeus/` exists holding a
    single sidecar — at which point a skip-if-present rule would strand that
    project's entire memory graph under the old name permanently. Observed on
    a real machine, not imagined.

    So: two directories merge entry by entry, and a file that already exists is
    left alone because the new one is the live copy. Nothing is ever deleted or
    overwritten; the old tree is simply emptied where it can be, and whatever
    collided stays put under the old name for a human to look at.
    """
    if not os.path.exists(src):
        return
    if not os.path.exists(dst):
        try:
            os.replace(src, dst)
            moved.append((src, dst))
        except OSError as e:
            failed.append((src, str(e)))
        return
    if os.path.isdir(src) and os.path.isdir(dst):
        _merge(src, dst, moved, failed)


def _merge(src, dst, moved, failed):
    """Recursive per-entry move of *src* into an existing *dst*."""
    try:
        names = os.listdir(src)
    except OSError as e:
        failed.append((src, str(e)))
        return
    for name in names:
        _move(os.path.join(src, name), os.path.join(dst, name), moved, failed)
    try:
        os.rmdir(src)          # only when everything moved out; never forced
    except OSError:
        pass


def _rename_prefixed(directory, old_prefix, new_prefix, moved, failed):
    """Every entry in *directory* whose name starts with *old_prefix*."""
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if name.startswith(old_prefix):
            _move(os.path.join(directory, name),
                  os.path.join(directory, new_prefix + name[len(old_prefix):]),
                  moved, failed)


def _migrate_config_dir(cfgdir, moved, failed):
    """The settings file, the two libraries and every cache in one account."""
    _rename_prefixed(cfgdir, OLD, NEW, moved, failed)


def _migrate_project(base, moved, failed):
    """One project root — either a real working directory or its mirror under
    `<cfgdir>/projects/<enc>`. Both carry the same layout."""
    _move(os.path.join(base, OLD_WORKDIR), os.path.join(base, NEW_WORKDIR),
          moved, failed)
    dot_claude = os.path.join(base, '.claude')
    # `.claude/.claudectl-agents.json`, `.claude/.claudectl-managed.json`
    _rename_prefixed(dot_claude, OLD_WORKDIR, NEW_WORKDIR, moved, failed)
    # `.claude/rules/claudectl-mem-<unit>.md`
    _rename_prefixed(os.path.join(dot_claude, 'rules'), OLD + '-', NEW + '-',
                     moved, failed)


#: any .py path inside a hook or statusLine command, quoted or bare
_PY_ARG = re.compile(r'"([^"]+\.py)"|(\S+\.py)')


def _repoint(cmd, pkg_dir):
    """Re-point a command at THIS installation, or return it unchanged.

    Hooks and the statusline record an absolute path to a script inside the
    package — never the CLI name — which is why the rename itself did not touch
    them, and why a pip upgrade in place needs nothing done here.

    Installing into a DIFFERENT environment is the case that breaks, and pipx
    does exactly that: `pipx install archeus` builds a new venv, so every
    recorded path still points into claudectl's, and `pipx uninstall claudectl`
    then deletes it. Nothing notices. `hooks._cmd_keys` compares whole command
    strings, so an old-path hook is simply unrecognised and sits there orphaned;
    `statusline.is_installed` only tests that the command CONTAINS the package
    name, so a dead statusline still reports itself as installed and prints
    nothing at all, on every turn, forever.

    Identity is the script FILENAME — the same rule `hooks.install_memory_hook`
    already uses to repair a stale path. Only a path that is BOTH dead and one
    of ours is rewritten; anything the user wrote by hand is left alone.
    """
    out = cmd
    for m in _PY_ARG.finditer(cmd):
        raw = m.group(1) or m.group(2)
        if os.path.isfile(raw):
            continue                       # still resolves — not ours to touch
        ours = os.path.join(pkg_dir, os.path.basename(raw))
        if os.path.isfile(ours):
            out = out.replace(raw, ours)
    if out == cmd:
        return cmd
    # The interpreter moved with the package, so rebuild that half too — a
    # command that runs the OLD venv's python against the NEW venv's script
    # works only until `pipx uninstall claudectl` removes it. `hooks._PYEXE` is
    # already the "strip the interpreter, keep the rest" rule, so the arguments
    # a template appended (`--denied`) survive.
    import sys
    from . import hooks
    tail = hooks._PYEXE.sub('', out.strip())
    return f'"{sys.executable}" {tail}' if tail != out.strip() else out


def repair_commands(cfgdirs=None, moved=None, failed=None):
    """Fix hook and statusLine commands whose script path no longer exists.

    **This runs on every start, not once**, and that is the whole point of it.
    `_repoint` only rewrites a path that is DEAD, and the single run the first
    version got happened at the one moment when the old paths still resolve: you
    install into the new environment, archeus starts, the migration finds nothing
    to repair and closes its gate — and only THEN do you remove the old one.

        pipx install archeus      # both venvs exist, nothing is dead, flag set
        pipx uninstall claudectl  # every recorded path dies, and nothing is left
                                  # that would ever look at them again

    The same hole swallows a checkout that is moved, renamed or re-cloned after
    the flag was written, and anyone who never had the old name at all. Running
    it unconditionally costs one settings read per account and one `isfile` per
    `.py` argument, on a path that already loads the TUI.

    **It walks Claude accounts only, and that is a measurement rather than an
    oversight.** A path dies here because archeus WROTE it into a config file;
    Codex keeps its hooks in `<CODEX_HOME>/hooks.json` behind a trust hash and
    pi has none at all, and archeus writes to neither — both declare
    `hooks: (False, …)`, so there is nothing of ours in either file to go
    stale. The day one of them gains `hooks: True`, this has to learn that
    file's reader, and
    `test_the_repair_covers_every_harness_archeus_writes_hooks_for` fails until
    it does. Extend this; do not write a second repair.
    """
    from . import hooks
    if cfgdirs is None:
        cfgdirs = [d for _name, d in _c.all_config_dirs()]
    if moved is None:
        moved = []
    if failed is None:
        failed = []
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    for cfgdir in cfgdirs:
        try:
            s = hooks._load(cfgdir)
        except Exception as e:
            failed.append((cfgdir, str(e)))
            continue
        changed = False
        for _event, entries in (s.get('hooks') or {}).items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                for h in (entry.get('hooks') or []):
                    if not isinstance(h, dict):
                        continue
                    fixed = _repoint(str(h.get('command', '')), pkg_dir)
                    if fixed != h.get('command'):
                        h['command'] = fixed
                        changed = True
                        moved.append((cfgdir, 'hook -> ' + fixed))
        sl = s.get('statusLine')
        if isinstance(sl, dict):
            # NOT `_repoint`: it rebuilds the interpreter half as
            # `sys.executable`, which is python.exe — and this command runs on
            # every conversation turn, so on Windows that is a console window
            # flashing up each time. `statusline._command()` is the same script
            # path with `_interpreter()`'s pythonw preference, which is why it
            # exists.
            cur = str(sl.get('command', ''))
            if _repoint(cur, pkg_dir) != cur:
                from . import statusline
                sl['command'] = statusline._command()
                changed = True
                moved.append((cfgdir, 'statusLine -> ' + sl['command']))
        if changed:
            try:
                hooks._save(s, cfgdir)
            except Exception as e:
                failed.append((cfgdir, str(e)))
    return moved, failed


def _old_config_dirs():
    """[dir] for every account named by the OLD settings file, default first."""
    default = os.path.dirname(_c.settings_file)
    out, seen = [], set()
    accounts = []
    try:
        with open(OLD_SETTINGS, encoding='utf-8') as f:
            accounts = (json.load(f) or {}).get('accounts') or []
    except (OSError, ValueError):
        pass
    cands = [default]
    for a in accounts:
        if isinstance(a, dict) and a.get('dir'):
            cands.append(os.path.expanduser(os.path.expandvars(a['dir'])))
    for d in cands:
        key = os.path.normcase(os.path.abspath(d))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def pending():
    """True until a run has completed without a failure. One settings read.

    Deliberately NOT "does anything old still exist": the settings file is the
    first thing users lose sight of and one of the last things moved, so a run
    that got most of the way through would answer "nothing left to do" while a
    project's memory graph sat under the old name forever. That exact hole was
    caught by `test_a_failure_does_not_write_the_done_flag`.

    The cost of a flag-only gate is that a brand-new install runs `run()` once
    for nothing; `_has_old_artifacts` keeps that to one listdir per account.
    """
    return not _c.load_settings().get(FLAG)


def _has_old_artifacts(cfgdirs):
    """Did claudectl ever run on this machine? One listdir per account.

    Asking the config dirs is the whole question: claudectl writes its settings
    file on first launch, before it can have written any project state, so a
    `<project>/.claudectl` cannot exist without a `claudectl*` entry here.
    """
    for d in cfgdirs:
        try:
            if any(n.startswith(OLD) for n in os.listdir(d)):
                return True
        except OSError:
            continue
    return False


def run():
    """Do the move. Returns (moved, failed) as lists of tuples.

    The flag is written only on a clean run, so a project whose directory was
    locked (an editor holding a file open, a sync client) is picked up on the
    next start rather than left behind for good.
    """
    from . import paths
    moved, failed = [], []
    cfgdirs = _old_config_dirs()

    if not _has_old_artifacts(cfgdirs):
        _mark_done(moved)
        return moved, failed

    for cfgdir in cfgdirs:
        for enc in _encoded_folders(cfgdir):
            folder = store.project_folder(cfgdir, enc)
            _migrate_project(folder, moved, failed)
            try:
                real = paths.find_actual_path(enc, folder=folder)
            except Exception:
                real = None
            if real and os.path.isdir(real):
                _migrate_project(real, moved, failed)

    # the config dirs LAST: the settings file is what `pending()` and
    # `_old_config_dirs()` both read, so moving it before the projects would
    # mean a crash in the middle left nothing pointing at the rest.
    for cfgdir in cfgdirs:
        _migrate_config_dir(cfgdir, moved, failed)

    _rederive_config_paths()
    # its own `fixed` list, NOT `moved`: `_mark_done` reads that one to decide
    # whether to stamp `migrated_from`, and a routine hook repair years later
    # must not record a clean install as having come from the old name.
    _rfixed, _rfailed = repair_commands(cfgdirs)
    failed.extend(_rfailed)

    if not failed:
        _mark_done(moved)
    return moved, failed


# ── the second pass: the state that is not a path ─────────────
# `run()` renames things. These three carry the old name INSIDE them, so a
# rename could never have reached them and nothing noticed for a whole release.

#: the blocks a renderer owns end to end (`claude_md.write_memory_block`,
#: `agents._write_routing_block`, `loops.write_journal_block`,
#: `conventions`), so an orphaned one is stale generated text and nothing else.
#: KEEP is deliberately absent: it is a REPEATABLE fence around the user's own
#: prose, and it is renamed, never removed.
_UNIQUE_BLOCKS = ('MEMORY', 'AGENTS', 'LOOP', 'CONVENTIONS')

#: KEEP is the user's own fence and may legitimately appear many times, so it is
#: renamed with the rest and never removed.
_SENTINEL_BLOCKS = _UNIQUE_BLOCKS + ('KEEP',)

_OLD_TAG = '<!-- %s:' % OLD.upper()
_NEW_TAG = '<!-- %s:' % NEW.upper()

#: `loops.TASK_PREFIX` under the old name. A scheduler entry is a NAME, so no
#: path move could have reached it. Asserted against `loops.TASK_PREFIX` in the
#: tests, or a second blind substitution would collapse the pair.
OLD_TASK_PREFIX = OLD + '-loop-'


def sweep_pending():
    """True until the second pass has completed without a failure."""
    return not _c.load_settings().get(SWEEP_FLAG)


def sweep(cfgdirs=None):
    """Rewrite the sentinels and re-register the scheduler entries.

    Returns (fixed, failed). Gated separately from `run()`, because everyone
    this has to reach has already run `run()` to completion.

    **It reads `all_config_dirs()`, which `run()` is forbidden to use** — the
    rule there is inverted, not relaxed: `run()` cannot use it because the file
    it reads has not been moved yet, and by the time this runs that file is the
    only place the account list exists. Using `_old_config_dirs()` here would
    silently sweep the default account and skip every other one.

    Accepted ceiling: `diffview.restore` can put a pre-rename snapshot back
    after the gate has closed. A permanent guard for that is not worth carrying.
    """
    from . import paths
    fixed, failed = [], []
    # the gate lives HERE and not at the call site, so "has this run?" has one
    # owner and a second caller cannot forget to ask
    if not sweep_pending():
        return fixed, failed
    if _c.load_settings().get('migrated_from') != OLD:
        _mark_sweep_done(failed)        # never had the old name — nothing to walk
        return fixed, failed
    if cfgdirs is None:
        cfgdirs = [d for _name, d in _c.all_config_dirs()]
    for cfgdir in cfgdirs:
        # the account's own CLAUDE.md — the CONVENTIONS block lives there, and
        # `upsert_block` joins 'CLAUDE.md' onto whatever it is given, so the
        # global file needs no special case
        _sweep_claude_md(cfgdir, fixed, failed)
        _sweep_loops(cfgdir, fixed, failed)
        for enc in _encoded_folders(cfgdir):
            folder = store.project_folder(cfgdir, enc)
            try:
                real = paths.find_actual_path(enc, folder=folder)
            except Exception:
                real = None
            # only the real working directory: nothing writes a CLAUDE.md into
            # the `projects/<enc>` mirror, which holds snapshots and diff records
            # — history, and history keeps its own bytes
            if real and os.path.isdir(real):
                _sweep_claude_md(real, fixed, failed)
    _mark_sweep_done(failed)
    return fixed, failed


def _mark_sweep_done(failed):
    """Close the second gate, unless a WRITE failed.

    Narrower than `run()`'s rule on purpose: a CLAUDE.md that cannot be read may
    not even contain an old sentinel, and treating that as a reason to retry
    would re-walk every account on every start for ever.
    """
    if failed:
        return
    s = _c.load_settings()
    s[SWEEP_FLAG] = True
    _c.save_settings(s)


def _sweep_claude_md(base, fixed, failed):
    """One CLAUDE.md: drop a block the new name already owns, rename the rest.

    `claude_md.upsert_block` needs BOTH new sentinels to replace a block, so an
    old one is invisible to it and every build appended a second block beside the
    first — measured on three of this machine's own projects. The orphan is then
    injected into every session for ever, saying whatever it said the day the
    rename landed.

    The order is load-bearing. Delete the superseded blocks FIRST, while their
    sentinels still carry the old name, and only then rename what is left; doing
    it the other way round produces two blocks with identical sentinels and no
    way to tell which one the renderer will find.

    KEEP is renamed and never removed — `claude_md._KEEP_RE` is built from the
    new sentinels only, so until this runs a user's protected prose is no longer
    excised before the compression prompt and the model may rewrite it.

    A HALF pair — a start with no end — is left exactly as it is. Renaming one
    would manufacture the state above: `upsert_block` indexes the FIRST
    occurrence, so a stray new-name start sentinel silently captures every later
    write and orphans the real block.
    """
    from . import claude_md
    path = os.path.join(base, 'CLAUDE.md')
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            text = f.read()
    except OSError as e:
        _c.log.warning('sweep could not read %s: %s', path, e)
        return          # a read failure is not a reason to retry for ever
    if _OLD_TAG not in text:
        return
    for name in _UNIQUE_BLOCKS:
        start, end = _OLD_TAG + name + ':START -->', _OLD_TAG + name + ':END -->'
        if (text.count(start) == text.count(end) > 0
                and (_NEW_TAG + name + ':START -->') in text):
            ok, _before, text = claude_md.upsert_block(base, start, end, '')
            if not ok:
                failed.append((path, 'could not drop the superseded %s block' % name))
                return
            fixed.append((path, 'dropped the superseded %s block' % name))
    new = text
    for name in _SENTINEL_BLOCKS:
        start, end = _OLD_TAG + name + ':START -->', _OLD_TAG + name + ':END -->'
        if new.count(start) == new.count(end) > 0:
            new = (new.replace(start, _NEW_TAG + name + ':START -->')
                      .replace(end, _NEW_TAG + name + ':END -->'))
    if new == text:
        return
    if _c.write_atomic(path, new):
        fixed.append((path, 'sentinels renamed'))
    else:
        failed.append((path, 'could not rewrite the sentinels'))


def _sweep_loops(cfgdir, fixed, failed):
    """Drop the scheduler entry registered under the old name, re-create it.

    A scheduler entry is a NAME, not a path, so no move could reach it: the
    registry is `archeus-loops.json` now while the task is still
    `claudectl-loop-<id>`. `loops.is_scheduled` therefore reports the loop as
    unscheduled while the old entry goes on firing — and the moment the user
    schedules it again from the UI there are two of them.

    Delete-and-recreate rather than rename, because the old entry's command line
    also names the OLD environment's interpreter, which is the one `pipx
    uninstall claudectl` deleted. A rename would leave a correctly named task
    that fails silently for ever; `loops.schedule` rebuilds the argv.

    The POSIX half cannot go through `loops._cron_write`: it filters on the NEW
    tag, so the old line survives every rewrite it ever does.
    """
    from . import loops, proc
    rows = [r for r in loops._load(cfgdir) if r.get('id')]
    if not rows:
        return
    stale = []
    if proc.WINDOWS:
        for r in rows:
            tn = OLD_TASK_PREFIX + r['id']
            q = proc.run(['schtasks', '/query', '/tn', tn], timeout=30)
            if q is None or q.returncode:
                continue
            proc.run(['schtasks', '/delete', '/tn', tn, '/f'], timeout=30)
            stale.append(r)
    else:
        cur = proc.run(['crontab', '-l'], timeout=15)
        lines = ((cur.stdout or '').splitlines()
                 if cur is not None and not cur.returncode else [])
        keep = [ln for ln in lines if OLD_TASK_PREFIX not in ln]
        if len(keep) == len(lines):
            return
        w = proc.run(['crontab', '-'], stdin='\n'.join(keep).strip() + '\n', timeout=15)
        if w is None or w.returncode:
            failed.append((cfgdir, 'could not rewrite the crontab'))
            return
        stale = [r for r in rows
                 if any(OLD_TASK_PREFIX + r['id'] in ln for ln in lines)]
    for r in stale:
        ok, msg = loops.schedule(r['id'], r.get('interval') or '', cfgdir)
        (fixed if ok else failed).append((cfgdir, 'loop %s: %s' % (r['id'], msg)))


def stale_env_warning():
    """`CLAUDECTL_*` is read nowhere and fails silently — say so, fix nothing.

    A read-the-old-name-too fallback is exactly what this module exists to stop
    the rest of the codebase from carrying, and the value lives in a shell
    profile or a CI config that archeus has no business editing either way.
    """
    names = sorted(k for k in os.environ if k.startswith(OLD.upper() + '_'))
    if not names:
        return ''
    pairs = ', '.join('%s is now %s' % (n, NEW.upper() + n[len(OLD):]) for n in names)
    return ('set but no longer read: ' + pairs
            + '. Rename them in your shell profile, or they do nothing.')


def stale_plugin_warning(cfgdir=None):
    """The Claude Code plugin id moved with the name, and nothing aliases it.

    Both the marketplace and the plugin are called archeus now, so an install
    made as `claudectl@claudectl` still resolves to a directory on disk and goes
    on shadowing the new one. The repair is two commands typed into Claude Code;
    the plugin caches are only ever written through the `claude` CLI (their
    format has already changed once), so this reads and reports.
    """
    from . import plugins
    try:
        stale = [p['key'] for p in plugins.installed(cfgdir)
                 if OLD in (p['name'] + p['marketplace'])]
        stale += [m['name'] for m in plugins.known_marketplaces(cfgdir)
                  if m['name'] == OLD and not stale]
    except Exception:
        return ''
    if not stale:
        return ''
    return ('the Claude Code plugin is still installed under the old name (%s). '
            'In Claude Code run:  /plugin uninstall %s@%s  then  '
            '/plugin marketplace add babarmuhammad/%s  and  /plugin install %s@%s'
            % (', '.join(sorted(set(stale))), OLD, OLD, NEW, NEW, NEW))


def coinstalled_warning():
    """The one thing a user can do that breaks this install, worded as the fix.

    Both distributions ship the same import package, `claude_sessions`. So
    `pip install archeus` over an existing claudectl silently OVERWRITES those
    files — both distributions then claim to own them — and the obvious next
    step, `pip uninstall claudectl`, deletes them. archeus is left listed as
    installed and unable to import itself:

        ModuleNotFoundError: No module named 'claude_sessions.cli'

    Verified end to end in a clean venv, in both orders. There is no packaging
    metadata that expresses "conflicts with", so the only defence is saying so
    before the user reaches for the uninstall — which is the order everybody
    does it in.

    Returns '' when there is nothing to warn about, which is every case except
    the two packages sharing one environment.
    """
    try:
        import importlib.metadata as md
        md.distribution(OLD)
    except Exception:
        return ''                      # not installed here — nothing to say
    return (f'{OLD} is still installed alongside archeus and they share files. '
            f'Do NOT `pip uninstall {OLD}` on its own — it deletes archeus too. '
            f'Run:  pip uninstall {OLD} && pip install --force-reinstall archeus')


def _mark_done(moved):
    """Close the gate. `migrated_from` is the RECORD and is written only when
    something actually moved — it is what tells a support question apart: an
    install that came from claudectl, versus one that never had it."""
    s = _c.load_settings()
    s[FLAG] = True
    if moved:
        s['migrated_from'] = OLD
        s['migrated_at'] = int(time.time())
    _c.save_settings(s)


def _encoded_folders(cfgdir):
    root = store.projects_root(cfgdir)
    try:
        names = os.listdir(root)
    except OSError:
        return []
    return [n for n in names
            if store.is_encoded(n) and os.path.isdir(os.path.join(root, n))]


def _rederive_config_paths():
    """config_dir and friends are computed at IMPORT, from a settings file that
    did not exist yet — so a user with a `claude_config_dir` override would have
    spent the rest of this process pointed at the default account. The four
    values below are exactly what config.py computes at its own import; this
    recomputes them now that the settings are readable.
    """
    _c.config_dir = _c.get_config_dir()
    _c.projects_dir = store.projects_root(_c.config_dir)
    _c.last_session_file = os.path.join(_c.projects_dir, 'last-session.json')
    _c.global_claude_md = os.path.join(_c.config_dir, 'CLAUDE.md')
