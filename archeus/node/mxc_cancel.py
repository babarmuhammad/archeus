"""Cancellation order and the disposal verdict for one MXC execution (T-454).

Pure orchestration over injected callables. This module owns the ORDER and the
verdict and nothing else: it calls no MXC, Win32, subprocess or ledger API, and
no disposal call is invented here — the caller injects every effect below and
keeps the authority, the handles and the transport behind them.

    revoke_admission(execution)          cut the broker grant, nothing new is served
    end_job(execution)                   end the whole Job Core holds for it
    wait_quiescent(execution, deadline)  True quiescent, False not within the bound,
                                         anything else says nothing about quiescence
    read_back_resources(execution)       True = every owned resource read back gone,
                                         a sequence of text ids = those are still
                                         owned, anything else answers nothing about
                                         ownership
    record(execution, verdict, facts)    persist the verdict for this execution;
                                         record(execution, None, None) reads back what
                                         is already on record and writes nothing

The worst thing seen decides the verdict: a fault anywhere quarantines, a bound
that elapsed without quiescence says still running, and only a clean run of all
four steps verifies disposal. A fault in one step never skips the later steps
that are safe to run: the read-back is read-only, so it runs even when the Job
did not end and even when the process may still be running. A verdict that
cannot be persisted is never reported as if it had been: the recorder's own
failure is the one fault this orchestration does not swallow.
"""

import time

DISPOSED_VERIFIED = 'DISPOSED_VERIFIED'
QUARANTINE_UNVERIFIED = 'QUARANTINE_UNVERIFIED'
STILL_RUNNING = 'STILL_RUNNING'

VERDICTS = (DISPOSED_VERIFIED, QUARANTINE_UNVERIFIED, STILL_RUNNING)

#: The one bound this orchestration owns: how long quiescence may take before the
#: execution is reported still running and the read-back stops being trustworthy.
WAIT_S = 5.0


def _owned_ids(answer):
    """The ids a read-back says are still there; () when it says none are, None when
    it answers nothing about ownership (an untrusted answer is never a verification)."""
    if answer is True:
        return ()
    if isinstance(answer, (tuple, list, set, frozenset)):
        if all(isinstance(item, str) and item for item in answer):
            return tuple(answer)
    return None


def _recorded(record, execution, faults):
    try:
        verdict = record(execution, None, None)
    except Exception as err:
        faults['prior_verdict'] = type(err).__name__
        return None
    return verdict if verdict in VERDICTS else None


def cancel(execution, revoke_admission, end_job, wait_quiescent, read_back_resources,
           record, *, clock=time.monotonic, wait_s=WAIT_S):
    effects = (('revoke_admission', revoke_admission), ('end_job', end_job),
               ('wait_quiescent', wait_quiescent), ('read_back_resources', read_back_resources),
               ('record', record))
    if any(not callable(effect) for _, effect in effects):
        raise ValueError('every cancellation effect must be callable')
    if type(wait_s) not in (int, float) or wait_s <= 0:
        raise ValueError('positive quiescence bound required')

    order, faults = [], {}
    prior = _recorded(record, execution, faults)
    if prior == DISPOSED_VERIFIED:
        return DISPOSED_VERIFIED                  # idempotent: gone and verified once

    order.append('revoke_admission')
    try:
        revoke_admission(execution)
    except Exception as err:
        faults['revoke_admission'] = type(err).__name__

    order.append('end_job')
    try:
        end_job(execution)
    except Exception as err:
        faults['end_job'] = type(err).__name__

    deadline = clock() + wait_s
    order.append('wait_quiescent')
    quiescent = None
    try:
        answer = wait_quiescent(execution, deadline)
        quiescent = answer if answer is True or answer is False else None
        if quiescent is None:
            faults['wait_quiescent'] = 'unverified'
    except Exception as err:
        faults['wait_quiescent'] = type(err).__name__

    owned, read_back = None, None
    if clock() >= deadline:
        faults['read_back'] = read_back = 'timed_out'
    else:
        order.append('read_back_resources')
        try:
            ids = _owned_ids(read_back_resources(execution))
            if ids is None:
                faults['read_back'] = read_back = 'unknown_ownership'
            elif ids:
                faults['read_back'] = read_back = 'still_owned'
                owned = sorted(ids)
            elif clock() >= deadline:
                faults['read_back'] = read_back = 'timed_out'
            else:
                read_back = 'absent'
        except Exception as err:
            faults['read_back'] = read_back = type(err).__name__

    if faults:
        verdict = QUARANTINE_UNVERIFIED
    elif quiescent is False:
        verdict = STILL_RUNNING
    else:
        verdict = DISPOSED_VERIFIED
    if prior == QUARANTINE_UNVERIFIED and verdict == DISPOSED_VERIFIED:
        verdict = QUARANTINE_UNVERIFIED           # only a fresh verification lifts a quarantine

    order.append('record')
    facts = {'order': list(order), 'faults': dict(faults), 'quiescent': quiescent,
             'read_back': read_back, 'owned': owned, 'prior': prior, 'wait_s': wait_s}
    recorded = record(execution, verdict, facts)
    return recorded if recorded in VERDICTS else verdict
