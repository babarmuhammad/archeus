"""T-334 — the highest-risk uncovered branches of `archeus/node/isolation.py`
lines 1-650: the fail-closed and denial paths first, then boundary values, then
error paths. Runs everywhere (the same fixtures as the synthetic tests, no OS
calls); the real mechanism stays the Windows integration file's job.

Style and fixtures are copied from the closest existing tests of this module,
`tests/v1/unit/test_pv20_isolation.py`, narrowed to what these branches need.
Every test names, in its docstring, the source branch whose removal or
inversion it catches:

1.  isolation.py:377-378  `_derive`'s `except IsolationUnavailable: return None`
2.  isolation.py:303-305  the job condition with no job facts at all
3.  isolation.py:303-304  the job condition with the wrong type, or a name that
                          could not be read (job_facts name None)
4.  isolation.py:381-382  `unmet_conditions`'s missing-key default `(False, '')`
5.  isolation.py:423,425  A4's `is`-comparisons: a truthy stand-in is not the fact
6.  isolation.py:439-440  `is_test_harness_id`'s 'test' prefix (and the adapter
                          seam `is_test_harness` reads when no id is present)
7.  isolation.py:544-545  `_identity_problem`'s `sid_underivable` refusal
8.  isolation.py:526-530  `_shape_problem` over the LEDGER types (via
                          `_ledger_problem`, isolation.py:571-587) — the
                          `released` early return included
9.  isolation.py:639-641  `Isolation.boundary`'s default on a platform without
                          the real boundary (fail-closed, never a guess)
10. isolation.py:62-63    `profile_name`'s sanitize/lower/127-cut
11. isolation.py:67       `is_stale_profile`'s guards (the boot reclaim's delete
                          filter)
12. isolation.py:356-360  `_within`'s separator-bounded prefix test (a sibling
                          sharing a name prefix is not nested)
"""

import json
import os
import sys
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.node import isolation as iso


def new_execution_id():
    return ids.new_id('execution')


# ── the synthetic boundary, copied from the closest existing tests ────────────

def _stable_sid(name):
    return 'S-1-15-3-9-' + str(abs(hash(str(name))) % (10 ** 8))


class FakeBoundary:
    """The answers `check_invariant` reads, each one a knob (the same fake, cut
    down to the readers these branches use; it never launches anything)."""
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.grant_ok = True
        self.broad = None
        self.core_state_granted = False
        self.caps = ()
        self.derive_fail = False            # the SID cannot be derived at all

    def available(self):
        return self.available_ok

    def derive_sid(self, execution_id):
        if self.derive_fail:
            raise iso.IsolationUnavailable('sid_derive', 'synthetic')
        return _stable_sid(iso.profile_name(execution_id))

    def grant_established(self, path, sid, access):
        return bool(self.grant_ok)

    def broad_write_grant(self, path, sid):
        return self.broad

    def granted_to(self, path, sid):
        return bool(self.core_state_granted) and 'core_state' in str(path)

    def capability_grants(self):
        return tuple(self.caps)


def make_satisfying_request(execution_id, root):
    """Copied verbatim from the existing tests: every required row present, the
    classes separated, Core's own state outside the boundary — all six conditions
    hold, so any single unmet one is the branch under test."""
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    workspace = d('workspace')
    runtime = d('runtime')
    hook = d('hook')
    mailbox = d('mailbox')
    response = d('response')
    sentinel = d('sentinel')
    state = d('state')
    core_state = d('core_state')
    broker = d('broker')
    spawn_config = os.path.join(response, 'spawn_config.json')
    with open(spawn_config, 'w', encoding='utf-8') as f:
        json.dump({'argv': []}, f)
    grants = (iso.Grant(workspace, 'rw', 'workspace'),
              iso.Grant(runtime, 'rx', 'runtime'),
              iso.Grant(hook, 'rx', 'hook'),
              iso.Grant(mailbox, 'rw', 'request'),
              iso.Grant(response, 'rx', 'response'),
              iso.Grant(sentinel, 'rx', 'sentinel'),
              iso.Grant(state, 'rw', 'state'))
    return iso.IsolationRequest(execution_id=execution_id, workspace=workspace,
                                grants=grants, mailbox=mailbox, response=response,
                                sentinel=sentinel, spawn_config=spawn_config,
                                state_dir=state, core_state=core_state, broker=broker)


