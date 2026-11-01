"""PV-20 B0: the committed reviewed pins, their digest rule and the pinned-schema validator.

Synthetic trees only: nothing here reads an installed SDK, runs a process or calls a native
API. The committed file holds UNSET placeholders (no real hash is knowable offline), so the
first group pins that every use of them refuses; the rest drives the same code from a pins
file the test writes and points the module at, which is the one thing a test may do that a
runtime caller cannot (there is no path argument, setting or environment variable)."""

import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from archeus.node import mxc_pins, mxc_schema, staging
from archeus.node.staging import StageError

SDK_FILES = {
    'package.json': json.dumps({'name': staging.MXC_PACKAGE,
                                'version': staging.MXC_VERSION}).encode(),
    staging.MXC_EXE: b'fake x64 launcher',
    'schema/policy.json': json.dumps({'type': 'object', 'required': ['version'],
                                      'properties': {'version': {'const': '1.0.0'}},
                                      'additionalProperties': True}).encode(),
}
AGENT_FILES = {staging.AGENT_EXE: b'fake agent binary'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def document(**changes):
    doc = {'pins_version': 1,
           'mxc_sdk': {'version': staging.MXC_VERSION,
                       'files': {rel: sha(data) for rel, data in SDK_FILES.items()}},
           'policy_schema': {'path': 'schema/policy.json'},
           'claude_code': {'version': '2.1.0',
                           'files': {rel: sha(data) for rel, data in AGENT_FILES.items()}}}
    doc.update(changes)
    return doc


@pytest.fixture
def reviewed(tmp_path, monkeypatch):
    """Points the module at a pins file written here, with its digest bumped as a reviewer
    would: `put(doc)` writes another and bumps again, `put(doc, bump=False)` edits it only."""
    path = tmp_path / 'pins' / 'mxc_pins.json'
    path.parent.mkdir()
    monkeypatch.setattr(mxc_pins, 'PINS_FILE', str(path))

    def put(doc, bump=True):
        path.write_text(json.dumps(doc), encoding='utf-8')
        if bump:
            monkeypatch.setattr(mxc_pins, 'PINS_DIGEST', mxc_pins.digest(doc))
    put(document())
    return SimpleNamespace(put=put, path=path)


def tree(root, files):
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


# ── the committed file ──


def test_the_committed_file_is_the_reviewed_one_and_still_all_placeholders():
    pins = mxc_pins.load()
    assert mxc_pins.digest(pins) == mxc_pins.PINS_DIGEST
    values = (list(pins['mxc_sdk']['files'].values()) + list(pins['claude_code']['files'].values())
              + [pins['policy_schema']['path'], pins['claude_code']['version']])
    assert set(values) == {mxc_pins.UNSET}, 'a pin was recorded: rewrite the UNSET refusals'


@pytest.mark.parametrize('use', [
    lambda: mxc_pins.artifact('mxc_sdk'),
    lambda: mxc_pins.artifact('claude_code'),
    lambda: mxc_pins.schema_path(),
    lambda: staging.mxc_sdk_pins(),
    lambda: staging.agent_pins(),
    lambda: staging.verify_mxc('unused'),
    lambda: staging.verify_agent('unused'),
    lambda: staging.stage_mxc('unused', 'unused'),
    lambda: staging.stage_agent('unused', 'unused'),
    lambda: staging.mxc_schema_validator('unused'),
])
def test_an_unset_pin_refuses_every_use(use):
    with pytest.raises((StageError, mxc_pins.PinError)):
        use()


# ── the file and its digest ──


def test_a_pin_changed_without_the_digest_bump_is_refused(reviewed):
    doc = document()
    doc['claude_code']['files'][staging.AGENT_EXE] = sha(b'another binary')
    reviewed.put(doc, bump=False)
    with pytest.raises(mxc_pins.PinError, match='not the reviewed one'):
        mxc_pins.load()


def test_a_pin_changed_with_the_bump_is_the_reviewed_change(reviewed):
    doc = document()
    doc['claude_code']['files'][staging.AGENT_EXE] = sha(b'another binary')
    reviewed.put(doc)
    assert mxc_pins.artifact('claude_code') == {staging.AGENT_EXE: sha(b'another binary')}


def test_the_digest_does_not_depend_on_line_endings_or_key_order(reviewed):
    reviewed.path.write_bytes(json.dumps(document(), indent=2, sort_keys=True)
                              .replace('\n', '\r\n').encode())
    assert mxc_pins.load()['pins_version'] == 1


def test_a_missing_or_unparseable_file_refuses(reviewed):
    reviewed.path.write_text('{', encoding='utf-8')
    with pytest.raises(mxc_pins.PinError, match='cannot be read'):
        mxc_pins.load()
    reviewed.path.unlink()
    with pytest.raises(mxc_pins.PinError, match='cannot be read'):
        mxc_pins.load()


def _bad_shapes():
    extra = document()
    extra['mxc_sdk']['unreviewed'] = 1
    nested = document()
    nested['policy_schema'] = {'path': 'a', 'sha256': 'b'}
    return [document(pins_version=2), document(pins_version=True), extra, nested,
            {k: v for k, v in document().items() if k != 'claude_code'},
            document(claude_code={'version': '1', 'files': {}}),
            document(claude_code={'version': 1, 'files': {'claude.exe': mxc_pins.UNSET}})]


@pytest.mark.parametrize('doc', _bad_shapes())
def test_an_unknown_shape_refuses(reviewed, doc):
    reviewed.put(doc)
    with pytest.raises(mxc_pins.PinError):
        mxc_pins.load()


def test_nothing_names_another_pins_file():
    import inspect
    for fn in (mxc_pins.load, mxc_pins.artifact, mxc_pins.schema_path):
        assert not inspect.signature(fn).parameters.keys() & {'path', 'file', 'pins_file'}
    assert 'os.environ' not in inspect.getsource(mxc_pins) and 'getenv' not in inspect.getsource(mxc_pins)


# ── what a pin may be ──


@pytest.mark.parametrize('value', [mxc_pins.UNSET, '', 'a' * 63, 'a' * 65, 'A' * 64, 'g' * 64,
                                   None, 5, ['a' * 64]])
def test_a_value_that_is_not_a_full_lowercase_hash_is_no_pin(reviewed, value):
    doc = document()
    doc['claude_code']['files'][staging.AGENT_EXE] = value
    reviewed.put(doc)
    with pytest.raises(mxc_pins.PinError):
        mxc_pins.artifact('claude_code')


@pytest.mark.parametrize('name', ['', '../x', 'a/../x', 'a//x', '/x', 'a\\x', 'C:x', './x'])
def test_a_name_that_is_not_a_safe_relative_path_is_refused(reviewed, name):
    doc = document()
    doc['claude_code']['files'][name] = sha(b'x')
    reviewed.put(doc)
    with pytest.raises(mxc_pins.PinError):
        mxc_pins.artifact('claude_code')


def test_a_required_file_without_a_pin_is_refused(reviewed):
    with pytest.raises(mxc_pins.PinError):
        mxc_pins.artifact('claude_code', required=('other.exe',))
    assert mxc_pins.artifact('claude_code', required=(staging.AGENT_EXE,))


def test_a_version_the_code_was_not_reviewed_for_is_refused(reviewed):
    assert mxc_pins.artifact('mxc_sdk', version=staging.MXC_VERSION)
    with pytest.raises(mxc_pins.PinError, match='version'):
        mxc_pins.artifact('mxc_sdk', version='9.9.9')


def test_an_unset_version_refuses_even_with_every_hash_recorded(reviewed):
    doc = document()
    doc['claude_code']['version'] = mxc_pins.UNSET
    reviewed.put(doc)
    with pytest.raises(mxc_pins.PinError, match='version'):
        mxc_pins.artifact('claude_code')


def test_the_schema_path_must_be_recorded_and_safe(reviewed):
    assert mxc_pins.schema_path() == 'schema/policy.json'
    for bad in (mxc_pins.UNSET, '../policy.json', 'a\\b'):
        reviewed.put(document(policy_schema={'path': bad}))
        with pytest.raises(mxc_pins.PinError):
            mxc_pins.schema_path()


# ── verify_mxc and the staged tree, fed from the file ──


def test_verify_mxc_takes_its_pins_from_the_reviewed_file(reviewed, tmp_path):
    root = tree(tmp_path / 'sdk', SDK_FILES)
    assert staging.verify_mxc(root) == os.path.join(str(root), *staging.MXC_EXE.split('/'))


@pytest.mark.parametrize('drift', ['hash', 'extra', 'missing'])
def test_a_drifted_sdk_is_refused_against_the_reviewed_file(reviewed, tmp_path, drift):
    root = tree(tmp_path / 'sdk', SDK_FILES)
    if drift == 'hash':
        (root / staging.MXC_EXE).write_bytes(b'tampered')
    elif drift == 'extra':
        (root / 'extra.dll').write_bytes(b'unknown')
    else:
        (root / staging.MXC_EXE).unlink()
    with pytest.raises(StageError, match='differ from reviewed hashes'):
        staging.verify_mxc(root)


def test_a_missing_launcher_pin_is_refused_whatever_the_tree_holds(reviewed, tmp_path):
    doc = document()
    del doc['mxc_sdk']['files'][staging.MXC_EXE]
    reviewed.put(doc)
    with pytest.raises(StageError, match='missing or invalid reviewed pins'):
        staging.verify_mxc(tree(tmp_path / 'sdk', SDK_FILES))


def test_a_pin_for_another_version_of_the_sdk_is_refused(reviewed, tmp_path):
    doc = document()
    doc['mxc_sdk']['version'] = '0.0.1'
    reviewed.put(doc)
    with pytest.raises(StageError, match='version'):
        staging.verify_mxc(tree(tmp_path / 'sdk', SDK_FILES))


def test_stage_mxc_copies_under_the_reviewed_pins_and_reverifies(reviewed, tmp_path):
    root = tree(tmp_path / 'sdk', SDK_FILES)
    dest = staging.stage_mxc(root, tmp_path / 'stage')
    assert staging.verify_mxc(dest)


def test_explicit_pins_still_override_for_fixtures(reviewed, tmp_path):
    root = tree(tmp_path / 'sdk', {**SDK_FILES, 'extra.dll': b'x'})
    pins = {rel: sha((root / rel).read_bytes())
            for rel in ('package.json', staging.MXC_EXE, 'schema/policy.json', 'extra.dll')}
    assert staging.verify_mxc(root, pins=pins)


# ── the staged agent and the hook runtime ──


def test_verify_agent_checks_the_binary_folder_against_its_pins(reviewed, tmp_path):
    root = tree(tmp_path / 'agent', AGENT_FILES)
    assert staging.verify_agent(root) == os.path.join(str(root), staging.AGENT_EXE)
    (root / staging.AGENT_EXE).write_bytes(b'swapped')
    with pytest.raises(StageError, match='agent artifacts differ'):
        staging.verify_agent(root)


def test_verify_agent_refuses_a_second_unpinned_file(reviewed, tmp_path):
    root = tree(tmp_path / 'agent', {**AGENT_FILES, 'node.dll': b'x'})
    with pytest.raises(StageError, match='agent artifacts differ'):
        staging.verify_agent(root)


def test_stage_agent_copies_fresh_and_refuses_an_existing_destination(reviewed, tmp_path):
    root = tree(tmp_path / 'agent', AGENT_FILES)
    dest = staging.stage_agent(root, tmp_path / 'stage')
    assert staging.verify_agent(dest)
    assert os.stat(root / staging.AGENT_EXE).st_ino != os.stat(
        os.path.join(dest, staging.AGENT_EXE)).st_ino
    with pytest.raises(FileExistsError):
        staging.stage_agent(root, tmp_path / 'stage')


def test_stage_agent_refuses_a_source_that_drifted(reviewed, tmp_path):
    root = tree(tmp_path / 'agent', AGENT_FILES)
    (root / staging.AGENT_EXE).write_bytes(b'tampered')
    with pytest.raises(StageError):
        staging.stage_agent(root, tmp_path / 'stage')
    assert not (tmp_path / 'stage').exists()


@pytest.fixture
def hook_stage(tmp_path, archeus_home):
    src = tree(tmp_path / 'py', {'python.exe': b'MZ', 'python310.dll': b'dll',
                                 'Lib/os.py': b'# os'})
    hook = tree(tmp_path / 'hooks', {'hook.py': b'# the hook'}) / 'hook.py'
    archeus_home.mkdir()
    return staging.stage(str(src), str(hook), version=(3, 10))


def test_agent_grants_are_the_verified_agent_folder_and_hook_stage(reviewed, tmp_path,
                                                                    hook_stage):
    root = tree(tmp_path / 'agent', AGENT_FILES)
    exe, grants = staging.agent_grants(root, hook_stage)
    assert exe == os.path.join(str(root), staging.AGENT_EXE)
    assert grants == (str(root), hook_stage)


def test_agent_grants_refuse_a_hook_stage_that_was_edited(reviewed, tmp_path, hook_stage):
    root = tree(tmp_path / 'agent', AGENT_FILES)
    with open(os.path.join(hook_stage, 'hook.py'), 'ab') as f:
        f.write(b'# edited')
    with pytest.raises(StageError):
        staging.agent_grants(root, hook_stage)


def test_agent_grants_refuse_a_hardlinked_agent_file(reviewed, tmp_path, hook_stage):
    root = tree(tmp_path / 'agent', AGENT_FILES)
    outside = tmp_path / 'outside.exe'
    outside.write_bytes(b'x')
    os.link(outside, root / 'alias.exe')
    with pytest.raises(StageError):
        staging.agent_grants(root, hook_stage, pins={
            staging.AGENT_EXE: sha(AGENT_FILES[staging.AGENT_EXE]), 'alias.exe': sha(b'x')})


def test_agent_grants_refuse_an_unpinned_agent(reviewed, tmp_path, hook_stage):
    root = tree(tmp_path / 'agent', {staging.AGENT_EXE: b'not the pinned binary'})
    with pytest.raises(StageError, match='agent artifacts differ'):
        staging.agent_grants(root, hook_stage)


# ── the pinned-schema validator ──


def test_the_validator_is_built_from_the_pinned_file_and_applies_it(reviewed, tmp_path):
    root = tree(tmp_path / 'sdk', SDK_FILES)
    check = staging.mxc_schema_validator(root)
    assert check({'version': '1.0.0'}) is True
    assert check({'version': '2.0.0'}) is False
    assert check({}) is False
    assert check('1.0.0') is False


def test_a_schema_that_is_not_the_pinned_bytes_is_refused(reviewed, tmp_path):
    root = tree(tmp_path / 'sdk', SDK_FILES)
    (root / 'schema' / 'policy.json').write_bytes(b'{"type": "object"}')
    with pytest.raises(StageError, match='differs from the reviewed hash'):
        staging.mxc_schema_validator(root)


def test_a_schema_outside_the_reviewed_inventory_is_refused(reviewed, tmp_path):
    reviewed.put(document(policy_schema={'path': 'schema/other.json'}))
    with pytest.raises(StageError, match='not in the reviewed SDK inventory'):
        staging.mxc_schema_validator(tree(tmp_path / 'sdk', SDK_FILES))


def test_a_pinned_schema_this_checker_cannot_apply_is_refused_not_ignored(reviewed, tmp_path):
    files = dict(SDK_FILES)
    files['schema/policy.json'] = json.dumps({'type': 'object', 'format': 'uri'}).encode()
    doc = document()
    doc['mxc_sdk']['files'] = {rel: sha(data) for rel, data in files.items()}
    reviewed.put(doc)
    with pytest.raises(StageError, match='cannot be applied'):
        staging.mxc_schema_validator(tree(tmp_path / 'sdk', files))


def test_a_pinned_schema_that_is_not_json_is_refused(reviewed, tmp_path):
    files = dict(SDK_FILES, **{'schema/policy.json': b'not json'})
    doc = document()
    doc['mxc_sdk']['files'] = {rel: sha(data) for rel, data in files.items()}
    reviewed.put(doc)
    with pytest.raises(StageError, match='cannot be applied'):
        staging.mxc_schema_validator(tree(tmp_path / 'sdk', files))


def test_a_schema_file_reached_through_a_link_is_refused(reviewed, tmp_path):
    root = tree(tmp_path / 'sdk', SDK_FILES)
    real = root / 'schema' / 'policy.json'
    moved = tmp_path / 'moved.json'
    real.replace(moved)
    try:
        os.symlink(moved, real)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks unavailable')
    with pytest.raises(StageError, match='alias'):
        staging.mxc_schema_validator(root)


# ── the checker ──

SCHEMA = {
    '$schema': 'x', 'title': 'policy', 'type': 'object', 'required': ['a'],
    'additionalProperties': False,
    'properties': {
        'a': {'type': 'integer', 'minimum': 1, 'maximum': 9},
        'b': {'type': 'array', 'items': {'type': 'string', 'pattern': '^x', 'minLength': 2,
                                         'maxLength': 4},
              'minItems': 1, 'maxItems': 2, 'uniqueItems': True},
        'c': {'enum': ['p', 'q']},
        'd': {'const': {'k': 1}},
        'e': {'$ref': '#/definitions/flag'},
        'f': {'oneOf': [{'type': 'string'}, {'type': 'null'}]},
        'g': {'anyOf': [{'type': 'boolean'}, {'type': 'number'}], 'allOf': [{'type': ['boolean', 'number']}]},
    },
    'definitions': {'flag': {'type': 'boolean'}},
}
VALID = {'a': 1}


@pytest.mark.parametrize('extra', [
    {'a': 9}, {'b': ['xy']}, {'b': ['xy', 'xyz']}, {'c': 'q'}, {'d': {'k': 1}}, {'e': True},
    {'f': None}, {'f': 'text'}, {'g': True}, {'g': 1.5},
])
def test_a_document_inside_the_schema_conforms(extra):
    assert mxc_schema.validator(SCHEMA)({**VALID, **extra}) is True


@pytest.mark.parametrize('document', [
    {}, {'a': 0}, {'a': 10}, {'a': True}, {'a': 1.0}, {'a': '1'}, {'a': 1, 'z': 1},
    {'a': 1, 'b': []}, {'a': 1, 'b': ['xy', 'xz', 'xw']}, {'a': 1, 'b': ['xy', 'xy']},
    {'a': 1, 'b': ['yy']}, {'a': 1, 'b': ['x']}, {'a': 1, 'b': ['xyzzy']}, {'a': 1, 'b': [1]},
    {'a': 1, 'c': 'r'}, {'a': 1, 'd': {'k': 2}}, {'a': 1, 'e': 1}, {'a': 1, 'f': 1},
    {'a': 1, 'g': 'no'}, [], 'a', None, 1,
])
def test_a_document_outside_the_schema_does_not(document):
    assert mxc_schema.validator(SCHEMA)(document) is False


def test_oneof_needs_exactly_one_branch():
    check = mxc_schema.validator({'oneOf': [{'type': 'integer'}, {'type': 'number'}]})
    assert check(1) is False and check(1.5) is True


@pytest.mark.parametrize('keyword', ['format', 'patternProperties', 'not', 'if', 'then',
                                     'dependencies', 'propertyNames', 'contains', 'minProperties',
                                     'multipleOf', 'additionalItems'])
def test_a_keyword_the_checker_does_not_implement_refuses_the_schema(keyword):
    with pytest.raises(mxc_schema.SchemaError, match=keyword):
        mxc_schema.validator({'properties': {'a': {keyword: 1}}})


@pytest.mark.parametrize('schema', [[], 'x', 5, {'properties': []}, {'items': []},
                                    {'anyOf': {}}, {'properties': {'a': 5}}])
def test_a_schema_of_the_wrong_shape_refuses(schema):
    with pytest.raises(mxc_schema.SchemaError):
        mxc_schema.validator(schema)


def test_an_unresolvable_ref_and_a_ref_loop_do_not_conform():
    assert mxc_schema.validator({'$ref': '#/definitions/nope'})(1) is False
    assert mxc_schema.validator({'$ref': 'http://elsewhere/x'})(1) is False
    loop = {'definitions': {'a': {'$ref': '#/definitions/a'}}, '$ref': '#/definitions/a'}
    assert mxc_schema.validator(loop)(1) is False


def test_boolean_schemas_and_an_unknown_type_name():
    assert mxc_schema.validator({'properties': {'a': False}})({'a': 1}) is False
    assert mxc_schema.validator({'properties': {'a': True}})({'a': 1}) is True
    assert mxc_schema.validator({'type': 'weird'})(1) is False
