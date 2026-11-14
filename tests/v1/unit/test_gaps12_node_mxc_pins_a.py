"""T-1440: the reviewed-pin gates of `archeus/node/mxc_pins.py`, lines 40-90 (`check_files`,
`_shaped`, `load`, `artifact`, `schema_path`).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. mxc_pins.py:43-48  check_files refuses a non-dict map, a missing required name, an unsafe name and a
                       non-string value, each with 'missing or invalid reviewed pins'
 2. mxc_pins.py:45-47  UNSET is taken only with allow_unset=True; a lowercase 64-hex value is accepted
 3. mxc_pins.py:51-55  _shaped checks type identity (True is not an int, 1 is not a bool) and the exact
                       dict key set at every level
 4. mxc_pins.py:58-63  load refuses an unreadable PINS_FILE and non-UTF-8 bytes with 'cannot be read'
 5. mxc_pins.py:64-65  load refuses a valid file whose digest is not PINS_DIGEST
 6. mxc_pins.py:66-67  with the digest passing, pins_version 2 or a broken shape gives 'unknown shape'
 7. mxc_pins.py:68-71  an empty files map gives 'has no pinned files'; UNSET values pass load
 8. mxc_pins.py:78-82  artifact refuses an UNSET version and a version mismatch, skips the comparison when
                       version is None, and enforces the required names
 9. mxc_pins.py:87-90  schema_path refuses an UNSET or unsafe path and returns a safe one
10. mxc_pins.py:64     the digest is over the canonical JSON of what was parsed: a one-byte change inside a
                       pinned hash is refused and no pins are returned

Probe 8 drops the copy-isolation claim from the candidate list (mxc_pins.py:82, dict copy): load() re-reads
the file on every call, so mutation of the returned dict cannot reach the next load() whether or not the
copy is made, and no test can observe it.

Closest existing tests: tests/v1/unit/test_pv20_mxc_pins.py (pinned-value cases; its refusal list already
includes artifact('mxc_sdk'), artifact('claude_code') and schema_path() against the placeholder file, which
overlaps probe 7's UNSET version and probe 9's UNSET path). The version-mismatch, required-name, shape,
empty-map and byte-tamper probes are not in it.

Seams: PINS_FILE and PINS_DIGEST are monkeypatched to a document written under tmp_path. No real pins file
is read or edited; no network, no subprocess, no user config.
"""

import json

import pytest

from archeus.node import mxc_pins

H = 'a' * 64


def _doc():
    return {'pins_version': 1,
            'mxc_sdk': {'version': '1.0', 'files': {'sdk/run.py': H}},
            'policy_schema': {'path': 'schema/policy.json'},
            'claude_code': {'version': '2.0', 'files': {'cli.js': H}}}


@pytest.fixture
def pins(tmp_path, monkeypatch):
    def install(doc, *, raw=None):
        path = tmp_path / 'mxc_pins.json'
        path.write_bytes(raw if raw is not None else json.dumps(doc).encode())
        monkeypatch.setattr(mxc_pins, 'PINS_FILE', str(path))
        monkeypatch.setattr(mxc_pins, 'PINS_DIGEST', mxc_pins.digest(doc))
    return install


@pytest.mark.parametrize('files, required', [
    ([], ()),
    ({'sdk/run.py': H}, ('missing.py',)),
    ({'../run.py': H}, ()),
    ({'sdk/run.py': 5}, ()),
])
def test_check_files_refuses_non_dict_missing_unsafe_and_non_string(files, required):
    with pytest.raises(mxc_pins.PinError, match='missing or invalid reviewed pins'):
        mxc_pins.check_files(files, required)


def test_check_files_takes_unset_only_when_allowed():
    with pytest.raises(mxc_pins.PinError, match='missing or invalid reviewed pins'):
        mxc_pins.check_files({'a.py': mxc_pins.UNSET}, ())
    mxc_pins.check_files({'a.py': mxc_pins.UNSET}, (), allow_unset=True)
    mxc_pins.check_files({'a.py': H}, ('a.py',))
    with pytest.raises(mxc_pins.PinError, match='missing or invalid reviewed pins'):
        mxc_pins.check_files({'a.py': 'A' * 64}, ())