GOOD_JOB = {'type': 'Job', 'name': '', 'inheritable': False}


def _conds(b, req, job_facts=GOOD_JOB):
    return iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                               job_facts)


# ── 1: a boundary that cannot answer is a failed condition, never a pass ─────

class TestUnreadableAnswersFailClosed:
    def test_a_sid_that_cannot_be_derived_leaves_identity_unmet_and_never_raises(
            self, tmp_path):
        # catches inverting/removing isolation.py:377-378 (`except
        # IsolationUnavailable: return None` in `_derive`): uncaught, this test
        # raises instead of recording; treated-as-derived, the identity condition
        # would hold on a SID nobody established.
        b = FakeBoundary()
        b.derive_fail = True
        req = make_satisfying_request(new_execution_id(), str(tmp_path))
        conds = iso.check_invariant(b, req, {'created': True, 'sid': 'S-1-15-3-9-7'},
                                    GOOD_JOB)
        assert conds['identity'] == (False, 'no profile was created for this execution')
        assert iso.unmet_conditions(conds) == ('identity',)   # and nothing else broke

    @pytest.mark.skipif(sys.platform == 'win32',
                        reason='on Windows the default boundary is the real WindowsBoundary; '
                               'this asserts the non-Windows default fails closed')
    def test_the_default_boundary_of_an_authority_fails_closed(self, tmp_path):
        # catches inverting isolation.py:639-641 (`WindowsBoundary() if WINDOWS
        # else UnavailableBoundary()`): any default that is not the always-
        # unavailable boundary lets an authority on a platform without the real
        # boundary answer available/reads with something other than a refusal.
        a = iso.Isolation()
        assert isinstance(a.boundary, iso.UnavailableBoundary)
        assert a.boundary is a.boundary                       # created once, then cached
        assert a.boundary.available() is False                # §3.4: nothing may start
        other = iso.Isolation()
        b = FakeBoundary()
        other.set_boundary(b)
        assert other.boundary is b                            # an injected one is kept
        # and every read it does answer raises: `establish` would record the failure
        req = make_satisfying_request(new_execution_id(), str(tmp_path))
        with pytest.raises(iso.IsolationUnavailable) as err:
            iso.check_invariant(iso.Isolation().boundary, req,
                                {'created': True, 'sid': 'S-1-15-3-9-1'}, GOOD_JOB)
        assert err.value.reason == 'platform'


# ── 2/3/4: the Job is a fact, and a condition nobody answered is unmet ────────

class TestJobConditionAndMissingFacts:
    @pytest.mark.parametrize('job_facts', [
        None,                                        # the execution has no Job at all
        {'type': 'Process', 'name': '', 'inheritable': False},   # not a Job object
        {'type': 'Job', 'name': None, 'inheritable': False},     # name unreadable: no proof
    ], ids=['no_job_facts', 'not_a_job', 'job_name_unreadable'])
    def test_the_job_condition_holds_only_on_a_proven_unnamed_job(self, tmp_path,
                                                                   job_facts):
        # catches dropping `job_facts and` / the type check / `name == ''` from
        # isolation.py:303-304: with any one gone, the matching fact below would
        # make the Job condition hold and unmet_conditions() would come back empty.
        b = FakeBoundary()
        req = make_satisfying_request(new_execution_id(), str(tmp_path))
        conds = _conds(b, req, job_facts=job_facts)
        assert conds['job'][0] is False
        assert iso.unmet_conditions(conds) == ('job',)
        if job_facts is None:
            assert conds['job'][1] == 'the execution has no Core-held Job'
        else:
            assert 'no Core-held Job' not in conds['job'][1]   # the named/inheritable text

    def test_a_condition_nobody_answered_counts_as_unmet(self):
        # catches weakening isolation.py:382's default `conditions.get(name,
        # (False, ''))` to a missing key counting as held: every case below then
        # reports fewer unmet conditions than there are.
        assert iso.unmet_conditions({}) == iso.CONDITIONS
        partial = {name: (True, '') for name in iso.CONDITIONS if name != 'grants'}
        assert iso.unmet_conditions(partial) == ('grants',)
        assert iso.unmet_conditions(dict.fromkeys(iso.CONDITIONS, (False, 'x'))) \
            == iso.CONDITIONS                                  # reported in §3.4's order


