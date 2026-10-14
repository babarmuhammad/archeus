"""PV-20 S1: the isolated execution path (pv20-execution-isolation-design §3.1–§3.4, §3.7–§3.8).

Nine things live here, and only nine:

1. **Per-execution identity** (§3.1, R7) — one AppContainer profile per *execution*,
   created before its first spawn, reused by its resumes, torn down when it ends.
   No principal is ever shared between executions.
2. **Core-held kill-on-close Job** (§3.7, R6-A) — unnamed, class-9 limits, held only
   by the Core process that spawned the execution.
3. **The process-registry entry** (§3.7, item 83) — an instrument, not a lifetime
   authority; the Job is the lifetime authority. (`LocalNode` writes the line.)
4. **Teardown** (§3.2 Cleanup) — the identity deleted on every end path. S1 applies no
   ACE at all (grant application is outside S1, per its acceptance record), so there
   is nothing to revoke, and no code in S1 changes an ACL.
5. **Quarantine** (§3.7) — a profile that cannot be removed is quarantined, retried
   on boot, and never re-granted to anybody else.
6. **Restart reconciliation** (§3.7) — the records here decide what a restarted Core
   may and may not adopt; nothing an execution could have written is authority.
7. **The isolated spawn path** (§3.4) — the new mechanism behind the `base.spawn`
   seam. The pre-spawn invariant governs it; any condition unmet → fail closed.
   **There is no unisolated fallback and no setting that disables the invariant.**
8. **A4 eligibility** (§3.8, H-1) — *built, not enforced*: `a4_eligibility` exists and
   fails closed, and nothing on the dispatch path calls it until the owner authorizes
   enforcement (slice E).
9. **Zero network capability** (§4.9 of the S1 gate) — the identity is created with no
   capability SIDs at all, so it holds no network capability; P23 is untouched.

The two rules everything else follows from: an isolation-establishment failure means
**no process starts** (§3.4, §6.3), and a spawn failure never puts the untrusted
execution in the interactive user's security context. Production dispatch of isolated
executions stays E's: `PRODUCTION_DISPATCH_ENABLED` is False, so while S1 stands no
real harness is ever dispatched isolated (PV-20 §3.4, ADR-0053 §3.4).

The OS mechanism is the one the owner-authorized go/no-go spike validated
(`.spike/winapi.py`): pure ctypes, no admin, no C toolchain. Spike-derived constraints
honoured here (S1 gate §5): the environment block is passed explicitly and never
inherited-by-luck; Jobs are identified with `NtQueryObject`, not `GetFileType`; the
identity's lifecycle is read from the package-directory state, not
`GetAppContainerFolderPath`.

**Persisted state is never authority over what gets mutated.** A record or ledger
line names an execution; the profile and SID acted on are re-derived from that
execution's validated id, and a record whose contents disagree with the derivation is
reported and left exactly as found. The ad hoc probes of 2026-10-08 granted the real
Python install through a path parameter and broke it; nothing here takes one.
"""

import json
import os
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field

from claude_sessions import config

from ..core.domain import ids
from ..harnesses import base
from ..infra.paths import (MAX_ATTEMPT, VERIFY_KEY, ExecPaths, isolation_dir, isolation_state,
                           verify_consumed,
                           quarantine_log, run_dir, verify_key_parts)
from . import staging

WINDOWS = sys.platform.startswith('win')

#: §4.9: the identity is created with NO capabilities, so it holds no network
#: capability and P23's decision is not pre-empted. Nothing may widen this tuple:
#: a capability is a grant, and the grant inventory (§3.1) contains none.
CAPABILITIES = ()

#: the well-known capability SIDs whose absence §4.9 requires. `internetClientServer`
#: and `privateNetworkClientServer` are the two that would reach a network.
NETWORK_CAPABILITY_SIDS = ('S-1-15-3-1', 'S-1-15-3-2')

#: the principal's name is derived from the execution id, so a resume of an execution
#: reaches its own identity and no other execution can name it (R7).
PROFILE_PREFIX = 'archeus.exec.'
#: a verifier attempt's principal (A6): derived from its verification id and attempt,
#: so it never equals or contains an execution's
VERIFY_PREFIX = 'archeus.verify.'

#: E's constant, not a setting: production dispatch of isolated executions is not
#: implemented, so no real harness is dispatched isolated (PV-20 §3.4, §3.8; S1 gate
#: §7.5.10). Flipping it is E's authorization, not configuration.
PRODUCTION_DISPATCH_ENABLED = False


def production_dispatch_enabled():
    return bool(PRODUCTION_DISPATCH_ENABLED)


def profile_name(execution_id):
    """R7: the per-execution principal's name — one per execution, never shared, and
    re-derivable (which is what lets a resume reuse it and a boot reclaim find it). A
    verifier key names `archeus.verify.<verification_id>.<attempt>`."""
    if str(execution_id).startswith(VERIFY_KEY):
        p = principal(execution_id)
        return '%s%s.%d' % (VERIFY_PREFIX, p.owner_id.lower(), p.attempt)
    safe = ''.join(c if (c.isalnum() or c in '_.-') else '-' for c in str(execution_id))
    return (PROFILE_PREFIX + safe.lower())[:127]


def is_stale_profile(name):
    return str(name or '').lower().startswith((PROFILE_PREFIX, VERIFY_PREFIX))


class IsolationUnavailable(Exception):
    """Confinement could not be established. Nothing starts (the isolated path has no
    fallback, §3.4/§6.3); `reason` is one of the stable codes the record keeps."""

    def __init__(self, reason, detail=''):
        self.reason, self.detail = reason, str(detail or '')
        super().__init__('isolation unavailable (%s)%s'
                         % (reason, ': %s' % detail if detail else ''))


@dataclass(frozen=True)
class Principal:
    """One isolated principal (A6, T-054 C-1013 §2): the Core id it serves and, for a
    verifier, which attempt. Its `key` is the only map key, record path and name source;
    an execution's key is its own id. Every attempt is its own principal, so a retry
    never reuses one."""
    kind: str                   # 'exec' | 'verify'
    owner_id: str
    attempt: int = 0

    def __post_init__(self):
        owner = {'exec': 'execution', 'verify': 'verification'}.get(self.kind)
        if not (owner and ids.is_id(self.owner_id, owner) and type(self.attempt) is int
                and 0 <= self.attempt < MAX_ATTEMPT
                and (self.kind == 'verify' or self.attempt == 0)):
            raise IsolationUnavailable('profile_name', 'not a principal: %r' % (self,))

    @property
    def key(self):
        if self.kind == 'exec':
            return self.owner_id
        return '%s%s.%d' % (VERIFY_KEY, self.owner_id, self.attempt)


def principal(key):
    """The principal *key* names; anything malformed is refused, never repaired."""
    if str(key).startswith(VERIFY_KEY):
        try:
            vid, n = verify_key_parts(key)
        except ValueError as err:
            raise IsolationUnavailable('profile_name', str(err))
        return Principal('verify', vid, n)
    return Principal('exec', key)


def validated_profile(execution_id):
    """The profile name of a well-formed principal key. Every profile operation goes
    through this, so a name is never taken from a caller, a record or the ledger."""
    return profile_name(principal(execution_id).key)


# ── the §3.4 pre-spawn invariant ─────────────────────────────────────────────
#: the six conditions, in §3.4's order. All six are checked on every isolated spawn;
#: none of them is configurable, and the later-slice boundaries are among them, which
#: is what keeps S1 alone from ever launching a production execution (S1 gate §3).
CONDITIONS = ('identity', 'grants', 'no_broad_grants', 'job', 'mailbox', 'isolated_path')

#: what the §3.1 inventory requires Core to have granted before the process starts.
#: A production request cannot supply all of it yet (the broker row is R3-B's, and
#: the runtime and hook rows name Core's stage, which nothing grants), so it fails
#: closed here.
REQUIRED_GRANTS = ('workspace', 'runtime', 'hook', 'request', 'response', 'sentinel', 'state')

#: a verifier's whole inventory (A6, T-054 §3): its checkout and scratch, which it
#: writes, and Core's staged toolchain, which it runs. Any other row is condition 5's.
VERIFY_GRANTS = (('checkout', 'rw'), ('scratch', 'rw'), ('toolchain', 'rx'))

#: the execution's three mailbox classes (§7.5, R2) as inventory rows, each with the
#: only access it may carry: the execution writes its requests (class 1) and reads
#: Core's answers (class 2) and sentinels (class 3). A class may be split, never merged.
CLASS_ROWS = (('request', 'rw'), ('response', 'rx'), ('sentinel', 'rx'))

#: principals that must never hold a write ACE inside the boundary. Every one of them
#: is a *broad* principal: what it grants reaches users and containers this execution
#: has no business reaching (§3.1, "what it explicitly cannot access").
BROAD_PRINCIPALS = ('S-1-1-0',            # Everyone
                    'S-1-5-11',           # Authenticated Users
                    'S-1-5-32-545',       # Builtin\Users
                    'S-1-15-2-1',          # ALL APPLICATION PACKAGES
                    'S-1-15-2-2')          # RESTRICTED ALL APPLICATION PACKAGES


@dataclass(frozen=True)
class Grant:
    """One entry of the §3.1 inventory as S1 establishes it: a path, an access level,
    and the inventory row it answers (`row`, e.g. 'workspace', 'runtime')."""
    path: str
    access: str                 # 'rx' | 'rw' | 'x'
    row: str = ''


@dataclass(frozen=True)
class IsolationRequest:
    """Everything the invariant needs to point at before an isolated process may
    start. A synthetic fixture supplies each artifact; the production layout does not
    (no broker, and no grant on Core-staged runtime and hook copies), so the same
    check that passes in a fixture fails closed for a production execution."""
    execution_id: str                    # the principal's key (`Principal.key`)
    workspace: str
    grants: tuple = ()                   # (Grant, ...)
    mailbox: str = ''                    # class 1: the execution's own request box
    response: str = ''                   # class 2: Core's answers, execution-readable
    sentinel: str = ''                   # class 3: Core's flags, execution-readable
    spawn_config: str = ''               # class 2: Core-authored, inside `response`
    state_dir: str = ''                  # class 7: per-execution runtime state
    core_state: str = ''                 # class 4–6: Core-owned, must stay ungranted
    core_only: tuple = ()                # further class 4–6 paths, likewise
    broker: str = ''                     # R3-B: who brokers provider access
    isolated_path: bool = True

    def grant_for(self, row):
        return next((g for g in self.grants if g.row == row), None)

    @property
    def kind(self):
        return 'verify' if str(self.execution_id).startswith(VERIFY_KEY) else 'exec'


def _admit(key):
    """A verifier attempt is used once (A6): its consumed marker is created exclusively
    before anything else, and nothing removes it, so a released, reclaimed or
    restarted-over attempt is refused like a running one. A record without a marker
    (written before the marker existed) is refused too."""
    marker = verify_consumed(key)
    if os.path.lexists(isolation_state(key)):
        raise IsolationUnavailable('attempt_consumed', key)
    try:
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, 'x', encoding='utf-8') as f:
            f.write(key + '\n')
    except FileExistsError:
        raise IsolationUnavailable('attempt_consumed', key) from None
    except OSError as err:
        # nothing was created: the attempt is not admitted, and not started
        raise IsolationUnavailable('attempt_unadmitted', '%s: %s' % (key, err)) from None


def _verify_rows(request):
    """Every grant of a verifier checked, never only the first of a row: exactly one
    checkout and one scratch, any number of distinct toolchain paths, each row at
    exactly its access. Returns the problems, empty when the rows hold."""
    access = dict(VERIFY_GRANTS)
    rows = [g.row for g in request.grants]
    out = [row for row in access if row not in rows]
    out += ['%s:%s' % (g.row, g.access) for g in request.grants
            if g.row in access and g.access != access[g.row]]
    out += ['%s:duplicate' % row for row in ('checkout', 'scratch') if rows.count(row) > 1]
    tools = [_norm(g.path) for g in request.grants if g.row == 'toolchain']
    if len(set(tools)) != len(tools):
        out.append('toolchain:duplicate')
    return out


