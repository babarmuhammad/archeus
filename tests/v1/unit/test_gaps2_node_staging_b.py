"""T-1024: the ten highest-risk still-uncovered branches of archeus/node/staging.py
lines 226-444 inclusive (the publication tail of `stage`, then the MXC/agent
verification, staging and seed bridging).

Selected branches, in the order written below (all inside 226-444; the fakes are
the seams the existing tests already use, and no OS call this slice makes is
real where a seam exists):

  1. staging.py:320-328  `_pinned_tree` refuses a pin map that is not a reviewed map
     (and a tree missing a required artifact), for the AGENT wording, before the tree
     is looked at -- reached only from `verify_agent`/`stage_agent`.
  2. staging.py:361-364  `mxc_schema_validator` refuses an unpinned policy-schema
     LOCATION, before any entry of the SDK is inspected.
  3. staging.py:367-369  `mxc_schema_validator` refuses a policy-schema path that is
     an alias, or that stands under one, before it is opened and hashed.
  4. staging.py:293-294  `_mxc_inventory` link-scans the whole tree before it hashes a
     byte of it, so a second name refuses without being read.
  5. staging.py:398      `_stage_pinned` re-scans each source immediately before it
     opens it.
  6. staging.py:400      `_stage_pinned` re-checks every directory above a destination
     file after it made them and before it writes beneath them.
  7. staging.py:288-290  `scan_grants` checks every ANCESTOR of a granted path (up the
     whole chain) before it lists that path at all.
  8. staging.py:248-249  `stage` refuses a finished temporary tree whose manifest is
     not the planned one, and never publishes it.
  9. staging.py:242-243 and 401-402  the chunked copy of an artifact that spans (or
     exactly fills) one 1 MiB read chunk, in either copy loop.
 10. staging.py:251-256  a publication that fails for a reason other than a lost race
     propagates the OS error instead of falling through to `verify`.

They are written in the numbered order above; the report ranks them by risk
(/work/QWEN-DONE-T-1024.md §4), and that order is 5, 6, 7, 1, 3, 4, 2 (fail-closed and
denial), then 9 (boundary), then 8 and 10 (error paths).

Offline and platform-neutral: no installed SDK, no committed pins edited, no
native or Windows call, no process, no network, no DLL, no sleeps. A second name
or a reparse point is presented through a faked `os.lstat` (never `os.link`, so
nothing depends on what a volume allows), the reviewed pins file is the tmp file
`tests/v1/unit/test_pv20_mxc_pins.py` writes, and every assertion is on state,
order and absence of side effects rather than on OS error text.
"""

import hashlib
import json
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.infra import paths
from archeus.node import mxc_pins, staging

CHUNK = 1 << 20
REPARSE = stat.FILE_ATTRIBUTE_REPARSE_POINT
VERSION = (3, 10)
MANIFEST = staging.MANIFEST
SCHEMA_REL = 'schema/policy.json'
SCHEMA = json.dumps({'type': 'object', 'required': ['version'],
                     'properties': {'version': {'const': '1.0.0'}}}).encode()

#: a synthetic runtime closure: never the installed one (tests/v1/conftest.py, T-040)
RUNTIME = {
    'python.exe': b'MZ fake interpreter',
    'python3.dll': b'stable abi',
    'python310.dll': b'versioned abi',
    'vcruntime140.dll': b'crt',
    'Lib/os.py': b'# os',
    'Lib/encodings/__init__.py': b'# encodings',
    'DLLs/_hash.pyd': b'fake extension',
}
SDK = {
    'package.json': json.dumps({'name': staging.MXC_PACKAGE,
                                'version': staging.MXC_VERSION}).encode(),
    staging.MXC_EXE: b'fake x64 launcher',
    'bin/x64/runtime.dll': b'fake runtime',
}
AGENT = {staging.AGENT_EXE: b'fake agent binary', 'bin/helper.dll': b'fake helper'}

_STAT_FIELDS = ('st_mode', 'st_ino', 'st_dev', 'st_size', 'st_mtime_ns', 'st_nlink',
                'st_file_attributes')


def tree(root, files):
    for rel, data in files.items():
        path = os.path.join(root, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'xb') as out:
            out.write(data)
    return root


def listing(top):
    """{relative path: bytes} of every file under *top*, read plainly."""
    found = {}
    for folder, _dirs, names in os.walk(top):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, 'rb') as f:
                found[path[len(top) + 1:].replace(os.sep, '/')] = f.read()
    return found