# ── 5/6: A4's facts must be the facts; a test harness is never eligible ──────

A4_FACTS = dict(isolated_launch=True, job_held=True, sandbox=False,
                exception_claimed=False, evidence='from-path')


class TestA4Facts:
    @pytest.mark.parametrize('over,unmet', [
        ({'sandbox': 'yes'}, ('sandbox_inner_layer',)),
        ({'sandbox': 1}, ('sandbox_inner_layer',)),
        ({'sandbox': None}, ('sandbox_inner_layer',)),
        ({'exception_claimed': True}, ('no_harness_exception',)),
        ({'evidence': []}, ('evidence_from_path',)),
        ({'sandbox': True}, ()),                                 # the accepted side
    ], ids=['sandbox_yes', 'sandbox_1', 'sandbox_none', 'exception_true',
            'evidence_empty', 'sandbox_true_holds'])
    def test_only_the_fact_itself_satisfies_an_a4_condition(self, over, unmet):
        # catches inverting isolation.py:423 (`is not False and is not True`) or
        # 425 (`is not False`) to truthiness: then 'yes'/1 would claim an inner
        # layer nobody established and an asserted exception would be no exception.
        ok, got = iso.a4_eligibility(harness_id='real-agent', **{**A4_FACTS, **over})
        assert got == unmet and ok is (not unmet)

    def test_a_test_prefixed_harness_is_never_production_eligible(self):
        # catches removing 'test' from isolation.py:440's `('fake', 'test')` or
        # the `or`-guards/attribute lookups at 434-437/440: a 'test-…' adapter
        # would then be production-dispatchable, and an adapter whose id is
        # absent would crash instead of falling back to its test_harness flag.
        assert iso.is_test_harness_id('test-runner') is True
        assert iso.is_test_harness_id('fake-runner') is True
        assert iso.is_test_harness_id('real-agent') is False
        assert iso.is_test_harness_id('') is False
        assert iso.is_test_harness_id(None) is False
        ok, unmet = iso.a4_eligibility(harness_id='test-runner', **A4_FACTS)
        assert ok is False and unmet == ('production_dispatch',)
        assert iso.is_test_harness(SimpleNamespace(id='test-runner')) is True
        assert iso.is_test_harness(SimpleNamespace(id=None, test_harness=True)) is True
        assert iso.is_test_harness(SimpleNamespace(id='real-agent',
                                                   test_harness=True)) is True
        assert iso.is_test_harness(SimpleNamespace()) is False


# ── 7/8: persisted records and ledger lines are believed only in shape ────────

class TestPersistedTrust:
    def test_a_record_sid_that_cannot_be_derived_is_refused_as_ununderivable(
            self, tmp_path):
        # catches removing isolation.py:544-545 (`except IsolationUnavailable:
        # return 'sid_underivable'`): without it this call raises out of the
        # reclaim/sweep read path, and any fallback that believed an unreadable
        # SID would return '' (the record trusted) instead of the refusal word.
        eid = new_execution_id()
        b = FakeBoundary()
        b.derive_fail = True
        d = iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid),
                                sid='S-1-15-3-9-777', state='established',
                                planned=(iso.Grant(str(tmp_path), 'rx', 'runtime'),))
        assert iso._identity_problem(eid, d.as_dict(), b, False) == 'sid_underivable'

    @pytest.mark.parametrize('over,want', [
        ({'at': 'yesterday'}, 'malformed:at'),
        ({'op': 5}, 'malformed:op'),
        ({'planned': 'checkout'}, 'malformed:planned'),
        ({'grants': [{'path': 'x', 'access': 'rx', 'row': 'runtime'}]},
         'unknown_fields:grants'),
        ({'op': 'grant'}, 'op_unknown'),
        ({'execution_id': 'exe_NOPE0000000000000000000'}, 'execution_id_invalid'),
        # a `released` line proves only its principal: the identity fields are the
        # quarantining line's burden (isolation.py:585-586 returns before 587)
        ({'op': 'released', 'profile': 'archeus.spike.life0', 'sid': 'S-1-5-18'}, ''),
        ({'profile': 'archeus.spike.life0'}, 'profile_mismatch'),
    ], ids=['at_str', 'op_int', 'planned_str', 'extra_field', 'op_grant',
            'bad_execution_id', 'released_skips_identity', 'quarantine_profile'])
    def test_a_quarantine_line_is_believed_only_in_its_declared_shape(self, over, want):
        # catches bypassing `_shape_problem` (isolation.py:526-530) on the LEDGER
        # types: a line with a typed field out of shape, an unknown field, an
        # unknown op or an unparseable principal would then be trusted, and the
        # `released` early return at 585-586, removed, would demand a matching
        # profile/sid that a release line never carries.
        eid = new_execution_id()
        b = FakeBoundary()
        good = {'op': 'quarantine', 'execution_id': eid, 'profile': iso.profile_name(eid),
                'sid': '', 'planned': [], 'reason': 'cleanup failed', 'at': 1.5}
        assert iso._ledger_problem(good, b) == ''               # the baseline is trusted
        assert iso._ledger_problem(dict(good, **over), b) == want