def check_invariant(api, request, identity, job_facts=None):
    """The §3.4 invariant as data: `condition -> (holds, why)`. Unmet conditions are
    returned, never raised, so the caller can record the whole six-condition state —
    the deterministic, restart-reconcilable record O7's decision requires. A boundary
    read that fails (a descriptor, the token) raises `IsolationUnavailable` instead,
    which `establish` records as the failure: an unread answer is never a held one.

    *identity* is what the boundary answered when the profile was created
    (`{'profile', 'sid', 'created', 'package_dir'}`), and *job_facts* what it answers
    about the Job; the checks read answers, never assumptions."""
    out = {}
    sid = (identity or {}).get('sid') or ''

    def put(name, holds, why=''):
        out[name] = (bool(holds), _text('' if holds else why))

    # 1. the execution identity exists (§3.1): the OS created or confirmed it, it has
    # a SID, and that SID is the one its own name derives (spike C1)
    put('identity', identity and identity.get('created') and sid
        and sid == _derive(api, request.execution_id),
        'no profile was created for this execution')

    # 2. the required resource grants are established, workspace included (§3.1, §3.2 A1),
    # and each mailbox class is granted on its own directory with its own access (§7.5)
    boxes = {'request': request.mailbox, 'response': request.response,
             'sentinel': request.sentinel}
    verifier = request.kind == 'verify'
    if verifier:
        # A6: every row at exactly its access, its one checkout the workspace
        missing = _verify_rows(request)
        checkout = request.grant_for('checkout')
        misclassed = [] if checkout and _norm(checkout.path) == _norm(request.workspace) \
            else ['checkout']
        misplaced = 'the checkout is not granted as the workspace: %s'
    else:
        missing = [row for row in REQUIRED_GRANTS if request.grant_for(row) is None]
        misclassed = [row for row, access in CLASS_ROWS if request.grant_for(row) is not None
                      and (_norm(request.grant_for(row).path) != _norm(boxes[row])
                           or request.grant_for(row).access != access)]
        misplaced = 'a mailbox class granted at another path or access: %s'
    absent = [g.path for g in request.grants if not os.path.isdir(g.path)]
    # a descriptor is read only where there is one: a path that is not there already
    # fails this condition by name, and a read that fails raises rather than pass
    present = [g for g in request.grants if os.path.isdir(g.path)]
    unverified = [g.path for g in present if not api.grant_established(g.path, sid, g.access)]
    put('grants', not (missing or misclassed or absent or unverified)
        and bool(request.workspace) and os.path.isdir(request.workspace)
        and (verifier or bool(request.broker)),
        _reason((not missing, 'missing inventory rows: %s' % (missing,)),
                (not misclassed, misplaced % (misclassed,)),
                (not absent, 'granted path that is not present: %s' % (absent,)),
                (not unverified, 'grant unreadable in the DACL: %s' % (unverified,)),
                (bool(request.workspace) and os.path.isdir(request.workspace),
                 'no Core-established workspace (§3.2, A1)'),
                (verifier or bool(request.broker), 'no broker holds provider access (R3-B)')))

    # 3. prohibited broad grants are absent (§3.1)
    broad = [g.path for g in present if api.broad_write_grant(g.path, sid)]
    # Core's own state is not granted, and not planned for a grant either: a plan that
    # names it (the execution's directory as its workspace) never reaches a DACL
    core = [p for p in (request.core_state,) + tuple(request.core_only) if p]
    planned = {_norm(g.path) for g in request.grants}
    leaked = [p for p in core if _norm(p) in planned or api.granted_to(p, sid)]
    caps = [c for c in api.capability_grants() if c]
    put('no_broad_grants', not (broad or leaked or caps),
        _reason((not broad, 'a broad principal holds write: %s' % (broad,)),
                (not leaked, 'Core-owned state is granted to the execution: %s' % (leaked,)),
                (not caps, 'capability SIDs are granted: %s' % (caps,))))

    # 4. the Job object exists (§3.7: unnamed, kill-on-close, not inheritable). Its name
    # reads '' when it has none and None when the lookup failed, which proves nothing
    put('job', job_facts and job_facts.get('type') == 'Job' and job_facts.get('name') == ''
        and not job_facts.get('inheritable'),
        'the execution has no Core-held Job' if not job_facts
        else 'the Job is named, has a name that could not be read, is inheritable, '
             'or is no Job: %s' % (job_facts,))

    # 5. the required Core/mailbox boundary exists (§3.3, §7.5): classes 1, 2 and 3 are
    # three directories, none of them another or inside another or Core's own, none of
    # them is, holds or lies inside the execution's workspace or state (class 7), and
    # the spawn configuration Core wrote is in class 2. A verifier (A6) has the inverse:
    # no mailbox class, spawn configuration, broker or other row named, and Core's own
    # state named and ungranted
    if verifier:
        stray = [g.row for g in request.grants if g.row not in dict(VERIFY_GRANTS)]
        put('mailbox', not (stray or any(boxes.values()) or request.spawn_config
                            or request.broker)
            and bool(request.core_state) and not any(api.granted_to(p, sid) for p in core),
            'a verifier is given an execution interface (a mailbox class, a spawn '
            'configuration, a broker or rows %s), or Core-owned state is unnamed or '
            'granted' % (stray,))
    else:
        put('mailbox', all(boxes.values()) and bool(request.spawn_config)
            and bool(request.core_state)
            and all(os.path.isdir(p) for p in boxes.values())
            and _separate(boxes.values(), (request.workspace, request.state_dir))
            and not {_norm(p) for p in boxes.values()} & {_norm(p) for p in core}
            and os.path.isfile(request.spawn_config)
            and _norm(os.path.dirname(request.spawn_config)) == _norm(request.response)
            and not any(api.granted_to(p, sid) for p in core),
            'no separate class 1, 2 and 3 directories apart from the workspace and state, '
            'with the Core-authored spawn configuration in class 2, or Core-owned state is '
            'unnamed or sits inside the boundary')

    # 6. the isolated spawn path is selected (§3.4)
    put('isolated_path', bool(request.isolated_path) and api.available(),
        _reason((bool(request.isolated_path), 'the detached path was selected'),
                (api.available(), 'the OS boundary is unavailable')))
    return out


def _reason(*parts):
    """The reason of the first failing part, each part a `(holds, why)` pair."""
    return next((why for holds, why in parts if not holds), '')


def _text(s):
    return s if isinstance(s, str) else str(s)


def _norm(path):
    return os.path.normcase(os.path.abspath(path)) if path else ''


def _within(a, b):
    """Is *a* the directory *b*, or inside it?"""
    a, b = _norm(a), _norm(b)
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def _separate(paths, apart=()):
    """No two of *paths* are one directory or lie one inside the other, and none of
    them is, holds or lies inside any of *apart* — which are not judged among
    themselves (a workspace may hold its own state)."""
    paths = list(paths)
    return not (any(_within(a, b) for i, a in enumerate(paths)
                    for j, b in enumerate(paths) if i != j)
                or any(_within(a, o) or _within(o, a) for a in paths for o in apart if o))


def _derive(api, execution_id):
    """The SID the identity's name derives to, or None. The identity is what its name
    says it is: a name whose SID differs is a different principal (spike C1)."""
    try:
        return api.derive_sid(execution_id)
    except IsolationUnavailable:
        return None


def unmet_conditions(conditions):
    return tuple(name for name in CONDITIONS if not conditions.get(name, (False, ''))[0])


# ── A4 (§3.8, H-1): built, not enforced ──────────────────────────────────────
#: the six eligibility conditions of A4. Unknown or missing facts are NOT eligible:
#: the check fails closed, so a harness never runs production-dispatched on a fact
#: nobody established.
A4_CONDITIONS = ('production_dispatch', 'pv20_identity', 'core_held_job',
                 'sandbox_inner_layer', 'no_harness_exception', 'evidence_from_path')
A4_ENFORCED = False                      # enforcement is the owner's (slice E)


def a4_enforced():
    """Whether A4 gates dispatch. It does not yet (S1 gate §7.5.9); nothing on the
    dispatch path may call `a4_eligibility` while this is False."""
    return bool(A4_ENFORCED)


def a4_eligibility(*, harness_id, isolated_launch=None, job_held=None, sandbox=None,
                   exception_claimed=None, evidence=None):
    """Is *harness_id* eligible for production dispatch under PV-20? Built, not
    enforced (see `a4_enforced`). Six conditions, each of which must be a fact:

    `production_dispatch`  a fake or test harness is never production-dispatchable,
                           and a real harness is only eligible while it launches
                           inside PV-20 at all (§3.8's table);
    `pv20_identity`        it launches inside the execution identity;
    `pv20_job`             its process runs inside the Core-held Job;
    `sandbox_inner_layer`  its own sandbox, if it has one, is an inner layer, never a
                           substitute for the boundary;
    `no_harness_exception` nobody holds an exception (none exists);
    `evidence_from_path`   every PV-20 property claimed for it is claimed on evidence
                           taken from that path.
    """
    unmet = []
    if not harness_id or is_test_harness_id(harness_id):
        unmet.append('production_dispatch')
    if isolated_launch is not True:
        unmet.append('pv20_identity')
    if job_held is not True:
        unmet.append('core_held_job')
    if sandbox is not False and sandbox is not True:
        unmet.append('sandbox_inner_layer')      # unknown: nobody established it
    if exception_claimed is not False:
        unmet.append('no_harness_exception')
    if not evidence:
        unmet.append('evidence_from_path')
    return (not unmet, tuple(unmet))


def is_test_harness(adapter):
    """§3.8: fake and test harnesses. They may verify the mechanics and are never
    production-dispatchable, so they are also the only things S1 dispatches isolated."""
    return is_test_harness_id(getattr(adapter, 'id', None)) or bool(
        getattr(adapter, 'test_harness', False))


def is_test_harness_id(harness_id):
    return str(harness_id or '').startswith(('fake', 'test'))


# ── the process identity, the Job and the grants: Core's side of the boundary ──

@dataclass
class IsolationRecord:
    """Core's own record of one execution's isolation (`run/isolation/<id>.json`).
    Core writes it and only Core reads it as authority — it is deliberately outside
    the execution's directory, where anything an execution wrote would be (§3.3).

    `planned` is the §3.1 inventory the plan asked for, kept as evidence; `applied` is
    access Core actually put in place. S1 applies none (grant application is outside
    it), so `applied` is always empty and `planned` is never an input to cleanup.

    `owned` records that the OS answered Core's create with a profile it had just
    made, saved before anything else can fail; only an owned profile is ever deleted.
    A record without it (a crash before the answer was saved) cannot tell Core's profile
    from one Core never made, so that profile is kept. Like every field here it is
    writable by the same user: it is evidence of what Core saw, not an authentication.

    `preexisting` marks a profile that was already standing under this execution's
    name when Core asked to create it, and that Core refused to adopt: Core did not
    create it, so nothing here ever deletes it. `attempts` counts failed cleanups.

    `invalid` is never written: it is how a record that exists but cannot be trusted
    is read back (`Isolation.record`)."""
    execution_id: str
    profile: str
    sid: str = ''
    state: str = 'pending'    # pending | established | failed | torn_down | quarantined | invalid
    reason: str = ''
    failure: str = ''         # why establishment failed; cleanup never overwrites it
    conditions: dict = field(default_factory=dict)
    planned: tuple = ()
    applied: tuple = ()
    pid: int = None
    create_time: object = None
    capabilities: tuple = CAPABILITIES
    owned: bool = False
    preexisting: bool = False
    attempts: int = 0
    at: float = 0.0
    updated: float = 0.0

    def as_dict(self):
        return {'execution_id': self.execution_id, 'profile': self.profile, 'sid': self.sid,
                'state': self.state, 'reason': self.reason, 'failure': self.failure,
                'conditions': self.conditions,
                'planned': _row_dicts(self.planned), 'applied': _row_dicts(self.applied),
                'pid': self.pid, 'create_time': self.create_time,
                'capabilities': list(self.capabilities), 'owned': self.owned,
                'preexisting': self.preexisting, 'attempts': self.attempts, 'at': self.at,
                'updated': self.updated}


def _row_dicts(rows):
    return [{'path': g.path, 'access': g.access, 'row': g.row} for g in rows]


def _rows(dicts):
    return tuple(Grant(g['path'], g['access'], g['row']) for g in dicts or ())


# ── persisted state is checked against what the execution id derives ─────────
RECORD_STATES = ('pending', 'established', 'failed', 'torn_down', 'quarantined')
#: an established identity always carries its SID; in the others it may never have
#: been confirmed (pending, a failed create) or has already gone (torn_down)
SIDLESS_STATES = ('pending', 'failed', 'torn_down', 'quarantined')
#: every field is a scalar or a flat container, so nothing nested survives the check
#: to be written back (a structure deep enough to load can be too deep to dump)
_RECORD_TYPES = {'execution_id': str, 'profile': str, 'sid': str, 'state': str,
                 'reason': str, 'failure': str, 'conditions': dict, 'planned': list,
                 'applied': list,
                 'pid': (int, type(None)), 'create_time': (int, float, type(None)),
                 'capabilities': list, 'owned': bool, 'preexisting': bool, 'attempts': int,
                 'at': (int, float), 'updated': (int, float)}
_LEDGER_TYPES = {'op': str, 'execution_id': str, 'profile': str, 'sid': str,
                 'planned': list, 'reason': str, 'at': (int, float)}


def _shape_problem(d, types):
    if not isinstance(d, dict):
        return 'not_an_object'
    extra = sorted(set(d) - set(types))
    if extra:
        return 'unknown_fields:%s' % ','.join(map(str, extra))
    bad = sorted(k for k, t in types.items() if k in d and not isinstance(d[k], t))
    return 'malformed:%s' % ','.join(bad) if bad else ''


def _identity_problem(execution_id, d, api, sidless_ok):
    """Does *d* name exactly the identity *execution_id* derives? A profile is compared
    with the derived name and a SID with the derived SID; neither is believed."""
    if d.get('profile') != profile_name(execution_id):
        return 'profile_mismatch'
    if not all(isinstance(g, dict) and set(g) == {'path', 'access', 'row'}
               and all(isinstance(v, str) for v in g.values()) for g in d.get('planned', ())):
        return 'planned_malformed'
    sid = d.get('sid', '')
    if not sid:
        return '' if sidless_ok else 'sid_missing'
    try:
        return '' if sid == api.derive_sid(execution_id) else 'sid_mismatch'
    except IsolationUnavailable:
        return 'sid_underivable'


def _record_problem(d, execution_id, api):
    """Why persisted record *d* cannot be trusted as *execution_id*'s, or ''."""
    problem = _shape_problem(d, _RECORD_TYPES)
    if problem:
        return problem
    if d.get('execution_id') != execution_id:
        return 'execution_id_mismatch'
    if d.get('state') not in RECORD_STATES:
        return 'state_unknown'
    if d.get('applied'):
        return 'applied_access'                  # S1 applies none
    if d.get('capabilities'):
        return 'capabilities'                    # §4.9: the identity holds none
    if not all(isinstance(v, list) and len(v) == 2 and isinstance(v[0], bool)
               and isinstance(v[1], str) for v in d.get('conditions', {}).values()):
        return 'conditions_malformed'
    if d.get('preexisting') and d['state'] != 'failed':
        return 'preexisting_state'               # a refused profile is only ever a failure
    if d.get('preexisting') and d.get('owned'):
        return 'ownership_conflict'
    return _identity_problem(execution_id, d, api, d['state'] in SIDLESS_STATES)


def _ledger_problem(e, api):
    """Why quarantine-ledger line *e* cannot be trusted, or ''."""
    problem = _shape_problem(e, _LEDGER_TYPES)
    if problem:
        return problem
    if e.get('op') not in ('quarantine', 'released'):
        return 'op_unknown'
    try:
        principal(e.get('execution_id'))
    except IsolationUnavailable:
        return 'execution_id_invalid'
    if e['op'] == 'released':
        return ''
    return _identity_problem(e['execution_id'], e, api, True)


#: how long a profile's deletion waits for the root process once Core has closed its Job
EXIT_WAIT_S = 2.0
#: how often the fence reads a Job's active-process count while it waits (K3)
FENCE_POLL_S = 0.05
#: the fence's clock and sleep: a test moves them, never the code
_clock, _sleep = time.monotonic, time.sleep

