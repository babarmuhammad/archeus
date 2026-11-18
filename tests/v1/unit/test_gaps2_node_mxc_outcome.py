"""T-1014: highest-risk uncovered branches of archeus/node/mxc_outcome.py lines 1-131.

Fail-closed and denial paths first, then boundaries, then error paths. The ten selected
branches (all verified uncovered: no test in tests/v1/unit/test_mxc_outcome.py or
tests/v1/unit/test_mxc_wire_outcome.py changes behaviour when the branch is weakened):

 1. L92  `_int(launcher_exit)` — a launcher-report object that is an int *subclass* and
       claims `== 0` would be read as a clean exit (untrusted reporter wins).
 2. L60/L115/L118 `_text` on `execution_id`/`nonce` — a str *subclass* that claims equal
       to anything would bind another execution's or another attempt's report.
 3. L54/L121 `_digest` on `payload_digest` — a str *subclass* naming different content.
 4. L64 `record['status'] not in _STATUS` — an echoed/upper-case verdict word.
 5. L62/L124 `_number` on `timestamp` — a float *subclass* whose arithmetic lands the
       stale record inside the accepted window.
 6. L67/L69 `_int` on `workload_exit` — an int *subclass* that claims zero while the
       workload really exited non-zero.
 7. L60/L75 nonce text checks together — a blank nonce on *both* sides would bind.
 8. L60/L75 `_text(record['nonce'])` / `_text(binding['nonce'])` — a nonce that is not
       usable text must read as damage (UNVERIFIED), never as forgery.
 9. L54 `_digest(value)` first operand — a `payload_digest`/`digest` that is not a str
       must fail closed instead of raising out of `bind_outcome`.
10. L106/L109 `record is None` — an empty string report is damaged evidence, not an
       absent one (the invariant spelled out in the comment at L103-105).

The module is pure: it takes no OS call, no clock and no digest function, so the only
seam is the injected `read_workload_outcome`, which every test fakes here. Nothing real
is launched, no DLL is loaded, no file is written and no sleep is taken, so the file is
platform-neutral by construction. Cards stay independent: nothing from another
test_gaps2 module is imported and no test depends on execution order.
"""

import pytest

from archeus.node import mxc_outcome as outcome

NOW = 1000
MAX_AGE = 60
EXEC = 'exec-7'
NONCE = 'nonce-a'
DIGEST = 'a' * 64
OTHER_DIGEST = 'b' * 64


def issued(**change):
    binding = {'execution_id': EXEC, 'nonce': NONCE, 'digest': DIGEST,
               'now': NOW, 'max_age': MAX_AGE}
    binding.update(change)
    return binding


def reported(**change):
    record = {'execution_id': EXEC, 'nonce': NONCE, 'payload_digest': DIGEST,
              'timestamp': NOW - 5, 'status': 'succeeded', 'workload_exit': 0}
    record.update(change)
    return record


def once(value):
    calls = []

    def read():
        calls.append(1)
        return value
    read.calls = calls
    return read


class ClaimStr(str):
    """A str subclass that claims equality with every non-empty string it meets.

    It answers `!= ''` truthfully so a lenient `isinstance(value, str)` check would
    take it for real text, while `x != 'some issued value'` comes back False.
    """

    def __eq__(self, other):
        return type(other) is str and other != ''

    def __ne__(self, other):
        return not (type(other) is str and other != '')

    def __hash__(self):
        return str.__hash__(self)


class ClaimInt(int):
    """An int subclass carrying a real value that claims to be exactly zero."""

    def __eq__(self, other):
        return type(other) is int and int(other) == 0

    def __ne__(self, other):
        return not (type(other) is int and int(other) == 0)

    def __hash__(self):
        return int.__hash__(self)


class ClaimFloat(float):
    """A float subclass that is always the right distance behind `now`."""

    def __rsub__(self, other):
        return 5


def assert_denied(result, state, launcher_exit=0):
    """Every denial is a denial: no success, no borrowed workload exit, no second read."""
    assert result.state == state
    assert result.state != outcome.SUCCEEDED
    assert result.succeeded is False
    assert result.workload_exit is None
    assert result.launcher_exit == launcher_exit
    assert outcome.SUCCEEDED not in result.reason