def lie_about(monkeypatch, victim, gate=None, **fields):
    """`os.lstat` of *victim* reports *fields*, as a same-user writer swapping an
    alias or a second name in would: from the first call at which *gate()* holds
    (always, with no gate), and latched once true. Returns the way to undo it."""
    real, want = os.lstat, os.path.normcase(os.path.abspath(victim))
    state = {'on': gate is None}

    def fake(path, *args, **kwargs):
        st = real(path, *args, **kwargs)
        if os.path.normcase(os.path.abspath(path)) != want:
            return st
        if not state['on'] and gate():
            state['on'] = True
        if not state['on']:
            return st
        return SimpleNamespace(**dict({name: getattr(st, name, 0) for name in
                                       _STAT_FIELDS}, **fields))
    monkeypatch.setattr(os, 'lstat', fake)

    def restore():
        monkeypatch.setattr(os, 'lstat', real)
    return restore


def recorder(monkeypatch, owner, name):
    """Wrap *owner.name* so every call's arguments are recorded: returns
    (calls, the real callable) so a test can restore it and keep going."""
    real, calls = getattr(owner, name), []

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)
    monkeypatch.setattr(owner, name, spy)
    return calls, real


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def sdk(tmp_path):
    root = tree(str(tmp_path / 'sdk'), SDK)
    return root, {rel: sha(data) for rel, data in SDK.items()}


@pytest.fixture
def agent(tmp_path):
    root = tree(str(tmp_path / 'agent'), AGENT)
    return root, {rel: sha(data) for rel, data in AGENT.items()}


@pytest.fixture
def reviewed(tmp_path, monkeypatch):
    """The reviewed pins file, written here and pointed at by the module, exactly as
    tests/v1/unit/test_pv20_mxc_pins.py does: a runtime caller can do neither."""
    path = tmp_path / 'pins' / 'mxc_pins.json'
    os.makedirs(os.path.dirname(str(path)))
    monkeypatch.setattr(mxc_pins, 'PINS_FILE', str(path))

    def put(doc, bump=True):
        with open(str(path), 'wb') as f:
            f.write(json.dumps(doc).encode())
        if bump:
            monkeypatch.setattr(mxc_pins, 'PINS_DIGEST', mxc_pins.digest(doc))
    return put


def pins_doc(sdk_files, agent_files=None, schema=SCHEMA_REL):
    return {'pins_version': 1,
            'mxc_sdk': {'version': staging.MXC_VERSION,
                        'files': {rel: sha(data) for rel, data in sdk_files.items()}},
            'policy_schema': {'path': schema},
            'claude_code': {'version': '2.1.0',
                            'files': {rel: sha(data) for rel,
                                      data in (agent_files or AGENT).items()}}}


# -- 1. the reviewed-pins structure guard on the agent side (staging.py:320-328)
# The guard itself is reachable and covered from `verify_mxc` - tests/v1/unit/
# test_pv20_mxc_staging.py::test_refuses_unreviewed_inventory (pins={}) and
# ::test_a_missing_launcher_pin_is_refused_whatever_the_tree_holds, plus the pin-shape
# cases in tests/v1/unit/test_pv20_mxc_staging_gaps.py - and the agent wording of the
# *other* raise at 326-327 is pinned by test_verify_agent_refuses_a_second_unpinned_file
# and ::test_agent_grants_refuse_an_unpinned_agent. What no existing test reaches is the
# argument at staging.py:352: passing `()` there instead is noticed by none of the 423
# existing tests (checked by mutation), because every existing agent test supplies a
# well-formed, complete pin map. Without it an agent folder whose pins simply do not
# mention the launcher is a verified agent folder.


def test_an_agent_folder_with_no_launcher_under_pins_that_name_nothing_is_still_refused(
        tmp_path, monkeypatch):
    root = tree(str(tmp_path / 'nothing-agent'), {})
    scanned, _ = recorder(monkeypatch, staging, '_mxc_inventory')
    with pytest.raises(staging.StageError,
                       match='missing or invalid reviewed agent pins') as caught:
        staging.verify_agent(root, pins={})
    assert type(caught.value) is staging.StageError
    assert scanned == []                       # the empty inventory was never even taken
    assert 'differ from reviewed hashes' not in str(caught.value)


