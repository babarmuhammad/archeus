"""Where Claude Code keeps a project's state on disk.

`os.path.join(cfgdir, 'projects', enc)` was written out by hand in fourteen
places across ten modules, and about forty HTTP endpoints reached it through
`gui_api._folder`, which joined a request-supplied `enc` with no normalisation
at all. `enc` is produced by `paths.encode_component`, which maps every
non-alphanumeric character to '-', so a separator or a dot in it means the
value did not come from the encoder — it came from the wire.
"""

import os

from . import config as _c
from . import harnesses as _harnesses

__all__ = ['projects_root', 'project_folder', 'session_file', 'transcript_path',
           'all_projects', 'under_temp', 'is_encoded',
           'workdir', 'workfile', 'WORKDIR']

#: what archeus writes into a project it does not own. Defined in config
#: because `config._ensure_dir` needs it and config may not import store, but
#: re-exported here because this is the module every path caller already has.
WORKDIR = _c.WORKDIR


def workdir(project_path):
    """`<project>/.archeus`, CREATED, and marked never-commit.

    Everything archeus parks in someone else's repository goes here, and some
    of it is sensitive: `bash-log.txt` is every Bash command Claude Code ran in
    that project (`export TOKEN=…`, `curl -H "Authorization: …"`), and
    `injected-context.md` is an entire transcript. archeus's own repo has the
    directory in `.gitignore`; nobody else's does, so the file landed in users'
    working trees looking like something to commit.

    A `.gitignore` holding `*` ignores the directory's contents including itself,
    which is the whole fix and costs one write the first time.
    """
    d = os.path.join(project_path, WORKDIR)
    _c._ensure_dir(d)     # one implementation of the marker, see config
    return d


def workfile(project_path, *parts):
    """`<project>/.archeus/<parts…>` as a PURE join — nothing is created.

    Separate from workdir() because most callers are readers: `conventions`
    scans other people's projects for a memory graph, the recall hook looks for
    one, the GUI asks whether one exists. Creating a directory as the side
    effect of a read would seed `.archeus/` into every folder merely looked
    at. Writers call workdir() first, or reach the disk through
    `config.write_atomic`, which creates the parent and marks it.
    """
    return os.path.join(project_path, WORKDIR, *parts)


def is_encoded(enc):
    """True if *enc* looks like something `paths.encode_component` produced."""
    return bool(enc) and all(c.isascii() and (c.isalnum() or c == '-') for c in enc)


def projects_root(cfgdir=None):
    return os.path.join(cfgdir or _c.config_dir, 'projects')


def project_folder(cfgdir, enc):
    """<cfgdir>/projects/<enc>. Raises ValueError if *enc* could escape.

    Validating the shape is stricter than a containment check and needs no
    filesystem call: the encoder's whole output alphabet is [A-Za-z0-9-].
    """
    if not is_encoded(enc):
        raise ValueError('not a project folder name: %r' % (enc,))
    return os.path.join(projects_root(cfgdir), enc)


def transcript_path(folder, sid):
    """The transcript of one session, from the FOLDER it lives in.

    Same answer as session_file() by a different road: that one starts from
    (cfgdir, enc) and validates both, this one is the form every reader actually
    holds, and it had been written out by hand in thirteen places. It is also the
    join that stopped being a join the moment a second harness existed — a Codex
    thread records an arbitrary rollout path rather than a file named after its
    id — which is why it is a function, and now a per-harness one.
    """
    return _harnesses.impl('transcript_path',
                           _harnesses.of_path(folder)['id'])(folder, sid)


def _transcript_claude(folder, sid):
    return os.path.join(folder, sid + '.jsonl')


def _projects_claude(home):
    """[(mtime, real path, enc)] — every project this Claude home has.

    The disk is the record here: a project exists because a session folder was
    created for it. Codex has no such directory, so its answer comes out of the
    index instead, which is the whole reason this is a descriptor entry.
    """
    from . import paths as _paths
    out = []
    root = projects_root(home)
    if not os.path.isdir(root):
        return out
    for enc in os.listdir(root):
        proj = os.path.join(root, enc)
        if not os.path.isdir(proj):
            continue
        actual = _paths.find_actual_path(enc, folder=proj)
        if actual:
            out.append((os.path.getmtime(proj), actual, enc))
    return out


def _has_project_claude(home, enc):
    return os.path.isdir(project_folder(home, enc))


def temp_root():
    """The directory whose contents are never a project, or '' to filter nothing.

    `tempfile.gettempdir()`, and deliberately NOT `config._TEMP`: that one falls
    back to the user profile when neither TEMP nor TMP is set, so on such a
    machine filtering by it would hide every project the user has.

    Two answers are refused for the same reason — a filter that cannot be wrong
    about a scratch directory can still be catastrophically wrong about a real
    one: a filesystem root, and the user profile itself.
    """
    import tempfile
    try:
        t = os.path.abspath(tempfile.gettempdir())
    except Exception:
        return ''
    if os.path.dirname(t) == t:
        return ''
    if os.path.normcase(t) == os.path.normcase(os.path.abspath(_c._USERPROFILE)):
        return ''
    return t


def under_temp(path):
    """True for a project that lives in the OS scratch directory.

    A one-shot run in a temp folder — a probe, a test, `claude -p` against a
    throwaway tree — writes the same session state a real project does, and
    every harness then reports it as a workspace. It is not one: the directory
    is gone by the next boot and nothing there is work anyone returns to.
    """
    root = temp_root()
    if not root or not path:
        return False
    p, r = os.path.normcase(os.path.abspath(path)), os.path.normcase(root)
    return p == r or p.startswith(r + os.sep)


def all_projects():
    """[(mtime, real path, enc, home)] across every harness, newest first.

    One walk. The same twenty lines stood in `gui.list_projects`,
    `gui_api._entries` and `main.run`, each producing this exact tuple — three
    places a second harness would have had to be remembered, and the sidebar
    would have shown Codex's projects while the terminal menu did not.

    It is also the one place the scratch directory is filtered, for that same
    reason: the rule is about what a project IS, not about which CLI recorded it.
    """
    out = []
    for _name, home, hid in _harnesses.instances():
        for mtime, actual, enc in _harnesses.impl('projects', hid)(home):
            if under_temp(actual):
                continue
            out.append((mtime, actual, enc, home))
    out.sort(reverse=True)
    return out


def session_file(cfgdir, enc, sid):
    """The transcript path for one session. *sid* is validated like *enc* —
    it reaches the filesystem from the wire on the same endpoints."""
    if not is_encoded(sid):
        raise ValueError('not a session id: %r' % (sid,))
    return os.path.join(project_folder(cfgdir, enc), sid + '.jsonl')
