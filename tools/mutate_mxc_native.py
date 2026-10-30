import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

NATIVE = 'archeus/node/mxc_native.py'
MXC = 'archeus/node/mxc.py'
TEST = 'tests/v1/unit/test_mxc_native.py::'

MUTATIONS = [
    ('N01', 'suspended creation removed', [(NATIVE,
     'flags=CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,',
     'flags=EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,')],
     [TEST + 'test_suspended_allowlist_and_resume_once']),
    ('N02', 'resume once check removed', [(NATIVE,
     '        if child.resumed:\n', '        if False:\n')],
     [TEST + 'test_suspended_allowlist_and_resume_once']),
    ('N03', 'fault handle cleanup removed', [(NATIVE,
     '            for handle in reversed(handles):\n                self.api.close_handle(handle)',
     '            for handle in reversed(handles):\n                pass')],
     [TEST + 'test_allocation_fault_closes_every_handle']),
    ('N04', 'inheritance allowlist removed', [(NATIVE,
     'attributes = self.api.attribute_list(inherited)',
     'attributes = self.api.attribute_list(())')],
     [TEST + 'test_suspended_allowlist_and_resume_once']),
    ('N05', 'assignment fault kill removed', [(MXC,
     '                child.terminate()\n', '                pass\n')],
     [TEST + 'test_job_fault_kills_and_closes']),
    ('N06', 'output bound removed', [(NATIVE,
     'if stream.tell() + len(data) > self.transport.output_limit:', 'if False:')],
     [TEST + 'test_output_bound']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
