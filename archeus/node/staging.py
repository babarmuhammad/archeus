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
from . import linkscan, mxc_pins, mxc_schema, seed

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
    try:
        st = os.lstat(path)
    except OSError as err:
        raise StageError('unreadable entry: %s' % path) from err
    if stat.S_ISLNK(st.st_mode) or \
            getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
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


def _inside(root, src):
    real, rootc = os.path.normcase(os.path.realpath(src)), os.path.normcase(root)
    if real != rootc and not real.startswith(rootc + os.sep):
        raise StageError('outside the runtime it is copied from: %s' % src)


def _hook(hook_path):
    st = _entry(hook_path, False)
    if os.path.normcase(os.path.realpath(hook_path)) != \
            os.path.normcase(os.path.abspath(hook_path)):
        raise StageError('the hook script is reached through an alias: %s' % hook_path)
    return st


def _source(root, rel, src):
    """What planning checked of *src*, checked again immediately before it is
    opened: the hook not reached through an alias; a runtime file's every
    component from the pinned root down plain, the leaf a file, inside the root."""
    if rel == HOOK:
        return _hook(src)
    d = root
    _entry(d, True)
    for name in rel.split('/')[:-1]:
        d = os.path.join(d, name)
        _entry(d, True)
    st = _entry(src, False)
    _inside(root, src)
    return st


def _plan(source_root, hook_path, version):
    """The pinned source root; what the stage will hold — (relative path, source,
    size, sha256, lstat signature) per copied file; the `._pth` and the manifest."""
    root = os.path.realpath(source_root)
    _entry(root, True)
    rows = []

    def take(src, rel, is_dir=None):
        st = _entry(src, is_dir)
        _inside(root, src)
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
    st = _hook(hook_path)
    rows.append((HOOK, hook_path, st.st_size, _sha(hook_path), _sig(st)))
    pth_name, pth = 'python%d%d._pth' % version, b'Lib\nDLLs\n'
    files = sorted([[r[0], r[2], r[3]] for r in rows] +
                   [[pth_name, len(pth), hashlib.sha256(pth).hexdigest()]])
    manifest = json.dumps({'python': '%d.%d' % version, 'source_root': root, 'files': files},
                          sort_keys=True, separators=(',', ':')).encode()
    return root, rows, (pth_name, pth), manifest


def _runtime():
    _entry(paths.archeus_home(), True)
    runtime = paths.runtime_dir()
    try:
        os.mkdir(runtime)
    except FileExistsError:
        pass
    return runtime


def _plain(*dirs):
    """ARCHEUS_HOME, runtime/ and *dirs*, each a plain directory: checked again
    before every act beneath them."""
    for d in (paths.archeus_home(), paths.runtime_dir()) + dirs:
        _entry(d, True)


def _dest(tmp, rel):
    """Where *rel* goes in *tmp*, once every directory above it is plain."""
    parts = rel.split('/')
    dirs = [tmp]
    for name in parts[:-1]:
        dirs.append(os.path.join(dirs[-1], name))
    _plain(*dirs)
    return os.path.join(dirs[-1], parts[-1])


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
    _plain()
    if _tree(stage_dir) != os.path.basename(stage_dir):
        raise StageError('the stage does not match its name: %s' % stage_dir)
    return stage_dir


def stage(source_root, hook_path, version=sys.version_info[:2]):
    """The stage for this runtime and hook: an existing one, verified, or a new
    one built from *source_root* (the real install, `sys.base_prefix`, never a
    venv). A stage that fails verification is refused, never repaired."""
    root, rows, (pth_name, pth), manifest = _plan(source_root, hook_path, version)
    digest = hashlib.sha256(manifest).hexdigest()
    runtime = _runtime()
    final = os.path.join(runtime, digest)
    if _present(final):
        return verify(final)
    tmp = os.path.join(runtime, '.tmp-%s-%d-%s' % (digest, os.getpid(), os.urandom(8).hex()))
    _plain()
    os.mkdir(tmp)
    made = set()
    for rel, src, size, sha, sig in rows:
        if _sig(_source(root, rel, src)) != sig:
            raise StageError('%s changed after it was planned' % src)
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
    _plain(tmp)
    try:
        os.rename(tmp, final)
    except OSError:
        # another stager published first; this call's temporary directory stays
        if not _present(final):
            raise
    return verify(final)


MXC_PACKAGE = '@microsoft/mxc-sdk'
MXC_VERSION = '1.0.1'
MXC_EXE = 'bin/x64/wxc-exec.exe'
AGENT_EXE = 'claude.exe'


def _ancestors(path):
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    if parent != path:
        _ancestors(parent)
    _entry(path)


def scan_grants(grants):
    """Refuse aliases and multiply named files in every granted path (F2).

    UNVERIFIED: scans are not atomic against concurrent host writers.
    """
    def walk(path):
        st = _entry(path)
        if stat.S_ISREG(st.st_mode):
            if st.st_nlink != 1:
                raise StageError('a second name for %s' % path)
        else:
            for name in os.listdir(path):
                walk(os.path.join(path, name))

    for path in grants:
        _ancestors(path)
        walk(path)


def _mxc_inventory(root):
    scan_grants((root,))
    found = {}
    for folder, _, names in os.walk(root, followlinks=False):
        for name in names:
            path = os.path.join(folder, name)
            found['/'.join(os.path.relpath(path, root).split(os.sep))] = _sha(path)
    return found