@pytest.mark.parametrize('broken', [
    lambda good: {},                                              # the binary has no pin
    lambda good: {staging.AGENT_EXE: 'UNSET'},                    # a placeholder, not a pin
    lambda good: {staging.AGENT_EXE: sha(AGENT[staging.AGENT_EXE]).upper()},
    lambda good: {staging.AGENT_EXE: good[staging.AGENT_EXE], '../evil': 'a' * 64},
    lambda good: {staging.AGENT_EXE: good[staging.AGENT_EXE], 'bin/helper.dll': 'nope'},
], ids=['no-pin', 'unset', 'uppercase', 'unsafe-name', 'short-value'])
def test_agent_pins_that_are_not_a_reviewed_map_refuse_before_the_tree_is_read(
        agent, monkeypatch, broken):
    root, good = agent
    scanned, _ = recorder(monkeypatch, staging, '_mxc_inventory')
    with pytest.raises(staging.StageError) as caught:
        staging.verify_agent(root, pins=broken(good))
    assert type(caught.value) is staging.StageError
    assert 'missing or invalid reviewed agent pins' in str(caught.value)
    assert 'differ from reviewed hashes' not in str(caught.value)
    assert scanned == []                       # the tree was never even inventoried


def test_a_fresh_agent_copy_refuses_unreviewed_pins_and_makes_no_destination(agent,
                                                                            tmp_path,
                                                                            monkeypatch):
    root, good = agent
    scanned, _ = recorder(monkeypatch, staging, '_mxc_inventory')
    dest = tmp_path / 'agent-stage'
    with pytest.raises(staging.StageError, match='missing or invalid reviewed agent pins'):
        staging.stage_agent(root, str(dest), pins={})
    assert scanned == []
    assert not dest.exists()                   # refused before os.mkdir, staging.py:394


# -- 2. the policy-schema LOCATION is pinned too (staging.py:361-364)
# Closest: tests/v1/unit/test_pv20_mxc_pins.py::test_an_unset_pin_refuses_every_use,
# which runs against the committed all-UNSET file and therefore refuses at
# staging.py:360 (`mxc_sdk_pins`) and never reaches 361-364; and
# ::test_the_schema_path_must_be_recorded_and_safe, which calls `mxc_pins.schema_path`
# itself, so the StageError mapping at 364 is nowhere asserted: delete the except and
# a bare PinError escapes into the launcher instead of a refusal.


def test_an_unpinned_policy_schema_location_refuses_the_validator_before_any_read(
        tmp_path, reviewed, monkeypatch):
    files = dict(SDK, **{SCHEMA_REL: SCHEMA})          # every byte of the SDK is the
    root = tree(str(tmp_path / 'sdk'), files)          # pinned one, schema included
    reviewed(pins_doc(files, schema=mxc_pins.UNSET))
    inspected, entry = recorder(monkeypatch, staging, '_entry')
    with pytest.raises(staging.StageError) as caught:
        staging.mxc_schema_validator(root)
    assert type(caught.value) is staging.StageError
    assert 'the policy schema is not pinned' in str(caught.value)
    assert isinstance(caught.value.__cause__, mxc_pins.PinError)
    assert inspected == []                             # nothing of the SDK was inspected
    monkeypatch.setattr(staging, '_entry', entry)      # the reviewer records the path
    reviewed(pins_doc(files))
    assert staging.mxc_schema_validator(root)({'version': '1.0.0'}) is True


# -- 3. the policy-schema path is an entry to check, not only a pin to match
# (staging.py:367-369)
# Closest: tests/v1/unit/test_pv20_mxc_pins.py::test_a_schema_file_reached_through_a_link_
# is_refused, which builds a REAL symlink and `pytest.skip('symlinks unavailable')` where
# that is refused, so on a Windows runner without developer mode nothing checks this read
# at all; and it only ever aliases the schema file itself, which `_ancestors` also refuses
# through its own leaf `_entry`, so deleting staging.py:369 alone changes nothing. The
# chain above the schema (368) is the unchecked part: deleting it alone is noticed by no
# existing test (checked by mutation). This test fakes `os.lstat`, so it runs everywhere
# and both halves of the pair are its control (deleting 368 and 369 together is caught by
# the `file-alias` case).


