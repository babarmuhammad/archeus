"""PV-20 C4a: a Core-owned copy of the hook's Python runtime (T-034 §3, C-1013-T034).

A stage is `<ARCHEUS_HOME>/runtime/<digest>/`: fresh byte copies of a runtime
closure and the hook script, a `pythonXY._pth` Core writes, and `MANIFEST.json`
naming every other file with its size and SHA-256. The directory's name is the
SHA-256 of the manifest, so a stage is never edited: it is built in a temporary
sibling, verified, and renamed into place.

Every entry is read with `os.lstat`; a link, a junction or any other reparse
point refuses the whole stage, on the source and the destination alike. These
checks precede the acts they guard, so they narrow what a same-user writer can
swap without closing it, and they say nothing about whether the closure is
complete. Nothing here deletes anything, its own leftovers included: removal is
a separate, separately authorized card.
"""

import hashlib
import json
import os
import stat
import sys

from ..infra import paths

#: copied when present; `python.exe`, the versioned DLL and `Lib` are required
FILES = ('python.exe', 'python3.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
TREES = ('Lib', 'DLLs')
SKIP = frozenset(('site-packages', 'test', 'idlelib', 'ensurepip', 'venv', 'tkinter',
                  'turtledemo', 'lib2to3', '__pycache__', 'pyvenv.cfg'))
MANIFEST = 'MANIFEST.json'
HOOK = 'hook.py'


class StageError(OSError):
    """The stage cannot be built or trusted: the isolated spawn refuses."""


def _entry(path, is_dir=None):
    # a symlink's own mode is neither a directory nor a regular file, so the
    # plain-entry test below refuses it; a junction needs the attribute
    st = os.lstat(path)
    if getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise StageError('an alias, never followed: %s' % path)
    found = stat.S_ISDIR(st.st_mode)
    if not (found or stat.S_ISREG(st.st_mode)) or is_dir is not None and is_dir != found:
        raise StageError('not the plain entry expected: %s' % path)
    return st


def _present(path):
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _sig(st):
    return st.st_ino, st.st_dev, st.st_size, st.st_mtime_ns


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _plan(source_root, hook_path, version):
    """What the stage will hold — (relative path, source, size, sha256, lstat
    signature) per copied file — and the `._pth` bytes and the manifest bytes."""
    root = os.path.realpath(source_root)
    _entry(root, True)
    rootc = os.path.normcase(root)
    rows = []

    def take(src, rel, is_dir=None):
        st = _entry(src, is_dir)
        real = os.path.normcase(os.path.realpath(src))
        if real != rootc and not real.startswith(rootc + os.sep):
            raise StageError('outside the runtime it is copied from: %s' % src)
        if stat.S_ISDIR(st.st_mode):
            for name in sorted(os.listdir(src)):
                if name not in SKIP:
                    take(os.path.join(src, name), rel + '/' + name)
        else:
            rows.append((rel, src, st.st_size, _sha(src), _sig(st)))

    dll = 'python%d%d.dll' % version
    for name in FILES + (dll,) + TREES:
        src = os.path.join(root, name)
        if _present(src):
            take(src, name, name in TREES)
        elif name in ('python.exe', dll, 'Lib'):
            raise StageError('the runtime has no %s: %s' % (name, root))
    st = _entry(hook_path, False)
    if os.path.normcase(os.path.realpath(hook_path)) != \
            os.path.normcase(os.path.abspath(hook_path)):
        raise StageError('the hook script is reached through an alias: %s' % hook_path)
    rows.append((HOOK, hook_path, st.st_size, _sha(hook_path), _sig(st)))
    pth_name, pth = 'python%d%d._pth' % version, b'Lib\nDLLs\n'
    files = sorted([[r[0], r[2], r[3]] for r in rows] +
                   [[pth_name, len(pth), hashlib.sha256(pth).hexdigest()]])
    manifest = json.dumps({'python': '%d.%d' % version, 'source_root': root, 'files': files},
                          sort_keys=True, separators=(',', ':')).encode()
    return rows, (pth_name, pth), manifest


def _runtime():
    _entry(paths.archeus_home(), True)
    runtime = paths.runtime_dir()
    try:
        os.mkdir(runtime)
    except FileExistsError:
        pass
    _entry(runtime, True)
    return runtime


def _dest(tmp, rel):
    """Where *rel* goes in *tmp*, once every directory above it, from ARCHEUS_HOME
    down, is plain: checked again before each mkdir and each write."""
    _entry(paths.archeus_home(), True)
    _entry(paths.runtime_dir(), True)
    d = tmp
    _entry(d, True)
    parts = rel.split('/')
    for name in parts[:-1]:
        d = os.path.join(d, name)
        _entry(d, True)
    return os.path.join(d, parts[-1])


def _write(dst, chunks):
    """Writes a new name only (`xb`) and hashes what it wrote; every written
    entry is checked once more, plain and single-named, before publication."""
    h = hashlib.sha256()
    with open(dst, 'xb') as out:
        for chunk in chunks:
            h.update(chunk)
            out.write(chunk)
    return h.hexdigest()


def _tree(top):
    """The SHA-256 of *top*'s manifest, once every entry is plain, has one name
    and matches it exactly, nothing missing and nothing extra."""
    _entry(top, True)
    found = {}

    def walk(d, rel):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            st = _entry(p)
            if stat.S_ISDIR(st.st_mode):
                walk(p, rel + name + '/')
            elif st.st_nlink != 1:
                raise StageError('a second name for %s' % p)
            else:
                found[rel + name] = [st.st_size, _sha(p)]

    walk(top, '')
    if found.pop(MANIFEST, None) is None:
        raise StageError('no manifest: %s' % top)
    with open(os.path.join(top, MANIFEST), 'rb') as f:
        raw = f.read()
    try:
        listed = {rel: [size, sha] for rel, size, sha in json.loads(raw)['files']}
    except (ValueError, KeyError, TypeError) as err:
        raise StageError('an unreadable manifest in %s: %s' % (top, err)) from err
    if listed != found:
        raise StageError('the stage differs from its manifest: %s' % top)
    return hashlib.sha256(raw).hexdigest()


def verify(stage_dir):
    """*stage_dir* is a published stage — under `runtime/`, every component
    plain, its content its manifest's and its name that manifest's digest.
    Returns it; raises StageError otherwise."""
    if os.path.normcase(os.path.dirname(os.path.abspath(stage_dir))) != \
            os.path.normcase(paths.runtime_dir()):
        raise StageError('not a stage: %s' % stage_dir)
    _entry(paths.archeus_home(), True)
    _entry(paths.runtime_dir(), True)
    if _tree(stage_dir) != os.path.basename(stage_dir):
        raise StageError('the stage does not match its name: %s' % stage_dir)
    return stage_dir


def stage(source_root, hook_path, version=sys.version_info[:2]):
    """The stage for this runtime and hook: an existing one, verified, or a new
    one built from *source_root* (the real install, `sys.base_prefix`, never a
    venv). A stage that fails verification is refused, never repaired."""
    rows, (pth_name, pth), manifest = _plan(source_root, hook_path, version)
    digest = hashlib.sha256(manifest).hexdigest()
    runtime = _runtime()
    final = os.path.join(runtime, digest)
    if _present(final):
        return verify(final)
    tmp = os.path.join(runtime, '.tmp-%s-%d-%s' % (digest, os.getpid(), os.urandom(8).hex()))
    os.mkdir(tmp)
    made = set()
    for rel, src, size, sha, sig in rows:
        parts = rel.split('/')
        for i in range(1, len(parts)):
            d = '/'.join(parts[:i])
            if d not in made:
                os.mkdir(_dest(tmp, d))
                made.add(d)
        with open(src, 'rb') as f:
            got = _write(_dest(tmp, rel), iter(lambda: f.read(1 << 20), b''))
        if got != sha or _sig(_entry(src, False)) != sig:
            raise StageError('%s changed while it was staged' % src)
    _write(_dest(tmp, pth_name), [pth])
    _write(_dest(tmp, MANIFEST), [manifest])
    if _tree(tmp) != digest:
        raise StageError('the stage was not what was planned: %s' % tmp)
    try:
        os.rename(tmp, final)
    except OSError:
        # another stager published first; this call's temporary directory stays
        if not _present(final):
            raise
    return verify(final)
