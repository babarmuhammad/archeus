import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

LEDGER = 'archeus/node/mxc_ledger.py'
TEST = 'tests/v1/unit/test_mxc_ledger.py::'

MUTATIONS = [
    ('L01', 'intent written after native create', [(LEDGER,
     "        self.append(execution_id, 'intent', requested_policy_digest=digest,\n"
     "                    planned=list(planned), applied=[], observed={})\n"
     "        child, facts = create()",
     "        child, facts = create()\n"
     "        self.append(execution_id, 'intent', requested_policy_digest=digest,\n"
     "                    planned=list(planned), applied=[], observed={})")],
     [TEST + 'test_intent_before_create']),
    ('L02', 'durable flush removed', [(LEDGER,
     '            os.fsync(stream.fileno())', '            pass')],
     [TEST + 'test_flush_before_advance']),
    ('L03', 'digest verification removed', [(LEDGER,
     "                    or envelope['sha256'] != hashlib.sha256(payload).hexdigest()\n", '')],
     [TEST + 'test_corrupt_record[digest]']),
    ('L04', 'PID creation-time comparison removed', [(LEDGER,
     '                    elif current != created:', '                    elif False:')],
     [TEST + 'test_never_terminate_unknown']),
    ('L05', 'unknown PID terminated', [(LEDGER,
     '                        state = UNKNOWN_OWNER',
     '                        process_reader.terminate(pid)\n                        state = UNKNOWN_OWNER')],
     [TEST + 'test_never_terminate_unknown']),
    ('L06', 'quarantine persistence removed', [(LEDGER,
     "                self.append(execution_id, 'quarantine', reason='restart_unverified')",
     '                pass')],
     [TEST + 'test_quarantine_second_restart']),
    ('L07', 'ownership saved after advancement', [(LEDGER,
     "        self.append(execution_id, 'ownership', pid=child.pid, create_time=child.create_time,\n"
     "                    requested_policy_digest=digest, applied=facts['applied'],\n"
     "                    observed=facts['observed'], owned=facts['owned'])\n"
     "        advance(child)",
     "        advance(child)\n"
     "        self.append(execution_id, 'ownership', pid=child.pid, create_time=child.create_time,\n"
     "                    requested_policy_digest=digest, applied=facts['applied'],\n"
     "                    observed=facts['observed'], owned=facts['owned'])")],
     [TEST + 'test_flush_before_advance']),
    ('L08', 'persisted quarantine ignored', [(LEDGER,
     "            if invalid or 'quarantine' in ops:", '            if invalid:')],
     [TEST + 'test_quarantine_second_restart']),
    ('L09', 'resource absence accepted without verification', [(LEDGER,
     '                        if resource_reader(execution_id, owner) is True:',
     '                        if True:')],
     [TEST + 'test_restart_states']),
    ('L10', 'disposal readback ignored', [(LEDGER,
     '            if absent(owner) is not True:', '            if False:')],
     [TEST + 'test_disposal_uncertainty_quarantines']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