@pytest.mark.parametrize('alias', ['folder', 'file'], ids=['junction-above', 'file-alias'])
def test_a_policy_schema_reached_through_an_alias_refuses_before_it_is_read(
        tmp_path, reviewed, monkeypatch, alias):
    root = tree(str(tmp_path / 'sdk'), dict(SDK, **{SCHEMA_REL: SCHEMA}))
    reviewed(pins_doc(dict(SDK, **{SCHEMA_REL: b'these are not the schema bytes'})))
    below = os.path.join(str(root), 'schema')
    lie_about(monkeypatch, below if alias == 'folder' else os.path.join(below,
                                                                         'policy.json'),
              st_file_attributes=REPARSE)
    with pytest.raises(staging.StageError, match='an alias') as caught:
        staging.mxc_schema_validator(root)
    # a schema that is read anyway is refused for its HASH (staging.py:372-373), so the
    # message is what proves nothing was opened; both entry checks are between the pins
    # and the read.
    assert 'differs from the reviewed hash' not in str(caught.value)
    assert 'schema' in str(caught.value)


# -- 4. the whole tree is link scanned before a byte of it is hashed
# (staging.py:293-294)
# Closest: tests/v1/unit/test_pv20_mxc_staging_gaps.py::test_non_plain_entry_in_the_sdk_
# refused, which fakes a FIFO at the inventory scan (deleting 294 does not survive it),
# and tests/v1/unit/test_pv20_mxc_staging.py::test_all_grants_refuse_nested_hardlinks,
# which calls `scan_grants` directly and so says nothing about `verify_mxc` scanning.
# Neither presents a multiply named file to the inventory - where the content still
# matches its pin, so nothing else could notice - nor that the scan happens before the
# first `_sha`: with 294 deleted, or with the nlink test at 282 switched off, every file
# is read and hashed and `verify_mxc` still returns the launcher path.


def test_a_second_name_in_the_sdk_refuses_before_any_content_is_hashed(sdk, monkeypatch):
    root, pins = sdk
    hashed, _ = recorder(monkeypatch, staging, '_sha')
    lie_about(monkeypatch, os.path.join(root, 'bin', 'x64', 'runtime.dll'), st_nlink=2)
    with pytest.raises(staging.StageError, match='second name') as caught:
        staging.verify_mxc(root, pins=pins)
    assert type(caught.value) is staging.StageError
    assert hashed == []                        # nothing was read, not even to be refused


# -- 5. each source is scanned again immediately before it is opened
# (staging.py:398)
# Closest: tests/v1/unit/test_pv20_mxc_staging.py::test_sdk_hardlink_refused plants the
# second name before the call, so the inventory scan at 294 refuses it and 398 is dark;
# ::test_source_changed_during_copy_is_not_admitted changes an artifact's bytes, not its
# names. Delete 398 and the aliased copy is admitted: its content matches its pin, so
# neither the digest check at 403 nor the reverification at 405 notices.


def test_a_second_name_appearing_after_the_inventory_refuses_the_copy_before_it_opens(
        sdk, tmp_path, monkeypatch):
    root, pins = sdk
    dest = tmp_path / 'stage'
    made = {}
    real_mkdir = os.mkdir

    def mkdir(path, *args, **kwargs):
        made[os.path.normcase(os.path.abspath(path))] = True
        return real_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(os, 'mkdir', mkdir)
    lie_about(monkeypatch, os.path.join(root, 'bin', 'x64', 'runtime.dll'),
              gate=lambda: bool(made.get(os.path.normcase(os.path.abspath(str(dest))))),
              st_nlink=2)
    written, _ = recorder(monkeypatch, staging, '_write')
    with pytest.raises(staging.StageError, match='second name'):
        staging.stage_mxc(root, str(dest), pins=pins)
    assert written == []                # the aliased source was never opened to be copied
    assert listing(str(dest)) == {}     # and nothing was half-copied beside it


# -- 6. the destination's own directories are rechecked after they are made
# (staging.py:400)
# Closest: tests/v1/unit/test_pv20_mxc_staging_gaps.py::branch 6
# (test_destination_below_an_aliased_parent_refused) fakes the parent of the whole
# destination once, which is 393; nothing fakes a directory the copy itself made a
# moment earlier. Delete 400 and the artifact is written through the junction.


def test_a_junction_swapped_for_a_directory_just_made_refuses_the_write_beneath_it(
        sdk, tmp_path, monkeypatch):
    root, pins = sdk
    dest = tmp_path / 'stage'
    made = {}
    real_mkdir = os.mkdir

    def mkdir(path, *args, **kwargs):
        made[os.path.normcase(os.path.abspath(path))] = True
        return real_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(os, 'mkdir', mkdir)
    below = os.path.join(str(dest), 'bin', 'x64')
    lie_about(monkeypatch, below,
              gate=lambda: bool(made.get(os.path.normcase(os.path.abspath(below)))),
              st_file_attributes=REPARSE)
    written, _ = recorder(monkeypatch, staging, '_write')
    with pytest.raises(staging.StageError, match='an alias') as caught:
        staging.stage_mxc(root, str(dest), pins=pins)
    assert 'x64' in str(caught.value)                        # the directory, not the file
    assert written == []
    assert os.path.isdir(below)                       # the copy made it at staging.py:399
    assert listing(str(dest)) == {}                   # nothing was written through it


