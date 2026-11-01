"""The PV20 B0/B4 mutation suite: break each rule of the reviewed pins, the pinned-schema
validator, the UI posture, the capability set and the explicit environment, run the test
written for it, and require it to fail.

    py tools/mutate_mxc_policy.py               every mutation
    py tools/mutate_mxc_policy.py P01 P05       only these

It edits archeus/node/mxc.py, mxc_pins.py, mxc_schema.py, staging.py and local.py and
restores them whatever happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

MXC = 'archeus/node/mxc.py'
PINS = 'archeus/node/mxc_pins.py'
SCHEMA = 'archeus/node/mxc_schema.py'
STAGING = 'archeus/node/staging.py'
LOCAL = 'archeus/node/local.py'
B = 'tests/v1/unit/test_pv20_mxc_pins.py::'
U = 'tests/v1/unit/test_pv20_mxc_policy_b4.py::'

MUTATIONS = [
    ('P01', 'any UI value compiles, not only the named posture', [(MXC,
     "    if (ui is not False and ui != UI_CODE_CHANGE) or egress != 'deny':",
     "    if egress != 'deny':")],
     [U + 'test_only_the_named_posture_and_false_compile']),
    ('P02', 'the named posture leaves the UI subsystem blocked', [(MXC,
     "        'ui': {'disable': ui is False, 'clipboard': 'none', 'injection': False},",
     "        'ui': {'disable': True, 'clipboard': 'none', 'injection': False},")],
     [U + 'test_the_code_change_posture_opens_only_the_ui_subsystem']),
    ('P03', 'the default posture opens the UI subsystem', [(MXC,
     "        'ui': {'disable': ui is False, 'clipboard': 'none', 'injection': False},",
     "        'ui': {'disable': False, 'clipboard': 'none', 'injection': False},")],
     [U + 'test_the_default_posture_is_blocked']),
    ('P04', 'a ui.disable that is not a boolean validates', [(MXC,
     "                or type(raw['ui']['disable']) is not bool",
     "                or False")],
     [U + 'test_a_ui_disable_that_is_not_a_boolean_does_not_validate']),
    ('P05', 'a capability with no proxy route compiles', [(MXC,
     "    if (bool(value) != bool(proxy) or len(set(map(str, value))) != len(value)",
     "    if (False or len(set(map(str, value))) != len(value)")],
     [U + 'test_a_capability_with_no_proxy_route_is_refused',
      U + 'test_a_proxy_with_an_empty_capability_set_is_refused']),
    ('P06', 'a capability outside the reviewed set compiles', [(MXC,
     "            or any(c not in CAPABILITIES for c in value)):",
     "            or False):")],
     [U + 'test_a_capability_outside_the_reviewed_set_is_refused']),
    ('P07', 'a repeated capability compiles', [(MXC,
     "len(set(map(str, value))) != len(value)",
     "False")],
     [U + 'test_a_capability_outside_the_reviewed_set_is_refused']),
    ('P08', 'a mutated capability section validates', [(MXC,
     "                valid = caps == _capabilities(caps, True)",
     "                valid = True")],
     [U + 'test_a_mutated_capability_section_does_not_validate']),
    ('P09', 'a proxy carries no capability unless it names one', [(MXC,
     "        return list(CAPABILITIES) if proxy else []",
     "        return []")],
     [U + 'test_a_proxy_carries_its_reviewed_capability_by_default']),
    ('P10', 'an edited pins file is trusted without the digest bump', [(PINS,
     "    if digest(pins) != PINS_DIGEST:",
     "    if False:")],
     [B + 'test_a_pin_changed_without_the_digest_bump_is_refused']),
    ('P11', 'an UNSET placeholder counts as a pin', [(PINS,
     "    check_files(entry['files'], required)",
     "    check_files(entry['files'], required, allow_unset=True)")],
     [B + 'test_an_unset_pin_refuses_every_use',
      B + 'test_a_value_that_is_not_a_full_lowercase_hash_is_no_pin']),
    ('P12', 'a pin reviewed for another version is accepted', [(PINS,
     "    if entry['version'] == UNSET or version is not None and entry['version'] != version:",
     "    if entry['version'] == UNSET:")],
     [B + 'test_a_version_the_code_was_not_reviewed_for_is_refused',
      B + 'test_a_pin_for_another_version_of_the_sdk_is_refused']),
    ('P13', 'an UNSET version is accepted', [(PINS,
     "    if entry['version'] == UNSET or version is not None and entry['version'] != version:",
     "    if version is not None and entry['version'] != version:")],
     [B + 'test_an_unset_version_refuses_even_with_every_hash_recorded']),
    ('P14', 'an upper case hash is a pin', [(PINS,
     "_HEX = re.compile(r'[0-9a-f]{64}')",
     "_HEX = re.compile(r'[0-9a-fA-F]{64}')")],
     [B + 'test_a_value_that_is_not_a_full_lowercase_hash_is_no_pin']),
    ('P15', 'a name that climbs out of the tree is a pin name', [(PINS,
     "            and not any(part in ('', '.', '..') for part in rel.split('/')))",
     "            and True)")],
     [B + 'test_a_name_that_is_not_a_safe_relative_path_is_refused']),
    ('P16', 'the staged inventory is never compared with the pins', [(STAGING,
     "    if _mxc_inventory(root) != pins:",
     "    if False:")],
     [B + 'test_a_drifted_sdk_is_refused_against_the_reviewed_file',
      B + 'test_verify_agent_checks_the_binary_folder_against_its_pins']),
    ('P17', 'the policy schema is read without comparing its hash', [(STAGING,
     "    if hashlib.sha256(data).hexdigest() != pins[rel]:",
     "    if False:")],
     [B + 'test_a_schema_that_is_not_the_pinned_bytes_is_refused']),
    ('P18', 'a schema keyword the checker lacks is ignored', [(SCHEMA,
     "            raise SchemaError('schema keyword not implemented: %s' % key)",
     "            pass")],
     [B + 'test_a_keyword_the_checker_does_not_implement_refuses_the_schema']),
    ('P19', 'oneOf accepts several matching branches', [(SCHEMA,
     "sum(bool(sub(s, value)) for s in schema['oneOf']) != 1",
     "sum(bool(sub(s, value)) for s in schema['oneOf']) < 1")],
     [B + 'test_oneof_needs_exactly_one_branch']),
    ('P20', 'additionalProperties is never applied', [(SCHEMA,
     "        extra = schema.get('additionalProperties', True)",
     "        extra = True")],
     [B + 'test_a_document_outside_the_schema_does_not']),
    ('P21', 'a PATH entry may be a writable folder', [(LOCAL,
     "                           and not inside(entry, writable) for entry in path):",
     "                           for entry in path):")],
     [U + 'TestMxcEnv::test_a_writable_folder_inside_a_read_only_grant_is_no_path_entry']),
    ('P22', 'a folder variable may name any place', [(LOCAL,
     "        if name in _MXC_OWN_DIRS and not inside(value, writable):",
     "        if False:")],
     [U + 'TestMxcEnv::test_a_folder_variable_outside_the_execution_folders_is_refused']),
    ('P23', 'the launch never passes the posture on', [(LOCAL,
     "            ui=ui, egress='deny', proxy_url=proxy_url, capabilities=capabilities)",
     "            ui=False, egress='deny', proxy_url=proxy_url, capabilities=capabilities)")],
     [U + 'test_a_launch_carries_the_named_posture_route_and_capabilities']),
    ('P24', 'the launch never passes the proxy route on', [(LOCAL,
     "            ui=ui, egress='deny', proxy_url=proxy_url, capabilities=capabilities)",
     "            ui=ui, egress='deny', proxy_url=None, capabilities=capabilities)")],
     [U + 'test_a_launch_carries_the_named_posture_route_and_capabilities']),
    ('P25', 'the host PATH is kept beside the staged one', [(LOCAL,
     "        if name != 'PATH':\n            out[key] = value",
     "        out[key] = value")],
     [U + 'TestMxcEnv::test_the_host_path_never_reaches_the_container',
      U + 'TestMxcEnv::test_a_lowercase_path_is_dropped_too']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
