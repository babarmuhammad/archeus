import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

MXC = 'archeus/node/mxc.py'
LOCAL = 'archeus/node/local.py'
SCAN = 'archeus/node/linkscan.py'
UNIT = 'tests/v1/unit/test_node_mxc.py::'
LIVE = 'tests/v1/integration/test_pv20_mxc_local.py::'

MUTATIONS = [
    ('HL01', 'grant hardlink gate removed', [(MXC,
     '    linkscan.check_grants((root,), MxcUnavailable)\n', '')],
     [UNIT + 'test_nested_hardlink_refuses_without_outside_path']),
    ('HL02', 'local grant gate removed', [(LOCAL,
     '        linkscan.check_grants((workspace,) + readonly, staging.StageError)\n', '')],
     [LIVE + 'test_shared_hardlink_gate_refuses']),
    ('HL03', 'launch recheck removed', [(LOCAL,
     "        linkscan.check_grants(tuple(fs.get('readwritePaths', ()))\n"
     "                              + tuple(fs.get('readonlyPaths', ())), staging.StageError)\n", '')],
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
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