# -- 7. every ancestor above a granted path, before it is listed (staging.py:288-290)
# Closest: tests/v1/unit/test_pv20_mxc_staging.py::test_reparse_directory_refused_before_walk
# fakes the granted path itself, which `_entry` at staging.py:280 also refuses, so
# deleting `_ancestors(path)` at 289 changes nothing there. A grant reached through a
# junction is a grant the launch runs from.


def test_a_grant_below_an_aliased_parent_refuses_before_the_grant_is_listed(
        tmp_path, monkeypatch):
    parent = tmp_path / 'grants'
    grant = parent / 'agent'
    os.makedirs(os.path.join(str(grant), 'nested'))
    with open(os.path.join(str(grant), 'nested', 'file.dll'), 'wb') as f:
        f.write(b'granted')
    listed, listdir = recorder(monkeypatch, os, 'listdir')
    unalias = lie_about(monkeypatch, str(parent), st_file_attributes=REPARSE)
    with pytest.raises(staging.StageError, match='an alias') as caught:
        staging.scan_grants((str(grant),))
    assert 'grants' in str(caught.value)
    assert listed == []                       # the granted tree was never walked
    monkeypatch.setattr(os, 'listdir', listdir)
    unalias()                                 # the junction is swapped back out
    staging.scan_grants((str(grant),))        # the same tree, unaliased, is granted


# -- 8. the temporary tree must be the planned one before it is renamed
# (staging.py:248-249)
# Closest: tests/v1/unit/test_pv20_runtime_stage.py::test_a_temporary_tree_that_is_not_
# what_was_planned_is_never_published plants an EXTRA file, so `_tree` itself raises at
# staging.py:200 and the digest comparison never runs. Here the tree is internally
# consistent and only disagrees with the plan: delete 248-249 and it is renamed into
# place under the planned digest, a stage whose content is not its name.


def test_a_finished_tree_whose_manifest_is_not_the_planned_one_is_never_published(
        tmp_path, archeus_home, monkeypatch):
    src, hook = _runtime_source(tmp_path, archeus_home)
    verified, _ = recorder(monkeypatch, staging, 'verify')

    def write(dst, chunks):
        data = b''.join(chunks)
        if os.path.basename(dst) == MANIFEST:
            data = json.dumps(json.loads(data), indent=1).encode()   # same listing
        with open(dst, 'xb') as out:
            out.write(data)
        return hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(staging, '_write', write)
    with pytest.raises(staging.StageError, match='not what was planned'):
        staging.stage(src, hook, version=VERSION)
    assert verified == []
    assert _published() == []
    assert len(_runtime()) == 1               # the temporary tree stands for inspection


# -- 9. the chunk boundary of a copy, in either copy loop (staging.py:242-243, 401-402)
# Closest: tests/v1/unit/test_pv20_mxc_staging.py::test_offline_copy_verified_and_fresh_
# only, whose largest artifact is a 50-byte `package.json`, and the runtime fixtures of
# tests/v1/unit/test_pv20_runtime_stage.py, whose largest file is 32 bytes: across the
# five staging test files no fixture writes a file bigger than 104 bytes, so no existing
# copy ever reaches a second chunk and the `b''` sentinel is never what stops the loop. Reducing the SDK loop at 402 to one eager read is noticed
# by exactly one existing test, and only because it drifts a source *while* the lazy
# generator is being pulled; reducing the runtime loop at 243 the same way is noticed by
# no existing test at all (both checked by mutation) and publishes a truncated stage.


@pytest.mark.parametrize('size', [CHUNK, CHUNK + 5], ids=['exact-chunk', 'chunk-plus-5'])
def test_a_runtime_file_that_spans_the_read_chunk_is_published_whole(
        tmp_path, archeus_home, size):
    payload = _payload(size)
    src, hook = _runtime_source(tmp_path, archeus_home, extra={'Lib/big.py': payload})
    planned = hashlib.sha256(_planned_manifest(src, hook)).hexdigest()
    result = staging.stage(src, hook, version=VERSION)
    assert os.path.basename(result) == planned
    with open(os.path.join(result, 'Lib', 'big.py'), 'rb') as f:
        copied = f.read()
    assert copied == payload                      # the tail past chunk one came across
    assert staging.verify(result) == result       # its manifest names its real bytes
    assert _published() == [planned]              # one stage, no temporary tree left