def test_shaped_matches_type_identity_and_exact_keys():
    assert mxc_pins._shaped(1, int)
    assert not mxc_pins._shaped(True, int)
    assert not mxc_pins._shaped(1, bool)
    assert not mxc_pins._shaped({'a': '1', 'b': '2'}, {'a': str})
    assert not mxc_pins._shaped({}, {'a': str})
    assert mxc_pins._shaped({'v': {'x': 1}}, {'v': {'x': int}})
    assert not mxc_pins._shaped({'v': {'x': True}}, {'v': {'x': int}})


def test_load_refuses_an_unreadable_file_and_non_utf8_bytes(pins, tmp_path, monkeypatch):
    monkeypatch.setattr(mxc_pins, 'PINS_FILE', str(tmp_path / 'absent.json'))
    with pytest.raises(mxc_pins.PinError, match='cannot be read'):
        mxc_pins.load()
    pins(_doc(), raw=b'\xff\xfe{"pins_version": 1}')
    with pytest.raises(mxc_pins.PinError, match='cannot be read'):
        mxc_pins.load()


def test_load_refuses_a_valid_file_that_is_not_the_reviewed_one(pins, monkeypatch):
    pins(_doc())
    monkeypatch.setattr(mxc_pins, 'PINS_DIGEST', 'b' * 64)
    with pytest.raises(mxc_pins.PinError, match='not the reviewed one'):
        mxc_pins.load()


@pytest.mark.parametrize('edit', [
    lambda d: d.update(pins_version=2),
    lambda d: d.pop('policy_schema'),
])
def test_load_gives_unknown_shape_once_the_digest_passes(pins, edit):
    doc = _doc()
    edit(doc)
    pins(doc)
    with pytest.raises(mxc_pins.PinError, match='unknown shape'):
        mxc_pins.load()


def test_load_refuses_empty_files_and_accepts_unset_values(pins):
    doc = _doc()
    doc['mxc_sdk']['files'] = {}
    pins(doc)
    with pytest.raises(mxc_pins.PinError, match='mxc_sdk has no pinned files'):
        mxc_pins.load()
    doc = _doc()
    doc['claude_code']['files'] = {'cli.js': mxc_pins.UNSET}
    pins(doc)
    assert mxc_pins.load()['claude_code']['files'] == {'cli.js': mxc_pins.UNSET}


def test_artifact_checks_version_and_required_names(pins):
    doc = _doc()
    doc['mxc_sdk']['version'] = mxc_pins.UNSET
    pins(doc)
    with pytest.raises(mxc_pins.PinError, match='mxc_sdk is not pinned at the version'):
        mxc_pins.artifact('mxc_sdk')
    pins(_doc())
    with pytest.raises(mxc_pins.PinError, match='not pinned at the version'):
        mxc_pins.artifact('mxc_sdk', version='9.9')
    assert mxc_pins.artifact('mxc_sdk', version='1.0') == {'sdk/run.py': H}
    assert mxc_pins.artifact('mxc_sdk') == {'sdk/run.py': H}
    with pytest.raises(mxc_pins.PinError, match='missing or invalid reviewed pins'):
        mxc_pins.artifact('mxc_sdk', required=('missing.py',))


@pytest.mark.parametrize('path', [mxc_pins.UNSET, '../policy.json', '/etc/policy.json'])
def test_schema_path_refuses_unpinned_and_unsafe_paths(pins, path):
    doc = _doc()
    doc['policy_schema']['path'] = path
    pins(doc)
    with pytest.raises(mxc_pins.PinError, match='the policy schema is not pinned'):
        mxc_pins.schema_path()


def test_schema_path_returns_a_safe_path(pins):
    pins(_doc())
    assert mxc_pins.schema_path() == 'schema/policy.json'


def test_digest_gate_refuses_a_one_byte_change_inside_a_pinned_hash(pins, tmp_path):
    pins(_doc())
    path = tmp_path / 'mxc_pins.json'
    raw = path.read_bytes()
    tampered = raw.replace(b'"' + H.encode(), b'"b' + H[1:].encode(), 1)
    assert len(tampered) == len(raw) and tampered != raw
    path.write_bytes(tampered)
    with pytest.raises(mxc_pins.PinError, match='not the reviewed one'):
        mxc_pins.load()
