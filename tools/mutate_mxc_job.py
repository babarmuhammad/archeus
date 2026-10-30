import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

SOURCE = 'archeus/node/mxc_native.py'
TEST = 'tests/v1/unit/test_mxc_native.py::'

MUTATIONS = [
    ('J01', 'membership check removed', [(SOURCE,
     '            if self.in_job(job, child) is not True:',
     '            if False:')], [TEST + 'test_start_fault_terminates_and_closes']),
    ('J02', 'resume before assignment', [(SOURCE,
     '            self.assign_job(job, child)',
     '            self.resume(child)\n            self.assign_job(job, child)')],
     [TEST + 'test_start_orders_assignment_membership_and_single_resume']),
    ('J03', 'terminate on start fault removed', [(SOURCE,
     '        except BaseException:\n            child.terminate()\n            raise',
     '        except BaseException:\n            child.close()\n            raise')],
     [TEST + 'test_start_fault_terminates_and_closes']),
    ('J04', 'handle close on fault removed', [(SOURCE,
     '            finally:\n                self.close()',
     '            finally:\n                pass')],
     [TEST + 'test_start_fault_terminates_and_closes']),
    ('J05', 'resume once guard removed', [(SOURCE,
     '        if child.resumed:\n', '        if False:\n')],
     [TEST + 'test_start_orders_assignment_membership_and_single_resume']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