@pytest.mark.parametrize('size', [CHUNK, CHUNK + 5], ids=['exact-chunk', 'chunk-plus-5'])
def test_an_artifact_that_spans_the_read_chunk_is_copied_and_hashed_whole(sdk, tmp_path,
                                                                         size):
    root, pins = sdk
    payload = _payload(size)
    big = 'bin/x64/big.dll'
    with open(os.path.join(root, 'bin', 'x64', 'big.dll'), 'xb') as out:
        out.write(payload)
    pins = dict(pins, **{big: sha(payload)})
    dest = staging.stage_mxc(root, str(tmp_path / 'stage'), pins=pins)
    copy = os.path.join(dest, 'bin', 'x64', 'big.dll')
    assert os.path.getsize(copy) == size
    with open(copy, 'rb') as f:
        written = f.read()
    assert written == payload and sha(written) == pins[big]
    flipped = bytearray(written)                       # a tail that is not what was pinned
    flipped[-1] ^= 0x01
    with open(os.path.join(str(tmp_path / 'stage'), 'bin', 'x64', 'big.dll'), 'wb') as f:
        f.write(bytes(flipped))
    with pytest.raises(staging.StageError, match='differ from reviewed hashes'):
        staging.verify_mxc(dest, pins=pins)


# -- 10. a publication that fails for another reason is not a lost race
# (staging.py:251-256)
# Closest: tests/v1/unit/test_pv20_runtime_stage.py::test_a_lost_publication_race_uses_
# the_winner_and_keeps_its_own_tree and ::test_a_corrupt_winner_is_refused_and_left_as_it_
# is, both of which PUBLISH the winner first and so take only the false branch of 255.
# Delete `raise` and a real rename failure falls through to `verify(final)` of a stage
# that was never published: the caller is refused for the wrong reason, and the reason
# it is refused (an unreadable stage) names a directory that does not exist.


def test_a_publication_that_fails_for_another_reason_propagates_and_publishes_nothing(
        tmp_path, archeus_home, monkeypatch):
    src, hook = _runtime_source(tmp_path, archeus_home)
    verified, _ = recorder(monkeypatch, staging, 'verify')
    planned = hashlib.sha256(_planned_manifest(src, hook)).hexdigest()

    def refuse_rename(a, b):
        raise OSError('fixture rename failure')
    monkeypatch.setattr(os, 'rename', refuse_rename)
    with pytest.raises(OSError) as caught:
        staging.stage(src, hook, version=VERSION)
    assert not isinstance(caught.value, staging.StageError)
    assert 'fixture rename failure' in str(caught.value)
    assert verified == [] and _published() == []
    assert not os.path.exists(os.path.join(paths.runtime_dir(), planned))
    (leftover,) = _runtime()
    assert set(listing(os.path.join(paths.runtime_dir(), leftover))) == set(RUNTIME) | {
        'hook.py', 'python%d%d._pth' % VERSION, MANIFEST}


# -- fixtures and helpers for the runtime-stage cases ------------------------


def _payload(size):
    """Deterministic bytes of exactly *size*, with a tail that is not chunk-shaped."""
    payload = bytes(range(256)) * (size // 256) + b'\x7f' * (size % 256)
    assert len(payload) == size
    return payload


def _runtime_source(tmp_path, archeus_home, extra=None):
    """A synthetic runtime closure and hook, and the ARCHEUS_HOME the resolver names."""
    src = tree(str(tmp_path / 'py'), dict(RUNTIME, **(extra or {})))
    hook = str(tmp_path / 'hooks' / 'hook.py')
    os.makedirs(os.path.dirname(hook))
    with open(hook, 'xb') as out:
        out.write(b'# the hook')
    os.makedirs(str(archeus_home), exist_ok=True)
    return src, hook


def _runtime():
    try:
        return sorted(os.listdir(paths.runtime_dir()))
    except FileNotFoundError:
        return []


def _published():
    return [name for name in _runtime() if not name.startswith('.tmp-')]


def _planned_manifest(src, hook):
    """The manifest the planner would have written, so the test can name the stage."""
    return staging._plan(src, hook, VERSION)[3]