#: a confined verifier run's limits (A6-3, T-054 C-1013 §3). They are soft DETECTION:
#: Core polls, so between two polls a writer is bounded only by its own rate, and no
#: hard bound on bytes written is claimed
CONFINED_OUT_MAX = 64 << 20         # out.log
CONFINED_GROWTH_MAX = 2 << 30       # checkout and scratch growth over the start
CONFINED_POLL_S = 1.0
CONFINED_WALK_MAX = 200000          # entries per accounting walk


class Isolation:
    """Core's isolation authority for one process: the per-execution identities, the
    Jobs only Core holds, the quarantine ledger and the boot reclaim.

    The Job table lives here and nowhere else: the handle is never named, never made
    inheritable and never handed to another process, which is what makes Core its sole
    holder (R6-A) and the Job the execution's lifetime authority (§3.7)."""

    def __init__(self, node=None, *, boundary=None, authorize=None, plan=None):
        self.node = node
        self._boundary = boundary
        #: who Core authorized to run isolated. Production is E's, so this only ever
        #: reaches a test harness while `PRODUCTION_DISPATCH_ENABLED` is False.
        self._authorize = authorize
        #: the §3.1 grant inventory of one execution, as Core establishes it. The
        #: synthetic fixtures replace it; the default is the production layout, which
        #: cannot satisfy the invariant on its own (see `default_plan`).
        self._plan = plan
        self._jobs = {}                     # execution_id -> job handle (Core's only reference)
        self._live = {}                     # execution_id -> the process launched into the Job
        #: persisted records and ledger lines this Core found untrustworthy: key -> why.
        #: Each is noted in the registry once and otherwise left exactly as found.
        self.invalid = {}
        #: executions whose last sweep failed on a write of their own: id -> the error.
        #: Noted once per distinct error, cleared once the execution is handled again.
        self.faults = {}
        #: executions whose `released` line this Core has seen confirmed: profile absent
        self._released = set()
        #: verifier attempts this Core is running now: live whatever a caller says (A6-3)
        self._confined = set()
        self._admitted = set()        # verifier keys this Core admitted, not yet established

    # ── the boundary ──

    @property
    def boundary(self):
        if self._boundary is None:
            self._boundary = WindowsBoundary() if WINDOWS else UnavailableBoundary()
        return self._boundary

    def set_boundary(self, boundary):
        self._boundary = boundary

    # ── the decision ──

    def requested(self, execution_id, adapter=None):
        """Must this execution run isolated? Once an execution is isolated it stays
        isolated — its resumes reuse its identity (R7). Otherwise it is isolated only
        where Core authorized it, and never for a real harness while production
        dispatch is E's (§3.8, ADR-0053 §3.4)."""
        if self.record(execution_id) is not None:
            return True
        if self._authorize is None or not self._authorize(execution_id, adapter):
            return False
        if not production_dispatch_enabled() and not is_test_harness(adapter):
            return False
        return True

    # ── the record ──

    def record(self, execution_id):
        """The execution's record, checked against what its id derives, or None when it
        has none. A record that exists and cannot be trusted comes back as state
        `invalid` with only its derived identity, so the execution still counts as
        isolated (never a reason to run it unisolated) and nothing acts on what the
        file says."""
        path = isolation_state(execution_id)          # a malformed id is a caller's bug
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, RecursionError):  # RecursionError: nested too deep
            d, problem = None, 'unreadable'
        else:
            problem = _record_problem(d, execution_id, self.boundary)
        if problem:
            self._report_invalid(execution_id, problem)
            return IsolationRecord(execution_id=execution_id,
                                   profile=profile_name(execution_id), state='invalid',
                                   reason=problem)
        return IsolationRecord(
            execution_id=execution_id, profile=d['profile'], sid=d.get('sid', ''),
            state=d['state'], reason=d.get('reason', ''), failure=d.get('failure', ''),
            conditions=d.get('conditions', {}),
            planned=_rows(d.get('planned')), pid=d.get('pid'),
            create_time=d.get('create_time'), owned=d.get('owned', False),
            preexisting=d.get('preexisting', False),
            attempts=d.get('attempts', 0), at=d.get('at', 0.0), updated=d.get('updated', 0.0))

    def _report_invalid(self, key, problem):
        if self.invalid.get(key) == problem:
            return
        self.invalid[key] = problem
        self._note({'op': 'isolation_invalid', 'key': key, 'reason': problem})

    def _save(self, rec):
        if rec.state == 'invalid' or rec.applied:
            # an untrusted record is evidence and is never overwritten; S1 applies no
            # access, so a record claiming some is a bug, not a state
            raise ValueError('refusing to write the isolation record of %s (state %s, '
                             'applied %r)' % (rec.execution_id, rec.state, rec.applied))
        rec.updated = time.time()
        rec.at = rec.at or rec.updated
        path = isolation_state(rec.execution_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not config.write_json_atomic(path, rec.as_dict(),
                                        indent=None):
            raise OSError('could not write the isolation record of %s' % rec.execution_id)
        return rec

    def _note(self, line):
        """The registry is the instrument (item 83), never the authority: an isolated
        spawn and an isolation-establishment failure both leave a line here so that a
        later Core can tell which is which (§3.7, O7's reconcilable state)."""
        if self.node is not None:
            self.node._registry(dict(line, at=time.time()))

    # ── the isolated spawn path (§3.4) ──

    def request(self, execution_id, *, workspace, grants, mailbox='', response='',
                sentinel='', spawn_config='', state_dir='', core_state='', core_only=(),
                broker=''):
        """The opaque object `base.spawn` uses instead of the detached launcher
        (§3.4: "a new spawn mechanism behind the existing seam")."""
        return IsolationContext(
            self, IsolationRequest(execution_id=execution_id, workspace=workspace,
                                   grants=tuple(grants), mailbox=mailbox,
                                   response=response, sentinel=sentinel,
                                   spawn_config=spawn_config, state_dir=state_dir,
                                   core_state=core_state, core_only=tuple(core_only),
                                   broker=broker))

    def request_for(self, spec):
        """The isolated launch of one execution's process, planned from the spec. The
        plan is Core's (§3.1: the grants are established, not requested)."""
        r = (self._plan or default_plan)(spec)
        return self.request(spec.execution_id, workspace=r.workspace, grants=r.grants,
                            mailbox=r.mailbox, response=r.response, sentinel=r.sentinel,
                            spawn_config=r.spawn_config, state_dir=r.state_dir,
                            core_state=r.core_state, core_only=r.core_only,
                            broker=r.broker)

    def note_failure(self, spec, err):
        """The registry's word for a spawn that never happened (§3.7, O7's
        reconcilable state): an isolated execution's failure is recorded as
        `isolation_failed` with its reason, so the record, the tombstone and the
        registry agree on it across a restart. A non-isolated spawn is untouched."""
        if getattr(spec, 'isolation', None) is None:
            return
        try:
            rec = self.record(spec.execution_id)
            if rec is None or rec.state not in ('failed', 'quarantined'):
                self._note({'op': 'isolation_failed', 'execution_id': spec.execution_id,
                            'state': 'isolation_failed',
                            'reason': (rec.reason if rec else 'unknown') or str(err)})
        except OSError:
            # the registry is the instrument (item 83): a line it cannot take never
            # replaces the spawn failure the caller raises next, and the record holds it
            pass

    def establish(self, request, paths=None):
        """The §3.4 invariant, established: identity, grants, Job. Raises
        `IsolationUnavailable` when any of the six conditions does not hold, and
        records which ones did not. A write that fails (`OSError`: the record, a
        quarantine line, a registry note) is an establishment failure like any other:
        nothing starts, and what is on disk decides what cleanup may do."""
        api = self.boundary
        if request.kind == 'verify':
            if request.execution_id in self._admitted:
                self._admitted.discard(request.execution_id)     # admitted by run_confined
            else:
                _admit(request.execution_id)
        prior = self.record(request.execution_id)
        if prior is not None and prior.state == 'invalid':
            # a record exists and cannot be trusted: nothing is created for this
            # execution and the record is left as found, because it is the evidence
            raise IsolationUnavailable('record_invalid', prior.reason)
        if prior is not None and prior.preexisting:
            # the profile under this name is not Core's: it is never adopted, and the
            # record that says so is kept exactly as it is for review
            raise IsolationUnavailable('profile_preexisting',
                                       '%s was not created by Core' % prior.profile)
        if prior is not None and (prior.state not in ('pending', 'established')
                                  or prior.failure):
            # failed, quarantined or torn down: the record is cleanup's evidence and the
            # sweep's work, never a new start. Refused before any write, so the record,
            # the ledger and the profile stay exactly as found. `established` is a
            # PAUSED resume and `pending` the retry of one that died (Finding 1)
            raise IsolationUnavailable('record_unsettled', '%s: %s' % (
                prior.state, prior.failure or prior.reason))
        rec = prior or IsolationRecord(execution_id=request.execution_id,
                                       profile=profile_name(request.execution_id))
        try:
            return self._establish(api, rec, request, paths)
        except OSError as err:
            return self._fail(rec, 'os_error', str(err), paths)

    def _establish(self, api, rec, request, paths):
        if not api.available():
            return self._fail(rec, 'platform', 'this platform has no AppContainer boundary',
                              paths)
        # The OS identity is created before anything on disk proves it exists. A hard
        # Core crash in that interval would orphan a profile that `reclaim()` cannot
        # see, because reclaim discovers outstanding work by reading these records
        # (§3.2 Cleanup, §3.7). Persist the record first, pending, so the identity is
        # always recoverable. A pending record is not proof that Core made a profile:
        # only `owned` is, so a record without it never leads to a deletion. An owned
        # record keeps its ownership and SID through the reset, so a resume (or a retry
        # after a crash) is never refused its own profile.
        rec.state, rec.planned = 'pending', ()
        if not rec.owned:
            rec.sid = ''
        self._save(rec)
        try:
            identity = api.create_profile(rec.execution_id)
        except IsolationUnavailable as err:
            return self._fail(rec, err.reason, err.detail, paths)
        sid = identity.get('sid') or ''
        if identity.get('existed') and not (rec.owned and rec.sid and rec.sid == sid):
            # only this execution's own recorded profile is reused. Anything else
            # already standing under its name was not created by Core, so it is neither
            # adopted nor deleted: the name and SID are both derivable and prove nothing
            # about who made it
            rec.sid, rec.owned, rec.preexisting = sid, False, True
            return self._fail(rec, 'profile_preexisting',
                              'no record that Core created %s' % rec.profile, paths)
        # the OS's answer, on disk before the Job, the invariant or anything else can fail
        rec.sid, rec.owned = sid, True
        try:
            self._save(rec)
        except OSError:
            rec.owned = False     # not on disk, so not evidence: nothing deletes on it
            raise
        try:
            job = self._ensure_job(request.execution_id)
            facts = api.job_facts(job)
            # a boundary read that fails (the token, a DACL) is an establishment
            # failure like any other: recorded, and the identity released
            conditions = check_invariant(api, request, identity, facts)
        except IsolationUnavailable as err:
            return self._fail(rec, err.reason, err.detail, paths)
        rec.conditions = {k: list(v) for k, v in conditions.items()}
        # what the plan asked for, kept as evidence. S1 applies none of it, so it is
        # never an input to cleanup (it once was, and named the real Python install)
        rec.planned = request.grants
        unmet = unmet_conditions(conditions)
        if unmet:
            return self._fail(rec, 'condition_unmet:' + ','.join(unmet),
                              '; '.join('%s: %s' % (n, conditions[n][1]) for n in unmet), paths)
        rec.state = 'established'
        rec.reason = ''
        rec.capabilities = CAPABILITIES
        self._save(rec)
        return rec

    def _fail(self, rec, reason, detail, paths=None):
        """No process starts, and the state says so deterministically: the record, the
        registry line and the `ended` tombstone all carry the same reason, so a
        restarted Core reads the same thing this Core knew (O7, §3.7).

        Each of those writes, and the release, is tried on its own: one that fails
        (`OSError`) is added to the detail and never replaces *reason*, which is what is
        raised. The record left on disk is what the end path and the sweep finish from,
        and `rec.owned` is only ever true once it is on disk, so the release here
        deletes nothing the record does not say is Core's."""
        rec.state, rec.reason, rec.failure = 'failed', reason, reason
        unwritten = []

        def attempt(step, *args, **kw):
            try:
                step(*args, **kw)
            except OSError as err:
                unwritten.append(str(err))

        attempt(self._save, rec)
        attempt(self._note, {'op': 'isolation_failed', 'execution_id': rec.execution_id,
                             'profile': rec.profile, 'state': 'isolation_failed',
                             'reason': reason, 'conditions': rec.conditions})
        if paths is not None and not os.path.exists(paths.ended):
            attempt(base.mark_ended, paths, None, error='isolation: %s' % reason,
                    isolation_state='failed', isolation_reason=reason, isolation_detail=detail)
        attempt(self._release_best_effort, rec)
        if unwritten:
            note = 'cleanup incomplete: %s' % ' | '.join(unwritten)
            detail = '%s; %s' % (detail, note) if detail else note
        raise IsolationUnavailable(reason, detail)

    def _ensure_job(self, execution_id):
        """The execution's Job, created once and held only here (§3.7, R6-A)."""
        api = self.boundary
        job = self._jobs.get(execution_id)
        if job is None:
            job = api.create_job(execution_id)
            self._jobs[execution_id] = job
        return job

    def held_job(self, execution_id):
        """The Job handle Core holds for an execution, or None. Used by the verifier
        and by the sole-holder evidence; never handed to another process."""
        return self._jobs.get(execution_id)

    def held_jobs(self):
        return dict(self._jobs)

    def fence(self, execution_id, *, wait=EXIT_WAIT_S):
        """Quiescence before an import (C-1012-T030-2 §1): the Job's active-process
        count, read through the handle Core still holds and polled for up to *wait*
        seconds, then the Job closed whatever the answer. None when the count reached
        zero; otherwise why not: no Job held (every end after a restart), a query that
        fails or answers anything but a count, or members left at the bound. Zero shows
        only that the Job is empty, never that no writer outside it exists (T-008)."""
        job = self._jobs.get(execution_id)
        if job is None:
            return 'no Job is held for it'
        end, why = _clock() + wait, None
        try:
            while True:
                try:
                    n = self.boundary.job_active_processes(job)
                except Exception as err:
                    why = 'its Job could not be queried: %s' % type(err).__name__
                    break
                if type(n) is not int or n < 0:
                    why = 'its Job answered %r, not a process count' % (n,)
                    break
                if n == 0:
                    break
                if _clock() >= end:
                    why = '%d process(es) still in its Job after %gs' % (n, wait)
                    break
                _sleep(FENCE_POLL_S)
        finally:
            self._close_job(execution_id)       # kill-on-close: a survivor ends here
        return why

    def launched(self, execution_id):
        return self._live.get(execution_id)

    def assign(self, execution_id, process_handle):
        """Into the Job, before it runs (§3.4: created suspended, assigned, resumed)."""
        self.boundary.assign_job(self._ensure_job(execution_id), process_handle)

    # ── teardown, quarantine, reclaim (items 4, 5, 6) ──

    def teardown(self, execution_id, *, reason=''):
        """The identity deleted (§3.2 Cleanup); S1 applies no access, so nothing is
        revoked. Safe to call for an execution that never had one, and safe to call
        twice. The record goes only once the profile has been seen gone; a profile that
        will not go, or whose process may still run (`busy`), is quarantined with its
        record kept, and an untrusted record, like a profile Core refused to adopt, is
        left as found. Only a profile the record says Core created is deleted (see
        `_unowned` for the rest)."""
        rec = self.record(execution_id)
        out = {'execution_id': execution_id, 'reason': reason, 'job': 'none',
               'profile': 'none'}
        if rec is None and execution_id not in self._jobs:
            return None
        closed = self._close_job(execution_id)
        if closed:
            out['job'] = 'closed'
        if rec is None:
            return out
        if rec.state == 'invalid':
            out['profile'] = 'invalid_record'
            return out
        # the Job's close killed the tree; its root gets a bounded moment to go before
        # the profile does, which an in-use profile cannot survive (spike C9)
        out['profile'] = self._delete_profile(rec, reason=reason,
                                              wait=EXIT_WAIT_S if closed else 0)
        return out

    def _close_job(self, execution_id):
        job = self._jobs.pop(execution_id, None)
        if job is None:
            return False
        self.boundary.close_job(job)             # kill-on-close: the tree dies here
        return True

    def _delete_profile(self, rec, *, reason, wait=0):
        if rec.preexisting:
            return 'preexisting'                # not Core's: the record stays as evidence
        if rec.state == 'torn_down' and not rec.sid:
            return 'none'
        if not rec.owned:
            return self._unowned(rec)
        outcome = self._remove_profile(rec, wait)
        if outcome != 'torn_down':
            return outcome
        rec.state, rec.reason = 'torn_down', reason
        rec.sid = ''
        self._save(rec)
        self._remove_record(rec.execution_id)
        return 'torn_down'

    def _remove_profile(self, rec, wait):
        """The one way an owned profile is deleted, on every route: only once the
        process launched under it is gone, and released only once the boundary answers
        that the profile is gone — a delete reported done, or "not found", is a claim
        until then. Returns `torn_down` for that confirmed release; otherwise
        the record is quarantined with its SID, under a reason that says which of these
        failed, and `busy` or `quarantined` comes back for the sweep to retry."""
        process = self._process_state(rec, wait)
        if process != 'gone':
            self.quarantine(rec, 'process_alive' if process == 'alive' else 'process_unverified')
            return 'busy'
        try:
            self.boundary.delete_profile(rec.execution_id)
        except IsolationUnavailable as err:
            self.quarantine(rec, '%s: %s' % (err.reason, err.detail))
            return 'quarantined'
        presence = self._presence(rec.execution_id)
        if presence != 'absent':
            self.quarantine(rec, 'profile_delete_unverified' if presence == 'present'
                            else 'profile_presence_unknown')
            return 'quarantined'
        self._live.pop(rec.execution_id, None)
        return 'torn_down'

    def _process_state(self, rec, wait):
        """`gone`, `alive` or `unknown` for the process last launched under *rec*'s
        identity, waiting up to *wait* seconds for it to go. Core's own handle answers
        when Core holds one. Otherwise the recorded PID counts only with its recorded
        creation time: another process under that PID means the recorded one is gone,
        and a creation time that was never recorded or cannot be read proves nothing.
        This is the root process alone; its descendants end with the Job (kill-on-close),
        which every caller closes first, and are not looked at one by one."""
        child = self._live.get(rec.execution_id)
        if child is not None:
            return 'alive' if child.wait(wait) is None else 'gone'
        if rec.pid is None:
            return 'gone'                       # no process was ever recorded
        deadline = time.monotonic() + wait
        while True:
            try:
                started = self.boundary.process_started(rec.pid)
            except IsolationUnavailable:
                state = 'unknown'
            else:
                if started is None or (rec.create_time is not None
                                       and started != rec.create_time):
                    return 'gone'
                state = 'alive' if rec.create_time is not None else 'unknown'
            if time.monotonic() >= deadline:
                return state
            time.sleep(0.05)

    def _presence(self, execution_id):
        """`absent`, `present` or `unknown`: only an explicit False from the boundary is
        absence, so a read that fails, or answers anything else, never is."""
        try:
            present = self.boundary.profile_exists(execution_id)
        except IsolationUnavailable:
            return 'unknown'
        return 'absent' if present is False else 'present' if present is True else 'unknown'

    def _unowned(self, rec):
        """A profile nothing says Core created — the answer to its create never reached
        the record, or the only trace is a ledger line — is never deleted: it may be
        somebody else's. Absent, the record is finished with; standing, or in a state
        that cannot be read, it is kept as evidence with the SID its name derives,
        failed as `provenance_unknown`, and every later pass leaves it as it is."""
        if self._presence(rec.execution_id) == 'absent':
            self._remove_record(rec.execution_id)
            return 'torn_down'
        if rec.state != 'failed' or rec.reason != 'provenance_unknown':
            rec.state, rec.reason = 'failed', 'provenance_unknown'
            rec.sid = rec.sid or _derive(self.boundary, rec.execution_id) or ''
            self._save(rec)
            self._note({'op': 'isolation_provenance_unknown', 'execution_id': rec.execution_id,
                        'profile': rec.profile})
        return 'provenance_unknown'

    def _remove_record(self, execution_id):
        try:
            os.remove(isolation_state(execution_id))
        except OSError:
            pass

    def _release_best_effort(self, rec):
        """An establishment failure must not leave the identity standing: its profile
        is deleted, and quarantined if it will not go, may still hold a process, or
        cannot be seen gone. The record stays `failed` (O7's reconcilable state) for the
        sweep to finish. Nothing was applied, so nothing is revoked, and nothing is
        quarantined when there is no boundary at all. Only a profile the record says
        Core created is Core's to delete."""
        closed = self._close_job(rec.execution_id)
        if not self.boundary.available() or not rec.owned or rec.preexisting:
            return
        self._remove_profile(rec, EXIT_WAIT_S if closed else 0)

    # ── the quarantine ledger (§3.7) ──

    def quarantine(self, rec, reason):
        """A profile Core could not remove. Its record is kept, with the SID that names
        whatever the identity was ever given, and the boot retry keeps trying. It is
        never re-granted: the principal is this execution's and dies with it (R7).

        The ledger and the registry hear of a quarantine when it begins or its reason
        changes, never once per retry (the sweep retries every pass); the record
        carries the retry count and the last failure, and `updated` its time."""
        changed = rec.state != 'quarantined' or rec.reason != reason
        rec.state, rec.reason = 'quarantined', reason
        rec.attempts += 1
        self._save(rec)
        if not changed:
            return
        entry = {'op': 'quarantine', 'execution_id': rec.execution_id,
                 'profile': profile_name(rec.execution_id), 'sid': rec.sid,
                 'planned': _row_dicts(rec.planned), 'reason': reason, 'at': time.time()}
        os.makedirs(isolation_dir(), exist_ok=True)
        with open(quarantine_log(), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, sort_keys=True) + '\n')
        self._note({'op': 'quarantine', 'execution_id': rec.execution_id,
                    'profile': rec.profile, 'reason': reason})

    def quarantined(self):
        """The ledger's un-released entries, newest wins."""
        return {k: e for k, (_, e) in self._ledger().items() if e['op'] == 'quarantine'}

    def _ledger(self):
        """The newest valid ledger line of each execution, with its line number. A line
        that is not a valid entry for the identity its execution id derives is reported
        and skipped."""
        try:
            with open(quarantine_log(), encoding='utf-8', errors='replace') as f:
                raw = f.read().splitlines()
        except FileNotFoundError:
            return {}
        out = {}
        for n, line in enumerate(raw, 1):
            try:
                e = json.loads(line)
            except (ValueError, RecursionError):        # RecursionError: nested too deep
                e = None
            problem = _ledger_problem(e, self.boundary)
            if problem:
                self._report_invalid('quarantine.jsonl:%d' % n, problem)
            else:
                out[e['execution_id']] = (n, e)
        return out

    def release(self, execution_id):
        os.makedirs(isolation_dir(), exist_ok=True)
        with open(quarantine_log(), 'a', encoding='utf-8') as f:
            f.write(json.dumps({'op': 'released', 'execution_id': execution_id,
                                'at': time.time()}, sort_keys=True) + '\n')

    def reclaim(self, live_execution_ids=()):
        """Boot and every pass (§3.2 Cleanup, §3.7): quarantine retried, and every
        identity belonging to an execution that is not live is torn down. Returns the
        executions whose identity is now gone; a quarantine that still will not go,
        and an untrusted record or ledger line, stay where they are and are not in it.
        Nothing here changes an ACL: S1 applies none.

        `released` is appended only for a profile seen gone, and a `released` line is
        believed only while it is: a record of a later lifecycle governs instead, and a
        line the profile's state contradicts is reported once and kept as written.

        Each execution is handled on its own. A write of its own that fails — its record
        or ledger line, or the registry note about it — raises `OSError`, which makes it
        this execution's fault: noted once per distinct error, retried next pass, and
        the executions after it are still handled. Nothing else is caught: any other
        error is a bug, and a ledger that cannot be read, a record directory that cannot
        be listed, or a registry that cannot take the fault's own note fails the whole
        sweep, for the manager to report."""
        live = set(live_execution_ids or ()) | self._confined
        done, seen = [], set()
        for execution_id, (n, entry) in sorted(self._ledger().items()):
            if execution_id in live:
                continue
            if entry['op'] == 'released' and (
                    execution_id in self._released
                    or os.path.lexists(isolation_state(execution_id))):
                continue                        # settled, or a later record governs
            seen.add(execution_id)              # one attempt per execution per pass
            if self._contained(execution_id, self._reclaim_entry, execution_id, n, entry):
                done.append(execution_id)
        for execution_id in sorted(set(self.stale(live)) - seen):
            if self._contained(execution_id, self._reclaim_stale, execution_id):
                done.append(execution_id)
        return done

    def _contained(self, execution_id, step, *args):
        try:
            gone = step(*args)
        except OSError as err:
            if self.faults.get(execution_id) != str(err):
                self.faults[execution_id] = str(err)
                self._note({'op': 'isolation_fault', 'execution_id': execution_id,
                            'reason': str(err)})
            return False
        self.faults.pop(execution_id, None)
        return gone

    def _reclaim_entry(self, execution_id, n, entry):
        if entry['op'] == 'released':
            presence = self._presence(execution_id)
            if presence == 'absent':
                self._released.add(execution_id)
                return False
            # the line says the profile went, and it has not been seen gone: the line is
            # kept as written and reported, and the profile — nothing here says Core made
            # it — is kept as evidence like any other it cannot account for
            self._report_invalid('quarantine.jsonl:%d' % n, 'released_but_' + presence)
            self._unowned(IsolationRecord(execution_id=execution_id,
                                          profile=profile_name(execution_id)))
            return False
        closed = self._close_job(execution_id)  # what teardown would have done first
        rec = self.record(execution_id) or IsolationRecord(
            execution_id=execution_id, profile=profile_name(execution_id),
            sid=entry.get('sid', ''), state='quarantined',
            reason=entry.get('reason', ''), planned=_rows(entry.get('planned')))
        if rec.state == 'invalid':
            return False                        # reported by record(); left as found
        if self._delete_profile(rec, reason='reclaimed',
                                wait=EXIT_WAIT_S if closed else 0) != 'torn_down':
            return False
        self.release(execution_id)
        self._released.add(execution_id)
        return True

    def _reclaim_stale(self, execution_id):
        out = self.teardown(execution_id, reason='stale')
        return bool(out) and out['profile'] == 'torn_down'

    def stale(self, live_execution_ids=()):
        """Isolation records whose principal is not live, executions' and verifier
        attempts' alike. A file whose name is not a principal's is reported, never acted
        on."""
        live = set(live_execution_ids or ())
        out = []
        for prefix, why in (('', 'not_an_execution_id'), (VERIFY_KEY, 'not_a_verifier_key')):
            try:
                names = os.listdir(os.path.join(isolation_dir(), prefix))
            except FileNotFoundError:
                continue
            for n in names:
                if not n.endswith('.json'):
                    continue
                key = prefix + n[:-len('.json')]
                try:
                    principal(key)
                except IsolationUnavailable:
                    self._report_invalid(prefix + n, why)
                    continue
                if key not in live:
                    out.append(key)
        return out

    # ── one confined verifier attempt (A6-3, T-054 C-1013 §1 and §3) ──

    def run_confined(self, request, argv, *, env, timeout, out_path, stdin_path, record,
                     keep, prepare=None):
        """One verifier attempt, in this order: admit it (its consumed marker, before
        any file of it is written) -> `prepare()`, the caller's fresh-only creation of
        the attempt's files, which returns the environment built over them (and replaces
        *env*) -> establish its principal (nothing is
        launched unless all six conditions hold) -> launch into its Core-held Job with
        Core's handles -> wait under the soft limits -> tree shutdown, after confirmed
        quiescence when the root exited cleanly -> freeze the output -> `record(result)`
        -> delete the profile. Returns `run_check`'s result plus `confinement`; `error`
        is set whenever the run cannot be read as a clean finish.

        *record* is the caller's durable write of the verdict. It returns once the
        verdict is recorded, or once the row no longer awaits it; whatever it raises
        leaves the profile for reclaim and propagates. A teardown that fails quarantines
        the profile and never touches the result. Anything raised after
        establishment closes the Job first and propagates: no result is recorded and
        the profile is left for reclaim."""
        key = request.execution_id
        self._confined.add(key)
        try:
            result, established = self._run_confined(request, argv, env, timeout,
                                                      out_path, stdin_path, keep, prepare)
            record(result)
            if established:
                self._contained(key, lambda: self.teardown(key, reason='verified'))
            return result
        finally:
            self._confined.discard(key)

    def _run_confined(self, request, argv, env, timeout, out_path, stdin_path, keep, prepare):
        key, api = request.execution_id, self.boundary
        t0 = time.monotonic()
        try:
            _admit(key)
        except IsolationUnavailable as err:
            # refused before any file of the attempt is touched, so nothing is read
            return _unread(t0, 'isolation: %s' % err.reason), False
        self._admitted.add(key)
        if prepare is not None:
            try:
                env = prepare()
            except BaseException as err:
                # admitted and consumed, never started: whatever prepare raised, the
                # admission goes with it, or a later establish would skip the marker
                self._admitted.discard(key)
                if not isinstance(err, (OSError, ValueError)):
                    raise
                return _unread(t0, 'prepare_failed: %s' % err), False
        try:
            rec = self.establish(request)
        except IsolationUnavailable as err:
            return _confined_result(out_path, keep, t0, 'isolation: %s' % err.reason, None,
                                    {}), False
        finally:
            self._admitted.discard(key)
        facts = {'isolated': True, 'ac_profile': rec.profile, 'ac_sid': rec.sid,
                 'capabilities': list(rec.capabilities),
                 'job': 'core-held-unnamed-kill-on-close'}
        rows = [request.grant_for(r).path for r in ('checkout', 'scratch')]
        roots = [p for p in rows if not any(_norm(p) != _norm(q) and _within(p, q)
                                            for q in rows)]
        deadline = t0 + timeout
        late = 'timed out after %ds' % timeout
        try:
            try:
                start = _tree_bytes(roots)
            except OSError as err:
                error, child = 'accounting_failed: %s' % err, None
            else:
                error, child = self._confined_launch(api, rec, request, argv, env,
                                                     stdin_path, out_path)
            while error is None:
                exited = child.wait(min(CONFINED_POLL_S,
                                        max(0.0, deadline - time.monotonic()))) is not None
                # the deadline is read after the monitor and before the exit counts:
                # an exit or an accounting pass that ends late is a timeout, not a pass
                error = _over_limit(out_path, roots, start) or (
                    late if time.monotonic() >= deadline else None)
                if exited:
                    break
            if error is None:
                # accounted again once the Job is empty: a descendant may have written
                # past a cap, or broken the walk, after the root's last poll
                error = self._quiescent(api, self.held_job(key)) or \
                    _over_limit(out_path, roots, start) or (
                        late if time.monotonic() >= deadline else None)
        except BaseException:
            # the Job never outlives a failure here: closed, and the failure raised as it
            # was. No result is recorded and the profile is left for reclaim
            try:
                self._close_job(key)
            except Exception:
                pass
            raise
        try:
            self._close_job(key)
        except (IsolationUnavailable, OSError) as err:
            error = error or 'shutdown_failed: %s' % err
        code = None if error else child.wait(0)
        return _confined_result(out_path, keep, t0, error, code, facts), True

    def _confined_launch(self, api, rec, request, argv, env, stdin_path, out_path):
        handles = []
        try:
            handles.append(api.open_inherited(stdin_path, 'read'))
            handles.append(api.open_inherited(out_path, 'append'))
            child = api.launch(list(argv), cwd=request.workspace, env=env,
                               profile=rec.profile, job=self.held_job(rec.execution_id),
                               stdin=handles[0], stdout=handles[1])
        except Exception as err:                       # nothing half-started survives
            failed = getattr(err, 'child', None)
            if failed is not None:
                self._live[rec.execution_id] = failed
            return 'launch_failed: %s' % err, None
        finally:
            for h in handles:
                try:
                    api.close_handle(h)
                except Exception:
                    pass
        self._live[rec.execution_id] = child
        return None, child

    @staticmethod
    def _quiescent(api, job):
        """None once the held Job reports no member within `EXIT_WAIT_S`, else why not.
        A count Core cannot read is never zero, and a survivor is never waited out."""
        count = getattr(api, 'job_active_processes', None)
        if job is None or count is None:
            return 'quiescence_unknown: no Job count to read'
        deadline = time.monotonic() + EXIT_WAIT_S
        while True:
            try:
                n = count(job)
            except (IsolationUnavailable, OSError) as err:
                return 'quiescence_unknown: %s' % err
            if type(n) is int and n == 0:
                return None
            if time.monotonic() >= deadline:
                return 'quiescence_unknown: %r still in the Job' % (n,)
            time.sleep(0.05)


