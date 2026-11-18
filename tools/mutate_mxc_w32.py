import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

SOURCE = 'archeus/node/win32_mxc.py'
TEST = 'tests/v1/unit/test_win32_mxc.py::'

MUTATIONS = [
    ('W01', 'handle list attribute removed', [(SOURCE,
     "            self._call('UpdateProcThreadAttribute', buffer, 0, 0x00020002,\n"
     '                       values, c.sizeof(values), None, None)',
     '            pass')], [TEST + 'test_attribute_contents']),
    ('W02', 'parent end remains inheritable', [(SOURCE,
     "            self._call('SetHandleInformation', parent, 1, 0)",
     '            pass')], [TEST + 'test_pipe_inheritance_and_nowait']),
    ('W03', 'parent environment inherited', [(SOURCE,
     '        environment = environment_block(env)',
     '        environment = None')], [TEST + 'test_explicit_environment_and_creation']),
    ('W04', 'CREATE_SUSPENDED dropped', [(SOURCE,
     '                       flags, environment, cwd, c.byref(startup), c.byref(info))',
     '                       flags & ~4, environment, cwd, c.byref(startup), c.byref(info))')],
     [TEST + 'test_explicit_environment_and_creation']),
    ('W05', 'error code dropped', [(SOURCE,
     "        super().__init__(f'{api}: {code}')",
     '        super().__init__(api)')], [TEST + 'test_error_only_api_and_code']),
    ('W06', 'signature table entry removed', [(SOURCE,
     "    'CloseHandle': ([HANDLE], BOOL),\n", '')],
     [TEST + 'test_signatures_cover_every_api']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
