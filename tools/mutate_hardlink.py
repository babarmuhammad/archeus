import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

MXC = 'archeus/node/mxc.py'
LOCAL = 'archeus/node/local.py'
SCAN = 'archeus/node/linkscan.py'
UNIT = 'tests/v1/unit/test_node_mxc.py::'
LIVE = 'tests/v1/integration/test_pv20_mxc_local.py::'
GAPS = 'tests/v1/unit/test_node_mxc_gaps.py::'

MUTATIONS = [
    ('HL01', 'grant hardlink gate removed', [(MXC,
     '    linkscan.check_grants((root,), MxcUnavailable)\n', '')],
     [UNIT + 'test_nested_hardlink_refuses_without_outside_path']),
    ('HL02', 'local grant gate removed', [(LOCAL,
     '        linkscan.check_grants((workspace,) + readonly, staging.StageError)\n', '')],
     [LIVE + 'test_shared_hardlink_gate_refuses']),
    ('HL03', 'launch recheck removed', [(LOCAL,
     "        linkscan.check_grants(grants, staging.StageError)\n", '')],
     [LIVE + 'test_shared_hardlink_gate_refuses']),
    ('HL04', 'scan failure accepted', [(SCAN,
     "            raise error('hardlink scan failed; grant refused') from err",
     '            continue')],
     [UNIT + 'test_hardlink_scan_failure_refuses']),
    ('HL05', 'nonregular files reported', [(SCAN,
     'if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:',
     'if info.st_nlink > 1:')],
     ['tests/v1/unit/test_linkscan.py::test_only_regular_files_reported']),
    ('HL06', 'policy launch validation removed', [(MXC,
     'def spawn(policy: MxcPolicy, *, exe, job, backend=None, native_run=False) -> MxcProcess:\n'
     '    validate_policy(policy)',
     'def spawn(policy: MxcPolicy, *, exe, job, backend=None, native_run=False) -> MxcProcess:\n'
     '    pass')],
     [UNIT + 'test_launch_rechecks_before_backend_validation']),
    ('HL07', 'a policy path segment ending in a dot or space passes', [(MXC,
     "or ':' in rest or any(s[-1] in '. ' for s in rest.split('\\\\') if s)):",
     "or ':' in rest):")],
     [GAPS + 'test_a_path_windows_resolves_to_another_path_never_passes_an_overlap_gate']),
    ('HL08', 'a policy path stream syntax passes', [(MXC,
     "or ':' in rest or any(s[-1] in '. ' for s in rest.split('\\\\') if s)):",
     "or any(s[-1] in '. ' for s in rest.split('\\\\') if s)):")],
     [GAPS + 'test_a_path_windows_resolves_to_another_path_never_passes_an_overlap_gate',
      GAPS + 'test_only_a_letter_and_a_colon_make_a_drive']),
    ('HL09', 'a policy path drive need not be a letter', [(MXC,
     "drive[0].isascii() and drive[0].isalpha() and drive[1] == ':'", 'True')],
     [GAPS + 'test_only_a_letter_and_a_colon_make_a_drive']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