def _committed(name, **wanted):
    try:
        return mxc_pins.artifact(name, **wanted)
    except mxc_pins.PinError as err:
        raise StageError(str(err)) from err


def mxc_sdk_pins():
    """The SDK pins Core's reviewed file holds; refused while any is UNSET."""
    return _committed('mxc_sdk', version=MXC_VERSION, required=('package.json', MXC_EXE))


def agent_pins():
    """The pins of the staged agent binary; refused while any is UNSET."""
    return _committed('claude_code', required=(AGENT_EXE,))


def _pinned_tree(root, pins, required, what):
    pins = dict(pins)
    try:
        mxc_pins.check_files(pins, required)
    except mxc_pins.PinError:
        raise StageError('missing or invalid reviewed %s pins' % what) from None
    if _mxc_inventory(root) != pins:
        raise StageError('%s artifacts differ from reviewed hashes' % what)
    return pins


def verify_mxc(root, *, pins=None):
    """Verify an expanded SDK against an independently reviewed full SHA-256 map: by
    default the committed one (`mxc_pins`), which no runtime input can change.

    UNVERIFIED: the protocol supplies no artifact hashes or complete DLL inventory.
    Pins must come from Core's reviewed inventory, never from the staged package.
    """
    pins = _pinned_tree(root, mxc_sdk_pins() if pins is None else pins,
                        ('package.json', MXC_EXE), 'MXC')
    with open(os.path.join(root, 'package.json'), 'rb') as f:
        try:
            package = json.load(f)
        except ValueError as err:
            raise StageError('invalid MXC package metadata') from err
    if not isinstance(package, dict) or package.get('name') != MXC_PACKAGE             or package.get('version') != MXC_VERSION:
        raise StageError('MXC package identity differs from the pinned version')
    return os.path.join(os.fspath(root), *MXC_EXE.split('/'))


def verify_agent(root, *, pins=None):
    """The staged agent binary's folder, against its reviewed hashes; returns the exe."""
    _pinned_tree(root, agent_pins() if pins is None else pins, (AGENT_EXE,), 'agent')
    return os.path.join(os.fspath(root), *AGENT_EXE.split('/'))


def mxc_schema_validator(root):
    """The pinned-schema validator for a verified SDK: it reads the policy schema from the
    reviewed inventory, refuses unless that file is the pinned bytes, and refuses a schema
    it cannot apply in full. UNSET pins refuse here, never pass."""
    pins = mxc_sdk_pins()
    try:
        rel = mxc_pins.schema_path()
    except mxc_pins.PinError as err:
        raise StageError(str(err)) from err
    if rel not in pins:
        raise StageError('the policy schema is not in the reviewed SDK inventory')
    path = os.path.join(root, *rel.split('/'))
    _ancestors(path)
    _entry(path, False)
    with open(path, 'rb') as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != pins[rel]:
        raise StageError('the policy schema differs from the reviewed hash')
    try:
        return mxc_schema.validator(json.loads(data.decode('utf-8')))
    except (ValueError, mxc_schema.SchemaError) as err:
        raise StageError('the policy schema cannot be applied: %s' % err) from err


def agent_grants(agent_root, hook_stage, *, pins=None):
    """What the agent may run from, read-only: the verified agent binary folder and the
    verified hook runtime stage, both link scanned. Returns (exe, grants)."""
    exe = verify_agent(agent_root, pins=pins)
    verify(hook_stage)
    grants = (os.path.abspath(agent_root), os.path.abspath(hook_stage))
    scan_grants(grants)
    return exe, grants


def _stage_pinned(source_root, destination, pins, verify_tree):
    verify_tree(source_root, pins=pins)
    destination = os.path.abspath(destination)
    _ancestors(os.path.dirname(destination))
    os.mkdir(destination)
    for rel, digest in sorted(pins.items()):
        src = os.path.join(source_root, *rel.split('/'))
        dst = os.path.join(destination, *rel.split('/'))
        scan_grants((src,))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        _ancestors(os.path.dirname(dst))
        with open(src, 'rb') as f:
            got = _write(dst, iter(lambda: f.read(1 << 20), b''))
        if got != digest:
            raise StageError('artifact changed during copy: %s' % rel)
    verify_tree(destination, pins=pins)
    return destination


def stage_mxc(source_root, destination, *, pins=None):
    """Copy an offline expanded SDK into a fresh root; never install or execute it."""
    return _stage_pinned(source_root, destination,
                         dict(mxc_sdk_pins() if pins is None else pins), verify_mxc)


def stage_agent(source_root, destination, *, pins=None):
    """Copy the agent binary folder into a fresh root under its pins; never executes it."""
    return _stage_pinned(source_root, destination,
                         dict(agent_pins() if pins is None else pins), verify_agent)


def _seeded(act, *args):
    try:
        return act(*args, linkscan.multi_linked_files)
    except seed.SeedError as err:
        raise StageError(str(err)) from err
    except OSError as err:
        # the OS error text names absolute paths; the cause stays chained for the log
        raise StageError('the execution folder could not be staged') from err


def seed_execution(files, destination):
    """The execution folder: *files* (relative path -> source file) copied, never linked,
    into a fresh tree at *destination*, then hardlink and alias scanned."""
    return _seeded(seed.seed_copy, files, destination)


def import_results(source_root, files, destination):
    """The data-only way back out of an execution folder, into a fresh tree."""
    return _seeded(seed.import_back, source_root, files, destination)


def recheck_execution(destination):
    """Scans the folder again; the launcher calls it immediately before it launches."""
    return _seeded(seed.recheck, destination)
