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

    if not failed:
        _mark_done(moved)
    return moved, failed


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