def _tree_bytes(roots):
    """Bytes under *roots*, counted without following any link: a symlink or a
    reparse point (a junction) counts as itself and is never entered. Raises OSError
    when an entry cannot be classified or the walk outgrows `CONFINED_WALK_MAX`, so an
    unknown size is never read as a small one."""
    total, seen, todo = 0, 0, list(roots)
    while todo:
        path = todo.pop()
        # a root, or a directory queued as plain and replaced before its turn, is read
        # again without following: an alias is never entered. The interval between this
        # read and the scan itself stays open (a same-user race), narrowed not closed
        if not _plain_dir(os.lstat(path)):
            raise OSError('not a plain directory when scanned: %s' % path)
        with os.scandir(path) as entries:
            for e in entries:
                seen += 1
                if seen > CONFINED_WALK_MAX:
                    raise OSError('more than %d entries' % CONFINED_WALK_MAX)
                st = e.stat(follow_symlinks=False)
                reparse = getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                if _plain_dir(st):
                    todo.append(e.path)
                elif stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or reparse:
                    total += st.st_size
                else:
                    raise OSError('an entry that cannot be classified: %s' % e.path)
    return total


def _plain_dir(st):
    return stat.S_ISDIR(st.st_mode) and not (
        getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _over_limit(out_path, roots, start):
    try:
        out = os.lstat(out_path).st_size
        grown = _tree_bytes(roots) - start
    except OSError as err:
        return 'accounting_failed: %s' % err
    if out > CONFINED_OUT_MAX:
        return 'limit_exceeded: out.log holds %d bytes' % out
    if grown > CONFINED_GROWTH_MAX:
        return 'limit_exceeded: the checkout and scratch grew %d bytes' % grown
    return None


def _unread(t0, error):
    """A refusal before any file of the attempt was written: no output read."""
    return {'exit_code': None, 'duration_ms': int((time.monotonic() - t0) * 1000),
            'error': error, 'output': b'', 'output_bytes': 0, 'truncated': False,
            'confinement': {}}


def _confined_result(out_path, keep, t0, error, code, facts):
    tail, size = _captured(out_path, keep)
    return {'exit_code': code, 'duration_ms': int((time.monotonic() - t0) * 1000),
            'error': error, 'output': tail, 'output_bytes': size, 'truncated': size > keep,
            'confinement': facts}


def _captured(out_path, keep):
    """The output, frozen: its last *keep* bytes and its size."""
    size = os.path.getsize(out_path)
    with open(out_path, 'rb') as f:
        f.seek(max(0, size - keep))
        return f.read(), size


def _staged(cmd):
    """The stage the isolated hook command runs from: Core's `(python.exe, -I,
    hook.py)` inside one verified stage under `runtime/`. Anything else (no command,
    another shape, paths outside one stage, a stage that does not verify) refuses the
    launch before any profile is touched."""
    if not (isinstance(cmd, tuple) and len(cmd) == 3 and cmd[1] == '-I'
            and all(isinstance(p, str) and os.path.isabs(p) for p in (cmd[0], cmd[2]))):
        raise base.SpawnFailed('isolation: the hook command is not a staged one: %r'
                               % (cmd,))
    stage = os.path.dirname(cmd[0])
    if (cmd[0], cmd[2]) != (os.path.join(stage, 'python.exe'),
                            os.path.join(stage, staging.HOOK)):
        raise base.SpawnFailed('isolation: the hook command is not one stage: %r' % (cmd,))
    try:
        return staging.verify(stage)
    except OSError as err:
        raise base.SpawnFailed('isolation: the hook runtime does not verify: %s' % err)


def default_plan(spec):
    """The §3.1 inventory as this layout can establish it today — the production shape.

    It is deliberately *not* satisfiable yet: no R3-B broker holds the provider-access
    row, and nothing grants the runtime and hook rows, so §3.4's condition 2 stays unmet
    and an isolated production execution never starts — with no setting that changes
    it (S1 gate §3: "the invariant check must test all six conditions including the
    later-slice boundaries"). The class 1–3 directories are the ones `base.spawn`
    creates (§7.5), and the execution's own directory around them is Core's. A
    synthetic fixture supplies its own plan and satisfies the conditions in the fixture.
    """
    paths = ExecPaths(spec.execution_id)
    stage = _staged(spec.hook_settings)
    # planned rows only: nothing here applies any of them. The runtime and hook rows
    # name Core's verified stage (C4b), never the real Python install or this
    # repository, which no grant may ever touch (one did, 2026-10-08)
    grants = (Grant(spec.workdir, 'rw', 'workspace'),
              Grant(stage, 'rx', 'runtime'),
              Grant(stage, 'rx', 'hook'),
              Grant(paths.req, 'rw', 'request'),
              Grant(paths.res, 'rx', 'response'),
              Grant(paths.ctl, 'rx', 'sentinel'),
              Grant(paths.state, 'rw', 'state'))
    return IsolationRequest(execution_id=spec.execution_id, workspace=spec.workdir,
                            grants=grants, mailbox=paths.req, response=paths.res,
                            sentinel=paths.ctl,
                            spawn_config=os.path.join(paths.res, 'settings.json'),
                            state_dir=paths.state, core_state=run_dir(),
                            core_only=(paths.dir,), broker='')


class IsolationContext:
    """What rides on the `ExecutionSpec` into `base.spawn`: the isolated launch itself.
    Its presence, not a flag, is what selects the isolated path, and its failure is
    `SpawnFailed` — never a second attempt through the detached launcher."""

    def __init__(self, authority, request):
        self.authority = authority
        self.request = request
        self.execution_id = request.execution_id

    # ── the mechanism (§3.4) ──

    def launch(self, argv, *, cwd, env, paths):
        """Create the process inside the execution identity and inside its Core-held
        Job, with Core's own handles for stdin, stdout and stderr (§3.3: "the prompt
        and the stream reach the process as Core-opened handles"). Returns
        `(child, None)` like `proc.spawn_detached`; every failure raises
        `base.SpawnFailed` after the deterministic state is recorded."""
        api = self.authority.boundary
        try:
            rec = self.authority.establish(self.request, paths)
        except IsolationUnavailable as err:
            raise base.SpawnFailed('isolation: %s%s' % (err.reason,
                                                        ' (%s)' % err.detail if err.detail else ''))
        handles = []
        try:
            handles.append(api.open_inherited(paths.prompt, 'read'))
            handles.append(api.open_inherited(paths.stream, 'append'))
            child = api.launch(list(argv), cwd=cwd, env=env, profile=rec.profile,
                               job=self.authority.held_job(rec.execution_id),
                               stdin=handles[0], stdout=handles[1])
            # held before anything else can fail, so the end path waits on this process
            # by its own handle and never by a PID that may name another one by then
            self.authority._live[rec.execution_id] = child
            rec.pid, rec.create_time = child.pid, base_create_time(child.pid)
            self.authority._save(rec)
            return child, None
        except Exception as err:                       # nothing half-started survives
            # a process created and then not confined or not resumed was terminated by
            # the boundary, and is held here like a launched one, so the end path waits
            # on it by its own handle; the record never names it launched
            failed = getattr(err, 'child', None)
            if failed is not None:
                self.authority._live[rec.execution_id] = failed
            if isinstance(err, IsolationUnavailable):
                raise base.SpawnFailed('isolation: %s%s' % (
                    err.reason, ' (%s)' % err.detail if err.detail else ''))
            raise base.SpawnFailed('isolation: launch_failed (%s)' % err)
        finally:
            for h in handles:
                try:
                    api.close_handle(h)
                except Exception:
                    pass

    # what `base.spawn` and the registry read afterwards
    def facts(self):
        rec = self.authority.record(self.execution_id)
        if rec is None:
            return {}
        return {'isolated': True, 'ac_profile': rec.profile, 'ac_sid': rec.sid,
                'capabilities': list(rec.capabilities), 'isolation_state': rec.state,
                'job': 'core-held-unnamed-kill-on-close'}


def base_create_time(pid):
    from claude_sessions import proc
    return proc.process_create_time(pid)


# ── the OS boundary ──────────────────────────────────────────────────────────

class UnavailableBoundary:
    """Everything fails closed here: no identity, no Job, nothing launches, and the
    isolated path therefore never starts a process (§3.4). This is also what a
    non-Windows Core gets."""
    id = 'unavailable'

    def available(self):
        return False

    def __getattr__(self, name):
        def nope(*a, **k):
            raise IsolationUnavailable('platform', 'no isolation boundary on %s' % sys.platform)
        return nope


FILE_READ_DATA, FILE_WRITE_DATA, FILE_APPEND_DATA, FILE_EXECUTE = 0x1, 0x2, 0x4, 0x20
FILE_WRITE_EA, FILE_DELETE_CHILD, FILE_WRITE_ATTRIBUTES = 0x10, 0x40, 0x100
GENERIC_READ, GENERIC_WRITE, GENERIC_EXECUTE, GENERIC_ALL = 0x80000000, 0x40000000, \
    0x20000000, 0x10000000
WRITE_DAC, WRITE_OWNER, DELETE = 0x40000, 0x80000, 0x10000

#: The access-ACE types a DACL holds (winnt.h): allowed 0x0, denied 0x1 and their
#: conditional ("callback") forms 0x9 and 0xA. Each carries its SID right after the
#: 4-byte header and the 4-byte mask; a conditional one carries its condition after the
#: SID. Anything else found in a DACL — an object or compound ACE, or an audit, alarm or
#: label type that belongs in a SACL — is refused rather than read at a guessed offset.
ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE = 0x0, 0x1
ACCESS_ALLOWED_CALLBACK_ACE_TYPE, ACCESS_DENIED_CALLBACK_ACE_TYPE = 0x9, 0xA
DACL_ACE_TYPES = (ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE,
                  ACCESS_ALLOWED_CALLBACK_ACE_TYPE, ACCESS_DENIED_CALLBACK_ACE_TYPE)
ALLOW_ACE_TYPES = (ACCESS_ALLOWED_ACE_TYPE, ACCESS_ALLOWED_CALLBACK_ACE_TYPE)
#: an inherit-only ACE controls what is created inside a directory, not the directory
INHERIT_ONLY_ACE = 0x08
SYSTEM_SID = 'S-1-5-18'
#: the two app-package groups, which `BROAD_PRINCIPALS` already counts as reaching
#: containers: an allow ACE for either reaches the execution like one for its own SID
APP_PACKAGE_SIDS = ('S-1-15-2-1', 'S-1-15-2-2')
#: a NULL DACL grants everyone everything, AppContainers included, and is read as that
NULL_DACL = tuple((ACCESS_ALLOWED_ACE_TYPE, s, GENERIC_ALL, 0)
                  for s in ('S-1-1-0',) + APP_PACKAGE_SIDS)


def access_covered(mask, access):
    """Does the ACE mask *mask* give exactly what the inventory row *access* allows?
    Too little is un-established; more than the row allows is a broad grant (§3.1).
    Control/ownership/full-control always exceed a row; a writable ('rw') row is
    satisfied by Modify (read+write, whose delete is part of Modify), while read-'rx'
    and execute-'x' rows tolerate none of `_write_like`'s rights: no write of data,
    attributes or extended attributes, and no delete of the object or of a child.
    A row that is none of the three is never covered."""
    if mask & (WRITE_DAC | WRITE_OWNER | GENERIC_ALL):
        return False
    read = bool(mask & (GENERIC_READ | FILE_READ_DATA))
    write = bool(mask & (GENERIC_WRITE | FILE_WRITE_DATA | FILE_APPEND_DATA))
    execute = bool(mask & (GENERIC_EXECUTE | FILE_EXECUTE))
    if access == 'rx':
        return read and execute and not _write_like(mask)
    if access == 'x':
        return execute and not read and not _write_like(mask)
    return access == 'rw' and read and write


def _write_like(mask):
    """Any right that changes the object or what it holds: FILE_GENERIC_WRITE's parts
    (data, append, extended attributes, attributes), deleting it or a child of it, and
    control of its DACL or owner."""
    return bool(mask & (GENERIC_WRITE | GENERIC_ALL | FILE_WRITE_DATA | FILE_APPEND_DATA
                        | FILE_WRITE_EA | FILE_WRITE_ATTRIBUTES | FILE_DELETE_CHILD
                        | WRITE_DAC | WRITE_OWNER | DELETE))


def parse_ace(raw):
    """One DACL ACE as `(type, sid, mask, flags)`, read from its own bytes: ACE_HEADER
    (type, flags, size), the mask, then the SID (MS-DTYP 2.4.2). Anything that is not
    exactly a well-formed access ACE raises: a reader that skips what it cannot parse
    reports a clean DACL it never saw."""
    if len(raw) < 16:
        raise IsolationUnavailable('dacl_malformed', 'an ACE of %d bytes' % len(raw))
    ace_type, flags, size = raw[0], raw[1], int.from_bytes(raw[2:4], 'little')
    if ace_type not in DACL_ACE_TYPES:
        raise IsolationUnavailable('dacl_unsupported_ace', 'ACE type 0x%x' % ace_type)
    count = raw[9]                                  # the SID's sub-authority count
    end = 16 + 4 * count
    plain = ace_type in (ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE)
    if size != len(raw) or raw[8] != 1 or count > 15 or end > size or (plain and end != size):
        raise IsolationUnavailable('dacl_malformed', 'ACE type 0x%x of %d bytes'
                                   % (ace_type, size))
    authority = int.from_bytes(raw[10:16], 'big')
    if authority >= 2 ** 32:
        # MS-DTYP writes such an authority in hex; no principal compared here has one
        raise IsolationUnavailable('dacl_unsupported_sid', 'SID authority 0x%x' % authority)
    subs = ''.join('-%d' % int.from_bytes(raw[i:i + 4], 'little') for i in range(16, end, 4))
    return ace_type, 'S-1-%d%s' % (authority, subs), int.from_bytes(raw[4:8], 'little'), flags


class DaclReaders:
    """§3.4's conditions 2, 3 and 5, read from `self.dacl(path)`: the boundary's own
    descriptor read, or a synthetic one in a test. A read that fails raises, so no
    reader can take an unreadable descriptor for an empty one."""

    def grant_established(self, path, sid, access):
        """Every allow ACE for the execution's own SID, taken together, against the row.
        What the row needs must come from unconditional ACEs that apply to *path*
        itself: a conditional ACE holds only while its condition does, and an
        inherit-only one does not apply to the object it sits on. What the row must
        not exceed is judged over all of them, conditional and inherit-only included,
        because either may reach the execution (an inherit-only ACE reaches what is
        created inside *path*). One acceptable ACE beside a broader one is not a grant."""
        held = reach = 0
        for t, s, m, f in self.dacl(path):
            if t in ALLOW_ACE_TYPES and s == sid:
                reach |= m
                if t == ACCESS_ALLOWED_ACE_TYPE and not f & INHERIT_ONLY_ACE:
                    held |= m
        return access_covered(held, access) and access_covered(reach, access)

    def granted_to(self, path, sid):
        """Can the execution reach *path* through any allow ACE? Used for the paths that
        must not be granted at all (Core's own state). Conservative on purpose: a
        conditional or inherit-only ACE counts, a deny ACE is not credited, and an
        app-package group counts like the execution's own SID."""
        if not path:
            return False
        reach = (sid,) + APP_PACKAGE_SIDS
        return any(t in ALLOW_ACE_TYPES and s in reach for t, s, m, f in self.dacl(path))

    def broad_write_grant(self, path, sid):
        """The first principal other than the execution, Core's own user and SYSTEM that
        an allow ACE gives a write-like right — a broad principal above all (§3.1's
        third condition) — or None. Conservative like `granted_to`. The execution's own
        ACEs are not judged here: S1 applies none."""
        me = self._user_sid()
        return next((s for t, s, m, f in self.dacl(path)
                     if t in ALLOW_ACE_TYPES and _write_like(m)
                     and (s in BROAD_PRINCIPALS or s not in (sid, SYSTEM_SID, me))), None)


if WINDOWS:
    import ctypes as C
    from ctypes import wintypes as W

    if not hasattr(W, 'PWSTR'):
        W.PWSTR = C.POINTER(W.WCHAR)
    if not hasattr(W, 'ULONG_PTR'):
        W.ULONG_PTR = C.c_ulonglong if C.sizeof(C.c_void_p) == 8 else C.c_ulong

    kernel32 = C.WinDLL('kernel32')
    advapi32 = C.WinDLL('advapi32')
    userenv = C.WinDLL('userenv')
    ntdll = C.WinDLL('ntdll')

    def _f(lib, name, restype, argtypes):
        fn = getattr(lib, name)
        fn.restype, fn.argtypes = restype, argtypes
        return fn

    def _err():
        return kernel32.GetLastError()

    class _WinFail(IsolationUnavailable):
        """A Win32 call that failed: an isolation failure like any other, so it fails
        closed through the same `except` clauses and never escapes them."""

        def __init__(self, name, code=None, status=None):
            self.name, self.code, self.status = name, code, status
            super().__init__('winapi', '%s failed (%s)'
                             % (name, 'winerror=%s' % code if code is not None
                                else 'ntstatus=%s' % hex(status & 0xFFFFFFFF)))

    def _win(ok, name):
        if not ok:
            raise _WinFail(name, _err())
        return ok

    class _SI(C.Structure):
        _fields_ = [('cb', W.DWORD), ('lpReserved', W.PWSTR), ('lpDesktop', W.PWSTR),
                    ('lpTitle', W.PWSTR), ('dwX', W.DWORD), ('dwY', W.DWORD),
                    ('dwXSize', W.DWORD), ('dwYSize', W.DWORD), ('dwXCountChars', W.DWORD),
                    ('dwYCountChars', W.DWORD), ('dwFillAttribute', W.DWORD),
                    ('dwFlags', W.DWORD), ('wShowWindow', W.WORD), ('cbReserved2', W.WORD),
                    ('lpReserved2', C.POINTER(C.c_ubyte)), ('hStdInput', W.HANDLE),
                    ('hStdOutput', W.HANDLE), ('hStdError', W.HANDLE)]

    class _SIEX(C.Structure):
        _fields_ = [('StartupInfo', _SI), ('lpAttributeList', C.c_void_p)]

    class _PI(C.Structure):
        _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE), ('dwProcessId', W.DWORD),
                    ('dwThreadId', W.DWORD)]

    class _CAPS(C.Structure):
        _fields_ = [('AppContainerSid', C.c_void_p), ('Capabilities', C.c_void_p),
                    ('CapabilityCount', W.DWORD), ('Reserved', W.DWORD)]

    class _BL(C.Structure):
        _fields_ = [('PerProcessUserTimeLimit', C.c_longlong),
                    ('PerJobUserTimeLimit', C.c_longlong), ('LimitFlags', W.DWORD),
                    ('MinimumWorkingSetSize', C.c_size_t), ('MaximumWorkingSetSize', C.c_size_t),
                    ('ActiveProcessLimit', W.DWORD), ('Affinity', C.c_size_t),
                    ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]

    class _JBAI(C.Structure):
        # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four LARGE_INTEGER times, then DWORDs
        _fields_ = [('TotalUserTime', C.c_longlong), ('TotalKernelTime', C.c_longlong),
                    ('ThisPeriodTotalUserTime', C.c_longlong),
                    ('ThisPeriodTotalKernelTime', C.c_longlong),
                    ('TotalPageFaultCount', W.DWORD), ('TotalProcesses', W.DWORD),
                    ('ActiveProcesses', W.DWORD), ('TotalTerminatedProcesses', W.DWORD)]

    class _ELI(C.Structure):
        _fields_ = [('Basic', _BL), ('IoInfo', C.c_ulonglong * 6),
                    ('ProcessMemoryLimit', C.c_size_t), ('JobMemoryLimit', C.c_size_t),
                    ('PeakProcessMemoryUsed', C.c_size_t), ('PeakJobMemoryUsed', C.c_size_t)]

    class _HE(C.Structure):
        _fields_ = [('Object', C.c_void_p), ('pid', W.ULONG_PTR), ('Handle', W.HANDLE),
                    ('Granted', W.ULONG), ('creator', W.USHORT), ('TypeIndex', W.USHORT),
                    ('Attributes', W.ULONG), ('Reserved', W.ULONG)]

    class _ACINFO(C.Structure):
        # ACL_SIZE_INFORMATION (AclSizeInformation = 2): the field ORDER matters —
        # AceCount is first. Reading it as if AclBytesInUse led yielded a zero count.
        _fields_ = [('AceCount', W.DWORD), ('AclBytesInUse', W.DWORD),
                    ('AclBytesFree', W.DWORD)]

    _CloseHandle = _f(kernel32, 'CloseHandle', W.BOOL, [W.HANDLE])
    _CreateFileW = _f(kernel32, 'CreateFileW', W.HANDLE,
                      [W.PWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE])
    _CreateJobObjectW = _f(kernel32, 'CreateJobObjectW', W.HANDLE, [C.c_void_p, W.PWSTR])
    _QueryInformationJobObject = _f(kernel32, 'QueryInformationJobObject', W.BOOL,
                                    [W.HANDLE, W.INT, C.c_void_p, W.DWORD,
                                     C.POINTER(W.DWORD)])
    _SetInformationJobObject = _f(kernel32, 'SetInformationJobObject', W.BOOL,
                                  [W.HANDLE, W.INT, C.c_void_p, W.DWORD])
    _AssignProcessToJobObject = _f(kernel32, 'AssignProcessToJobObject', W.BOOL,
                                   [W.HANDLE, W.HANDLE])
    _CreateProcessW = _f(kernel32, 'CreateProcessW', W.BOOL,
                         [W.PWSTR, W.PWSTR, C.c_void_p, C.c_void_p, W.BOOL, W.DWORD,
                          C.c_void_p, W.PWSTR, C.c_void_p, C.POINTER(_PI)])
    _ResumeThread = _f(kernel32, 'ResumeThread', W.DWORD, [W.HANDLE])
    _GetExitCodeProcess = _f(kernel32, 'GetExitCodeProcess', W.BOOL,
                             [W.HANDLE, C.POINTER(W.DWORD)])
    _GetProcessTimes = _f(kernel32, 'GetProcessTimes', W.BOOL,
                          [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4)
    _TerminateProcess = _f(kernel32, 'TerminateProcess', W.BOOL, [W.HANDLE, W.UINT])
    _WaitForSingleObject = _f(kernel32, 'WaitForSingleObject', W.DWORD, [W.HANDLE, W.DWORD])
    _OpenProcess = _f(kernel32, 'OpenProcess', W.HANDLE, [W.DWORD, W.BOOL, W.DWORD])
    _GetCurrentProcess = _f(kernel32, 'GetCurrentProcess', W.HANDLE, [])
    _GetCurrentProcessId = _f(kernel32, 'GetCurrentProcessId', W.DWORD, [])
    _DuplicateHandle = _f(kernel32, 'DuplicateHandle', W.BOOL,
                          [W.HANDLE, W.HANDLE, W.HANDLE, C.POINTER(W.HANDLE), W.DWORD,
                           W.BOOL, W.DWORD])
    _SetHandleInformation = _f(kernel32, 'SetHandleInformation', W.BOOL,
                               [W.HANDLE, W.DWORD, W.DWORD])
    _GetHandleInformation = _f(kernel32, 'GetHandleInformation', W.BOOL,
                               [W.HANDLE, C.POINTER(W.DWORD)])
    _LocalFree = _f(kernel32, 'LocalFree', C.c_void_p, [C.c_void_p])
    _InitializeProcThreadAttributeList = _f(kernel32, 'InitializeProcThreadAttributeList',
                                            W.BOOL, [C.c_void_p, W.DWORD, W.DWORD,
                                                     C.POINTER(C.c_size_t)])
    _UpdateProcThreadAttribute = _f(kernel32, 'UpdateProcThreadAttribute', W.BOOL,
                                    [C.c_void_p, W.DWORD, W.DWORD, C.c_void_p, C.c_size_t,
                                     C.c_void_p, C.c_void_p])
    _DeleteProcThreadAttributeList = _f(kernel32, 'DeleteProcThreadAttributeList', None,
                                        [C.c_void_p])
    _QueryObject = _f(ntdll, 'NtQueryObject', W.LONG,
                      [W.HANDLE, W.INT, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)])
    _NtQuerySystemInformation = _f(ntdll, 'NtQuerySystemInformation', W.LONG,
                                   [W.ULONG, C.c_void_p, W.ULONG, C.POINTER(W.ULONG)])
    _OpenProcessToken = _f(advapi32, 'OpenProcessToken', W.BOOL,
                           [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)])
    _GetTokenInformation = _f(advapi32, 'GetTokenInformation', W.BOOL,
                             [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)])
    _ConvertSidToStringSidW = _f(advapi32, 'ConvertSidToStringSidW', W.BOOL,
                                 [C.c_void_p, C.POINTER(W.PWSTR)])
    _GetSecurityInfoByNameW = _f(advapi32, 'GetNamedSecurityInfoW', W.ULONG,
                                 [W.PWSTR, W.INT, W.DWORD, C.c_void_p, C.c_void_p,
                                  C.POINTER(C.c_void_p), C.POINTER(C.c_void_p),
                                  C.POINTER(C.c_void_p)])
    _GetAclInformation = _f(advapi32, 'GetAclInformation', W.BOOL,
                            [C.c_void_p, C.c_void_p, W.DWORD, W.INT])
    _GetAce = _f(advapi32, 'GetAce', W.BOOL, [C.c_void_p, W.DWORD, C.POINTER(C.c_void_p)])
    _CreateAppContainerProfile = _f(userenv, 'CreateAppContainerProfile', C.c_int,
                                    [W.PWSTR, W.PWSTR, W.PWSTR, C.c_void_p, W.DWORD,
                                     C.POINTER(C.c_void_p)])
    _DeriveAppContainerSidFromAppContainerName = _f(
        userenv, 'DeriveAppContainerSidFromAppContainerName', C.c_int,
        [W.PWSTR, C.POINTER(C.c_void_p)])
    _DeleteAppContainerProfile = _f(userenv, 'DeleteAppContainerProfile', C.c_int, [W.PWSTR])

    STILL_ACTIVE = 259
    #: `CreateAppContainerProfile`'s answer when the profile already exists, as userenv.h
    #: states it: HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS), with ERROR_ALREADY_EXISTS the
    #: Win32 code 183 and the macro (winerror.h) giving 0x80070000 | code
    ERROR_ALREADY_EXISTS = 183
    E_PROFILE_EXISTS = 0x80070000 | ERROR_ALREADY_EXISTS
    ERROR_INVALID_PARAMETER = 87
    HANDLE_FLAG_INHERIT = 0x1
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    OBJECT_TYPE_INFORMATION, OBJECT_NAME_INFORMATION = 2, 1
    PROCESS_CREATE_PROCESS, PROCESS_QUERY_LIMITED_INFORMATION = 0x0800, 0x1000
    PROCESS_QUERY_INFORMATION, PROCESS_TERMINATE, PROCESS_DUP_HANDLE = 0x0400, 0x1, 0x40
    TOKEN_QUERY, TOKEN_USER, TOKEN_GROUPS = 0x8, 1, 2
    TOKEN_CAPABILITIES, TOKEN_APPCONTAINER_SID = 30, 31
    TOKEN_IS_APPCONTAINER, TOKEN_INTEGRITY_LEVEL = 29, 25
    CREATE_SUSPENDED, DETACHED_PROCESS, EXTENDED_STARTUPINFO_PRESENT = 0x4, 0x8, 0x80000
    CREATE_UNICODE_ENVIRONMENT = 0x400
    STARTF_USESTDHANDLES = 0x100
    ATTR_SECURITY_CAPABILITIES = 0x00020009
    ATTR_HANDLE_LIST = 0x00020002               # WinBase.h: ProcThreadAttributeHandleList, input
    FILE_GENERIC_RW = 0x40000000 | 0x80000000 | 0x10000000
    STATUS_INFO_LENGTH_MISMATCH = -1073741772

    def _sid_str(psid):
        if not psid:
            return None
        s = W.PWSTR()
        _win(_ConvertSidToStringSidW(psid, C.byref(s)), 'ConvertSidToStringSidW')
        out = C.wstring_at(s)
        _LocalFree(s)
        return out

    def _derive_name(name):
        """The SID an identity's name derives to — pure, and the attestation §3.4's
        first condition compares the created SID against."""
        psid = C.c_void_p()
        hr = _DeriveAppContainerSidFromAppContainerName(name, C.byref(psid))
        if hr != 0:
            raise IsolationUnavailable('profile_derive', 'hr=%s' % hex(hr & 0xFFFFFFFF))
        try:
            return _sid_str(psid)
        finally:
            if psid:
                _LocalFree(psid)

    class WindowsBoundary(DaclReaders):
        """The OS mechanism itself: the validated ctypes path of the go/no-go spike,
        nothing else. Every failure is an `IsolationUnavailable`, so a caller can
        never mistake a broken check for a passed one."""
        id = 'windows'

        def available(self):
            return True

        # ── the identity (§3.1, R7) ──

        def create_profile(self, execution_id):
            """The identity, created (or confirmed already there) with **no capability
            SIDs at all** (§4.9). Answers what the OS said, because §3.4's first
            condition is about the answer, not about a hope. The name is derived here
            from a validated execution id and never accepted from a caller."""
            name = validated_profile(execution_id)
            psid = C.c_void_p()
            # an HRESULT is a signed LONG, so ctypes answers a failure as a negative int;
            # compared unsigned, as the header writes it
            hr = _CreateAppContainerProfile(name, name, name, None, len(CAPABILITIES),
                                           C.byref(psid)) & 0xFFFFFFFF
            if hr not in (0, E_PROFILE_EXISTS):
                raise IsolationUnavailable('profile_create', 'hr=%s' % hex(hr))
            try:
                sid = _sid_str(psid) or _derive_name(name)
                return {'profile': name, 'sid': sid, 'created': True,
                        'existed': hr == E_PROFILE_EXISTS,
                        'package_dir': self.package_dir_state(name)}
            finally:
                if psid:
                    _LocalFree(psid)

        def delete_profile(self, execution_id):
            """Only ever `archeus.exec.<validated execution id>`: no record, ledger or
            caller can point this at another profile (`archeus.spike.*`, another
            application's)."""
            # signed LONG from ctypes, so compared unsigned, as create_profile does
            hr = _DeleteAppContainerProfile(validated_profile(execution_id)) & 0xFFFFFFFF
            if hr not in (0, 0x80070490):                  # not found: already gone
                raise IsolationUnavailable('profile_delete', 'hr=%s' % hex(hr))

        def derive(self, execution_id):
            try:
                return _derive_name(profile_name(execution_id))
            except _WinFail as err:
                raise IsolationUnavailable('profile_derive', str(err))

        def derive_sid(self, execution_id):
            return self.derive(execution_id)

        def profile_exists(self, execution_id):
            # spike §5.4: the package directory's state is the lifecycle evidence. The
            # spike's 0x80070539 from `GetAppContainerFolderPath` came from passing a
            # profile name (build 26200, not retested); given the SID string on build
            # 26300 (A2) it answered S_OK while the profile was present and 0x80070002
            # before create and after delete. This predicate is unchanged pending a
            # separate decision. It is evidence of a *run* identity; §3.4's first
            # condition reads the create answer. A state that cannot be read raises:
            # recovery never takes it for absent.
            state = self.package_dir_state(profile_name(execution_id))
            if state == 'unknown':
                raise IsolationUnavailable('profile_state', 'the package directory of %s '
                                           'could not be read' % profile_name(execution_id))
            return state == 'materialized'

        def package_dir_state(self, name):
            base = os.environ.get('LOCALAPPDATA')
            if not base:
                return 'unknown'
            root = os.path.join(base, 'Packages', str(name).lower())
            try:
                os.stat(root)
            except FileNotFoundError:
                return 'absent'
            except OSError:
                return 'unknown'
            return 'materialized' if os.path.isdir(root) else 'unknown'

        # ── the Job (§3.7, R6-A) ──

        def create_job(self, execution_id):
            h = _CreateJobObjectW(None, None)               # unnamed: no name to open by
            if not h:
                raise IsolationUnavailable('job_create', 'winerror=%s' % _err())
            try:
                _win(_SetHandleInformation(h, HANDLE_FLAG_INHERIT, 0), 'SetHandleInformation')
                li = _ELI()
                li.Basic.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                _win(_SetInformationJobObject(h, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                             C.byref(li), C.sizeof(li)),
                     'SetInformationJobObject(KILL_ON_JOB_CLOSE)')
                facts = self.job_facts(h)
                if (facts.get('type') != 'Job' or facts.get('name') != ''
                        or facts.get('inheritable')):
                    raise IsolationUnavailable('job_limits', str(facts))
            except Exception:
                _CloseHandle(h)
                raise
            return h

        def job_facts(self, handle):
            """The spike's validated identification (`NtQueryObject`'s object-type
            information), never `GetFileType`, which answers 0 for a Job on build
            26200 (§5.3) — and the inheritability that makes Core its sole holder."""
            if handle is None:
                return None
            return {'type': self._obj_type(handle), 'name': self._obj_name(handle),
                    'inheritable': bool(self._handle_flags(handle) & HANDLE_FLAG_INHERIT)}

        def job_active_processes(self, job):
            """The Job's `ActiveProcesses` (JobObjectBasicAccountingInformation), read
            through Core's own handle. Written for the K3 fence and never run here: a
            reading on a real Job is T-008's (C6)."""
            info = _JBAI()
            _win(_QueryInformationJobObject(job, JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                                            C.byref(info), C.sizeof(info), None),
                 'QueryInformationJobObject')
            return int(info.ActiveProcesses)

        def assign_job(self, job, process_handle):
            if job is None:
                raise IsolationUnavailable('job_missing', 'no Job to assign the process to')
            _win(_AssignProcessToJobObject(job, process_handle), 'AssignProcessToJobObject')

        def close_job(self, job):
            """Closing the last handle is what ends the tree (kill-on-close)."""
            if job is not None:
                _CloseHandle(job)

        def close_handle(self, handle):
            if handle is not None:
                _CloseHandle(handle)

        def process_started(self, pid):
            """When the process now running under *pid* was created — the encoding
            `proc.process_create_time` records at launch, so the two compare — or None
            when nothing runs under it. Anything it cannot tell raises: a refused open or
            an unreadable time is not an exit. Nothing runs under a PID the open answers
            `ERROR_INVALID_PARAMETER` for (the reading psutil also takes); an exited
            process whose handles are still open reads as exited by its exit code."""
            h = _OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                code = _err()
                if code == ERROR_INVALID_PARAMETER:
                    return None
                raise IsolationUnavailable('process_state', 'pid %s: winerror=%s' % (pid, code))
            try:
                rc = W.DWORD(0)
                if not _GetExitCodeProcess(h, C.byref(rc)):
                    raise IsolationUnavailable('process_state', 'pid %s: exit code winerror=%s'
                                               % (pid, _err()))
                if rc.value != STILL_ACTIVE:
                    return None
                t = [W.FILETIME() for _ in range(4)]
                if not _GetProcessTimes(h, *[C.byref(x) for x in t]):
                    raise IsolationUnavailable('process_state', 'pid %s: times winerror=%s'
                                               % (pid, _err()))
                return (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
            finally:
                _CloseHandle(h)

        def job_handles_of(self, pid):
            """Every handle of *pid* whose object type is Job, with its name and
            inheritability: the sole-holder evidence (§3.7, R6-A)."""
            out = []
            for h in self._handles_of(pid):
                try:
                    if self._obj_type(h) != 'Job':
                        continue
                    out.append({'handle': h, 'type': 'Job', 'name': self._obj_name(h),
                                'inheritable': bool(self._handle_flags(h) & HANDLE_FLAG_INHERIT)})
                finally:
                    _CloseHandle(h)
            return out

        def _obj_type(self, h):
            buf = (C.c_byte * (16 + 2048))()
            got = W.DWORD(0)
            if _QueryObject(h, OBJECT_TYPE_INFORMATION, buf, C.sizeof(buf), C.byref(got)) != 0:
                return None
            length = C.cast(buf, C.POINTER(W.USHORT))[0]
            pbuf = C.cast(buf, C.POINTER(C.c_void_p))[1]
            if not pbuf or not length:
                return None
            return C.wstring_at(pbuf, length // 2)

        def _obj_name(self, h):
            """'' for an unnamed object; None when the query failed."""
            buf = (C.c_byte * (16 + 2048))()
            got = W.DWORD(0)
            if _QueryObject(h, OBJECT_NAME_INFORMATION, buf, C.sizeof(buf), C.byref(got)) != 0:
                return None
            length = C.cast(buf, C.POINTER(W.USHORT))[0]
            if length == 0:
                return ''
            pbuf = C.cast(buf, C.POINTER(C.c_void_p))[2]
            return C.wstring_at(pbuf, length // 2) if pbuf else ''

        def _handle_flags(self, h):
            flags = W.DWORD(0)
            if not _GetHandleInformation(h, C.byref(flags)):
                raise IsolationUnavailable('handle_state', 'winerror=%s' % _err())
            return flags.value

        def _handles_of(self, pid):
            size = W.ULONG(1 << 20)
            while True:
                buf = (C.c_byte * size.value)()
                st = _NtQuerySystemInformation(0x40, buf, size, None)
                if st == 0:
                    break
                if st == STATUS_INFO_LENGTH_MISMATCH or (st & 0xFFFFFFFF) == 0xC0000004:
                    size = W.ULONG(size.value * 2)
                    continue
                raise IsolationUnavailable('handle_enum', 'ntstatus=%s' % hex(st & 0xFFFFFFFF))
            n = C.cast(buf, C.POINTER(W.ULONG))[0]
            base = C.addressof(buf) + 16
            out = []
            ht = _OpenProcess(PROCESS_DUP_HANDLE, False, pid)
            if not ht:
                return out
            try:
                for i in range(n):
                    e = C.cast(base + i * C.sizeof(_HE), C.POINTER(_HE))
                    if e[0].pid != pid:
                        continue
                    dup = W.HANDLE()
                    if not _DuplicateHandle(ht, e[0].Handle, _GetCurrentProcess(),
                                            C.byref(dup), 0, False, 0):
                        continue
                    out.append(dup)                    # the caller closes each one
            finally:
                _CloseHandle(ht)
            return out

        # ── the token (evidence, never a decision) ──

        def token(self, pid):
            hproc = _OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not hproc:
                raise IsolationUnavailable('token', 'winerror=%s' % _err())
            tok = W.HANDLE()
            try:
                _win(_OpenProcessToken(hproc, TOKEN_QUERY, C.byref(tok)), 'OpenProcessToken')
                return {'is_appcontainer': self._token_flag(tok, TOKEN_IS_APPCONTAINER),
                        'ac_sid': self._token_sid(tok, TOKEN_APPCONTAINER_SID),
                        'integrity': self._token_integrity(tok),
                        'capability_sids': self._token_groups(tok, TOKEN_CAPABILITIES)
                        + self._token_groups(tok, TOKEN_GROUPS)}
            finally:
                if tok:
                    _CloseHandle(tok)
                _CloseHandle(hproc)

        def _token_groups(self, tok, cls):
            buf, got = self._token_buffer(tok, cls)
            if buf is None:
                return []
            n = C.cast(buf, C.POINTER(W.DWORD))[0]
            wide = C.sizeof(C.c_void_p) == 8
            # TOKEN_GROUPS/_CAPABILITIES: a DWORD count, then the SID_AND_ATTRIBUTES[]
            # array aligned to a pointer. On x64 the count pads to 8 before the array;
            # each entry is a PSID + DWORD attributes = 16 (x64) / 8 (x86) bytes.
            header = 8 if wide else 4
            entry = 16 if wide else 8
            out = []
            for i in range(n):
                at = C.addressof(buf) + header + i * entry
                psid = C.cast(at, C.POINTER(C.c_void_p))[0]
                s = _sid_str(psid) if psid else None
                if s:
                    out.append(s)
            return out

        def _token_flag(self, tok, cls):
            buf, _ = self._token_buffer(tok, cls)
            return None if buf is None else C.cast(buf, C.POINTER(W.DWORD))[0]

        def _token_sid(self, tok, cls):
            buf, _ = self._token_buffer(tok, cls)
            if buf is None:
                return None
            psid = C.cast(buf, C.POINTER(C.c_void_p))[0]
            return _sid_str(psid) if psid else None

        def _token_integrity(self, tok):
            buf, _ = self._token_buffer(tok, TOKEN_INTEGRITY_LEVEL)
            if buf is None:
                return None
            psid = C.cast(buf, C.POINTER(C.c_void_p))[0]
            if not psid:
                return None
            n = C.cast(psid, C.POINTER(C.c_ubyte))[1]
            return '0x%x' % C.cast(psid + 8, C.POINTER(W.DWORD))[n - 1]

        def _token_buffer(self, tok, cls):
            need = W.DWORD(64)
            for _ in range(4):
                buf = (C.c_byte * max(8, need.value))()
                got = W.DWORD(0)
                if _GetTokenInformation(tok, cls, buf, C.sizeof(buf), C.byref(got)):
                    return buf, got
                if _err() != 122:
                    return None, None
                need = W.DWORD(max(64, got.value))
            return None, None

        def capability_grants(self):
            """§4.9: this boundary grants no capability to anybody, so there are none
            to find. Any non-empty answer is a design change, not a setting."""
            return ()

        # ── the grants (§3.1): read, never written ──
        # S1 applies no ACE (grant application is outside it). `dacl` feeds the readers
        # §3.4's conditions 2, 3 and 5 check (`DaclReaders`); nothing in this module
        # changes an ACL, and `test_pv20_isolation`'s static gate keeps it that way.

        def _user_sid(self):
            """Core's own user SID, read from its process token — never parsed out of
            a localized tool's output."""
            tok = W.HANDLE()
            if not _OpenProcessToken(_GetCurrentProcess(), TOKEN_QUERY, C.byref(tok)):
                raise IsolationUnavailable('token', 'winerror=%s' % _err())
            try:
                sid = self._token_sid(tok, TOKEN_USER)
            except _WinFail as err:
                raise IsolationUnavailable('token', str(err))
            finally:
                _CloseHandle(tok)
            if not sid:
                raise IsolationUnavailable('token', 'the process token names no user')
            return sid

        def dacl(self, path):
            """[(ace_type, sid, mask, flags)] read from the security descriptor itself
            — `icacls`' output is localized and is not something to trust as evidence.
            Every failure raises: an unreadable or partly read descriptor is never an
            empty DACL. A NULL DACL (none at all) reads as what it grants: everything,
            to everyone."""
            pacl, sd = C.c_void_p(), C.c_void_p()
            err = _GetSecurityInfoByNameW(os.path.abspath(path), 1, 0x4, None, None,
                                          C.byref(pacl), None, C.byref(sd))
            if err != 0:
                raise IsolationUnavailable('dacl_unreadable', '%s: winerror=%s' % (path, err))
            try:
                if not pacl.value:
                    return list(NULL_DACL)
                info = _ACINFO()
                if not _GetAclInformation(pacl, C.byref(info), C.sizeof(info), 2):
                    raise IsolationUnavailable('dacl_unreadable', '%s: GetAclInformation '
                                               'winerror=%s' % (path, _err()))
                end = pacl.value + info.AclBytesInUse
                out = []
                for i in range(info.AceCount):
                    pace = C.c_void_p()
                    if not _GetAce(pacl, i, C.byref(pace)) or not pace.value:
                        raise IsolationUnavailable('dacl_unreadable', '%s: ACE %d of %d '
                                                   'could not be read' % (path, i, info.AceCount))
                    size = C.cast(pace.value + 2, C.POINTER(W.USHORT))[0]
                    if pace.value + size > end:
                        raise IsolationUnavailable('dacl_malformed', '%s: ACE %d runs past '
                                                   'the ACL' % (path, i))
                    out.append(parse_ace(C.string_at(pace.value, size)))
                return out
            finally:
                _LocalFree(sd)

        # ── the launch (§3.4) ──

        def open_inherited(self, path, mode):
            """A handle Core opens and hands to the process as stdio (§3.3). It is opened
            NOT inheritable: `launch` makes it inheritable for its own CreateProcessW call
            alone and names it in that call's handle list, so it reaches that child and
            no other process Core starts meanwhile."""
            access = (0x80000000 | 0x80) if mode == 'read' else (
                0x40000000 | 0x4 | 0x80)                  # GENERIC_WRITE | APPEND | ATTRIBUTES
            creation = 3 if mode == 'read' else 4         # OPEN_EXISTING | OPEN_ALWAYS
            h = _CreateFileW(os.path.abspath(path), access, 3, None, creation, 1, None)
            if not h or h in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
                raise IsolationUnavailable('stdio', 'could not open %s (%s)' % (path, _err()))
            return h

        def launch(self, argv, *, cwd, env, profile, job, stdin, stdout):
            """Create suspended inside the identity, assign to the Job, resume: there is
            no instant between the process existing and being confined and supervised.

            The child inherits *stdin* and *stdout* and nothing else of Core's: they are
            the whole PROC_THREAD_ATTRIBUTE_HANDLE_LIST, and inheritable only while
            CreateProcessW runs. A process created and then not confined or not resumed
            is terminated, and its handle rides on the error as `child`, so the end path
            waits on that process and never on a PID that may name another by then."""
            command = subprocess.list2cmdline([str(a) for a in argv])
            stdio = list(dict.fromkeys((stdin, stdout)))  # stderr is stdout's own handle
            listed = (W.HANDLE * len(stdio))(*stdio)       # read by CreateProcessW: kept alive
            size = C.c_size_t(0)
            _InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
            keep = (C.c_byte * size.value)()
            _win(_InitializeProcThreadAttributeList(keep, 2, 0, C.byref(size)),
                 'InitializeProcThreadAttributeList')
            psid = C.c_void_p()
            hr = _DeriveAppContainerSidFromAppContainerName(profile, C.byref(psid))
            caps = _CAPS()
            try:
                if hr != 0:
                    raise IsolationUnavailable('profile_derive', 'hr=%s' % hex(hr & 0xFFFFFFFF))
                caps.AppContainerSid = psid
                caps.Capabilities = None                   # §4.9: zero capabilities,
                caps.CapabilityCount = len(CAPABILITIES)   # and none of them a network one
                caps.Reserved = 0
                _win(_UpdateProcThreadAttribute(keep, 0, ATTR_SECURITY_CAPABILITIES,
                                                C.byref(caps), C.sizeof(caps), None, None),
                     'UpdateProcThreadAttribute(SECURITY_CAPABILITIES)')
                _win(_UpdateProcThreadAttribute(keep, 0, ATTR_HANDLE_LIST, C.byref(listed),
                                                C.sizeof(listed), None, None),
                     'UpdateProcThreadAttribute(HANDLE_LIST)')
                sia = _SIEX()
                sia.StartupInfo.cb = C.sizeof(_SIEX)
                sia.StartupInfo.dwFlags = STARTF_USESTDHANDLES
                sia.StartupInfo.hStdInput = stdin
                sia.StartupInfo.hStdOutput = stdout
                sia.StartupInfo.hStdError = stdout
                sia.lpAttributeList = C.cast(keep, C.c_void_p)
                flags = (EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | DETACHED_PROCESS
                         | CREATE_UNICODE_ENVIRONMENT)
                # the environment is the explicit block `base.spawn` merged (the
                # capability removals of P11 are part of the boundary), never an
                # inherited accident (§5.1). Each entry is null-terminated; the block
                # is double-null-terminated by the buffer's own terminator (an extra
                # trailing null is a malformed block: ERROR_ENVVAR_NOT_FOUND, 203)
                block = ''.join('%s=%s\0' % kv for kv in sorted(env.items()))
                ebuf = C.create_unicode_buffer(block)
                pi = _PI()
                # inheritable for this call alone, and each flag put back whatever it
                # answers. bInheritHandles must be TRUE for the list to apply; the list
                # is what limits it to these handles
                prior = [self._handle_flags(h) & HANDLE_FLAG_INHERIT for h in stdio]
                try:
                    for h in stdio:
                        _win(_SetHandleInformation(h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT),
                             'SetHandleInformation(inherit)')
                    created = _CreateProcessW(None, command, None, None, True, flags,
                                              C.cast(ebuf, C.c_void_p), cwd, C.byref(sia),
                                              C.byref(pi))
                    code = None if created else _err()
                finally:
                    for h, was in zip(stdio, prior):
                        _SetHandleInformation(h, HANDLE_FLAG_INHERIT, was)
                if not created:
                    if code == 203:                       # ERROR_ENVVAR_NOT_FOUND
                        raise IsolationUnavailable(
                            'environment_block',
                            'the explicit environment block was refused (spike §5.1)')
                    raise _WinFail('CreateProcessW(%s)' % command[:120], code)
                try:
                    _win(_AssignProcessToJobObject(job, pi.hProcess),
                         'AssignProcessToJobObject')
                    # the previous suspend count: (DWORD)-1 is a failure, 0 means the
                    # thread was not suspended at all, and more than 1 means it still is.
                    # Only 1 is CREATE_SUSPENDED's own suspension, lifted
                    count = _ResumeThread(pi.hThread)
                    if count == 0xFFFFFFFF:
                        raise _WinFail('ResumeThread', _err())
                    if count != 1:
                        raise IsolationUnavailable('process_resume',
                                                   'previous suspend count %d, not 1' % count)
                except Exception as err:
                    _TerminateProcess(pi.hProcess, 0xC0000142)
                    err.child = IsolatedProcess(self, pi.dwProcessId, pi.hProcess, pi.hThread)
                    raise
                child = IsolatedProcess(self, pi.dwProcessId, pi.hProcess, pi.hThread)
            finally:
                _DeleteProcThreadAttributeList(keep)
                if psid:
                    _LocalFree(psid)
            return child

    class IsolatedProcess:
        """What the isolated launch returns in place of a `Popen`: the same few things
        the adapters and the contract use (`pid`, `poll`, `wait`, `kill`,
        `returncode`). The Job, not this handle, is the lifetime authority (§3.7)."""

        def __init__(self, api, pid, hprocess, hthread):
            self._api, self.pid = api, pid
            self._p, self._t, self._rc = hprocess, hthread, None

        def poll(self):
            code = W.DWORD(0)
            if not _GetExitCodeProcess(self._p, C.byref(code)):
                return self._rc
            if code.value == STILL_ACTIVE:
                return None
            self._rc = code.value
            return self._rc

        @property
        def returncode(self):
            return self.poll()

        def wait(self, timeout=None):
            ms = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
            _WaitForSingleObject(self._p, ms)
            return self.poll()

        def kill(self):
            _TerminateProcess(self._p, 1)

        def terminate(self):
            self.kill()
else:
    WindowsBoundary = None
    IsolatedProcess = None