# 1. the launcher is an untrusted reporter: a nonzero exit dressed up as 0 is not clean
@pytest.mark.parametrize('reported_exit', [7, -9, 259])
def test_a_lying_int_subclass_launcher_exit_is_never_a_clean_exit(reported_exit):
    # L92 `_int(launcher_exit)`. Closest existing test:
    # test_launcher_exit_that_is_not_an_integer_fails, whose values (None, True, 0.0,
    # '0', [], {}, object()) can never answer `!= 0` falsely, so it cannot see a
    # reporter object that is an int subclass lying about its value.
    claimed = ClaimInt(reported_exit)
    assert int(claimed) == reported_exit and (claimed == 0) is True
    read = once(reported())
    result = outcome.bind_outcome(claimed, read, issued())
    assert result.state == outcome.LAUNCHER_FAILED
    assert result.launcher_exit is claimed
    # fail-closed order: an exit code that is not an exact int never opens the channel
    assert read.calls == []


# 2. the identity the workload was handed is compared by exact value and exact type
def test_a_lying_string_subclass_identity_never_binds_another_execution():
    # L60 `_text(record['execution_id'])` feeding L115. Closest existing tests:
    # test_a_malformed_report_is_unverified['identity-not-text'] (an int, so the
    # str-subclass path is not taken) and test_every_forgery_is_refused['execution_id']
    # (a plain different string, which a `__ne__` lying object would have satisfied).
    record = reported(execution_id=ClaimStr('exec-of-another-workload'))
    assert (record['execution_id'] == EXEC) is True
    assert str(record['execution_id']) != EXEC
    read = once(record)
    result = outcome.bind_outcome(0, read, issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


def test_a_lying_string_subclass_nonce_never_binds_another_attempt():
    # L60 `_text(record['nonce'])` feeding L118. Closest existing test:
    # test_identity_of_another_attempt_is_never_reused compares plain strings, so it
    # never exercises a value that is a str subclass with an inherited-looking identity.
    record = reported(nonce=ClaimStr('nonce-of-a-previous-attempt'))
    assert (record['nonce'] == NONCE) is True
    assert str(record['nonce']) != NONCE
    read = once(record)
    result = outcome.bind_outcome(0, read, issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


# 3. content binding is by exact hex text, not by a duck-typed string
def test_a_lying_string_subclass_payload_digest_never_binds_the_issued_content():
    # L54 `_digest(record['payload_digest'])` feeding L121. Closest existing tests:
    # test_a_malformed_report_is_unverified['digest-not-hex'] / ['digest-length'] are
    # plain strings, and test_every_forgery_is_refused['payload_digest'] uses a plain
    # OTHER digest, so none of them needs the `type(value) is str` operand.
    record = reported(payload_digest=ClaimStr(OTHER_DIGEST))
    assert len(str(record['payload_digest'])) == 64
    assert (record['payload_digest'] == DIGEST) is True
    assert str(record['payload_digest']) != DIGEST
    read = once(record)
    result = outcome.bind_outcome(0, read, issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


# 4. the only verdict words are the two exact lowercase ones the protocol defines
@pytest.mark.parametrize('echoed', [
    'SUCCEEDED', 'Succeeded', 'succeeded\n', ' succeeded', 'succeeded ', 'sUcCeEdEd',
], ids=['upper', 'title', 'newline', 'lead-space', 'trail-space', 'mixed'])
def test_an_echoed_verdict_word_is_not_the_workloads_own_report(echoed):
    # L64 `record['status'] not in _STATUS`. Closest existing test:
    # test_a_malformed_report_is_unverified['status-unknown'] / ['status-empty'] only
    # try 'ok' and '', never the module's own state names in another case or padded
    # with whitespace, which is exactly what a launcher echoing stdout would carry.
    record = reported(status=echoed, workload_exit=0)
    read = once(record)
    result = outcome.bind_outcome(0, read, issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


def test_an_echoed_failure_word_does_not_borrow_the_workloads_exit_code():
    # L64 again for the failed verdict: 'FAILED' is not a verdict either, and a denial
    # must not hand back the workload's claimed exit code. Closest existing test:
    # test_verified_workload_failure_is_not_missing_or_unverified uses the exact word.
    record = reported(status='FAILED', workload_exit=3)
    result = outcome.bind_outcome(0, once(record), issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)


# 5. the accepted window is arithmetic on a real number, never on a claim
def test_a_lying_float_subclass_timestamp_never_widens_the_accepted_window():
    # L62 `_number(record['timestamp'])` feeding L124-125. Closest existing tests:
    # test_every_forgery_is_refused['stale'] / ['future'] and
    # test_accepted_window_is_the_callers_clock all pass plain ints or floats, so a
    # timestamp whose own arithmetic decides the window is never exercised.
    stale = ClaimFloat(1.0)
    assert float(stale) < NOW - MAX_AGE            # genuinely far outside the window
    assert (NOW - stale) == 5                      # ... and it lies about the age
    read = once(reported(timestamp=stale))
    result = outcome.bind_outcome(0, read, issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


# 6. the workload cannot report success while its own exit code says otherwise
@pytest.mark.parametrize('claimed_exit', [7, -9], ids=['positive', 'negative'])
def test_a_lying_int_subclass_workload_exit_never_buys_success(claimed_exit):
    # L67 `_int(exit_code)` with L69's consistency rule. Closest existing tests:
    # test_a_malformed_report_is_unverified['exit-bool'] (a bool, not an int subclass)
    # and ['success-with-exit'] (a plain non-zero int), so `exit_code == 0` is never
    # asked of an object that can answer it falsely.
    claimed = ClaimInt(claimed_exit)
    assert int(claimed) == claimed_exit and (claimed == 0) is True
    record = reported(status='succeeded', workload_exit=claimed)
    read = once(record)
    result = outcome.bind_outcome(0, read, issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


# 7. a nonce that was never handed out cannot be "the nonce of this attempt"
def test_a_blank_nonce_on_both_sides_never_binds_a_success():
    # L60 and L75 together: if either text check went, an empty nonce on the report and
    # on the issued identity would compare equal and bind. Closest existing tests:
    # test_every_forgery_is_refused['nonce'] and test_a_malformed_report_is_unverified
    # ['missing-field'] only ever vary a *present, well-typed* nonce on one side.
    record = reported(nonce='')
    binding = issued(nonce='')
    assert record['nonce'] == binding['nonce']
    read = once(record)
    result = outcome.bind_outcome(0, read, binding)
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


# 8. a nonce that is not text is damaged evidence, not a forgery and not an absence
@pytest.mark.parametrize('broken', [0, True, None, 1.0, b'nonce-a'],
                         ids=['zero', 'true', 'none', 'float', 'bytes'])
def test_a_nonce_that_is_not_usable_text_is_damage_not_forgery(broken):
    # L60 `_text(record['nonce'])` and L75 `_text(binding['nonce'])`. Closest existing
    # tests: test_a_malformed_report_is_unverified never varies the nonce's type and
    # test_an_unavailable_identity_is_unverified_not_forged always carries a valid
    # nonce, so a non-text nonce on either side would silently fall through to the
    # `!=` comparison at L118 / L115 and be labelled OUTCOME_FORGED.
    damaged_record = reported(nonce=broken)
    read = once(damaged_record)
    assert_denied(outcome.bind_outcome(0, read, issued()), outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]
    damaged_binding = issued(nonce=broken)
    read = once(reported())
    assert_denied(outcome.bind_outcome(0, read, damaged_binding), outcome.OUTCOME_UNVERIFIED)
    assert read.calls == [1]


# 9. a digest that is not a string fails closed instead of raising out of the binding
@pytest.mark.parametrize('not_text', [None, 7, 7.5, b'ab', 'a' * 63],
                         ids=['none', 'int', 'float', 'bytes', 'short'])
def test_a_digest_that_is_not_a_string_is_unverified_and_never_raises(not_text):
    # L54 `_digest(value)` first operand, reached from L62 (record payload_digest) and
    # L77 (issued digest). Closest existing tests: test_a_malformed_report_is_unverified
    # ['digest-not-hex'] / ['digest-length'] and
    # test_an_unavailable_identity_is_unverified_not_forged all pass *strings*, so the
    # `type(value) is str` guard is never what saves them; without it `len(not_text)`
    # raises TypeError straight out of bind_outcome, past the OUTCOME_UNVERIFIED return
    # and past the caller's quarantine decision.
    for record, binding in ((reported(payload_digest=not_text), issued()),
                            (reported(), issued(digest=not_text))):
        read = once(record)
        assert_denied(outcome.bind_outcome(0, read, binding), outcome.OUTCOME_UNVERIFIED)
        assert read.calls == [1]


# 10. "nothing was reported" is only ever an explicit None
@pytest.mark.parametrize('damaged', ['', 0, 0.0, {}, [], ()],
                         ids=['empty-string', 'zero', 'zero-float', 'empty-dict',
                              'empty-list', 'empty-tuple'])
def test_an_empty_report_is_damaged_evidence_not_an_absent_one(damaged):
    # L106 `record is None` with L109 `_shape`. Closest existing tests:
    # test_a_malformed_report_is_unverified['empty-dict'] / ['zero'] and
    # test_a_clean_exit_code_is_never_an_outcome_by_itself never read the *empty
    # string*, the one falsy value that a reader which lost the file would hand back,
    # and which the comment at L103-105 promises must not read as OUTCOME_MISSING.
    read = once(damaged)
    result = outcome.bind_outcome(0, read, issued())
    assert_denied(result, outcome.OUTCOME_UNVERIFIED)
    assert result.state != outcome.OUTCOME_MISSING
    assert read.calls == [1]