# ── 10/11/12: name derivation and the separator-bounded nesting test ──────────

class TestProfileNamesAndSeparation:
    def test_a_profile_name_is_sanitized_lowered_and_cut_to_the_limit(self):
        # catches removing the replacement, the lower() or the [:127] cut from
        # isolation.py:62-63: a name would then carry a path separator or a
        # forbidden character, differ only by case between two executions, or
        # run past the 127-character limit the OS profile store refuses.
        assert iso.profile_name('../A B?C:D*E') == 'archeus.exec...-a-b-c-d-e'
        for n in (114, 115, 300):                     # 13 + 114 is exactly the limit
            name = iso.profile_name('z' * n)
            assert name == ('archeus.exec.' + 'z' * n)[:127]
            assert len(name) == min(13 + n, 127)
        assert set(iso.profile_name('we/ird?na:me*')) <= set(
            'abcdefghijklmnopqrstuvwxyz0123456789_.-')

    def test_only_a_profile_this_module_names_is_stale(self):
        # catches loosening isolation.py:67 (`str(name or '').lower().startswith(
        # (PROFILE_PREFIX, VERIFY_PREFIX))`): without the lower() an
        # upper-cased profile escapes the boot reclaim; without the anchored
        # prefixes an ordinary directory named `archeus.exec` or a verifier *key*
        # (never a profile name) would be swept as stale.
        assert iso.is_stale_profile(None) is False
        assert iso.is_stale_profile('') is False
        assert iso.is_stale_profile('archeus.exec') is False
        assert iso.is_stale_profile('archeus.execx.anything') is False
        assert iso.is_stale_profile('verify/exe_%s.0' % new_execution_id()) is False
        assert iso.is_stale_profile('archeus.exec.abc') is True
        assert iso.is_stale_profile('ARCHEUS.EXEC.ABC') is True
        assert iso.is_stale_profile('archeus.verify.vid.2') is True

    def test_sibling_directories_that_share_a_name_prefix_are_not_nested(
            self, tmp_path):
        # catches the separator in isolation.py:360 (`b.rstrip(os.sep) + os.sep`)
        # disappearing from `_within`: `inbox2` would then read as inside `inbox`,
        # condition 5 would refuse a valid layout, and `_separate` below flips.
        # Removing the `a == b` arm instead lets two classes share one directory.
        base = str(tmp_path)
        inner = os.path.join(base, 'inbox')
        deep = os.path.join(inner, 'deep')
        sibling = os.path.join(base, 'inbox2')
        os.makedirs(deep)
        assert iso._within(inner, inner) is True                # one directory is itself
        assert iso._within(deep, inner) is True
        assert iso._within(sibling, inner) is False             # the prefix trap
        assert iso._within(inner, sibling) is False
        assert iso._separate([inner, sibling]) is True
        assert iso._separate([inner, deep]) is False
        assert iso._separate([inner], apart=[base]) is False    # a parent holds it
        assert iso._separate([inner], apart=['']) is True       # an unnamed parent judges nothing
