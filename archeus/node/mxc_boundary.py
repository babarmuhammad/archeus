"""The production MXC boundary: the OS facts `Isolation` reads, and the launch, for a
process on the MXC base container (ADR-0053 F1a, MXC-R10).

No OS principal is created here and nothing writes an ACL. Core's side of the identity is
a name it reserves, and the grants are the path lists of the policy it compiles. The six
§3.4 conditions mean this, and a mapping marked INFERRED has no native evidence yet:

1 identity        the execution's name is reserved, and only while every earlier process
                  generation of it in the ledger ended with a completion; its marker,
                  `psec:<profile>`, is the one it derives. INFERRED: there is no S-1-15-2
                  SID on this tier, so the marker is never written where a SID is claimed
                  (`isolation.registry_sid`).
2 grants          each row is one the policy can list at that access (`rw`, `rx`), and the
                  hardlink gate passes on it. A row is registered for the launch only by
                  being verified here, so a launch never grants more than the plan.
3 no broad grants no broad principal can write inside a granted path (a DACL read), no
                  Core-owned path is reachable through a granted one, and no capability is
                  requested. INFERRED: the compiler admits none without a proxy.
4 job             the Core-held Job, read through the existing Win32 code.
5 mailbox         classes 1 to 3 are separate granted paths and Core-owned state is not
                  reachable (mapping 3's reachability).
6 isolated path   `available()`: the native api, the reviewed pins verified against the
                  staged SDK, the ledger and the pinned schema validator are all present,
                  and native admission is open (`mxc.NATIVE_RUN_ENABLED`, closed at the
                  tip, so this boundary is unavailable until the activation).

Deleting a profile releases the name and records that an MXC registration may remain.
Core neither enumerates nor removes those registrations (MXC-R10), so absence of the
name is all `profile_exists` ever answers.
"""

import itertools
import json
import math
import os
import subprocess
import time

from . import isolation as iso
from . import local, mxc, mxc_ledger, mxc_verifier, staging
from .isolation import IsolationUnavailable
from .mxc_context import MxcIsolationContext

#: file in the ledger's directory, not a journal (the ledger reads only `.jsonl`)
RESIDUE = 'registration-residue.log'
MARKER = 'psec:'


def launcher_exit(process):
    """OD-2 (a): the launcher's exit classifies an end. Whether the task succeeded is
    Core's own verification, never this number."""
    return process.launcher_exit


def _same(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class MxcBoundary:
    id = 'mxc'
    #: what `Isolation.request` hands `base.spawn`: the MXC transport owns the child's stdio
    context = MxcIsolationContext

    def __init__(self, *, win32=None, ledger=None, sdk_root=None, pins=None,
                 schema_validator=None, jobs=None, outcome=launcher_exit, timeout_ms=None,
                 env_rows=None, broker=None, resource_reader=None, readback=None,
                 watchdog=None, clock=time.time, process_reader=None):
        self.win32, self.ledger, self.sdk_root, self.pins = win32, ledger, sdk_root, pins
        self.schema_validator, self.outcome, self.timeout_ms = schema_validator, outcome, timeout_ms
        #: pid -> the creation time of the process now running under it, in the encoding
        #: of the ledger's ownership record, or None: what a restart reads a journal by
        self.process_reader = process_reader
        self.env_rows = dict(env_rows or {})
        self.broker, self.resource_reader = broker, resource_reader
        self.readback, self.watchdog, self.clock = readback, watchdog, clock
        self.jobs = jobs if jobs is not None else (
            iso.WindowsBoundary() if iso.WINDOWS else iso.UnavailableBoundary())
        self._reserved = {}                 # key -> [(path, access)] verified for the launch

    def available(self):
        if (mxc.NATIVE_RUN_ENABLED is not True or not callable(self.schema_validator)
                or any(part is None for part in (self.win32, self.ledger, self.sdk_root,
                                                 self.pins, self.process_reader))):
            return False
        try:
            staging.verify_mxc(self.sdk_root, pins=self.pins)
        except staging.StageError:
            return False
        return True

    def reconcile(self):
        """Every journal this Core is not running read for an end nobody verified: the
        ledger quarantines the ones it cannot prove dead, and answers each journal's
        state. Nothing is read without a way to read a process."""
        if self.ledger is None or self.process_reader is None:
            return {}
        return self.ledger.reconcile(self.process_reader, self.resource_reader or (
            lambda execution_id, owner: None), skip=local.mxc_busy(self.ledger))

    # ── the identity: a reserved name, no OS object ──

    def derive_sid(self, execution_id):
        return MARKER + iso.validated_profile(execution_id)

    def _generations(self, key):
        """The journals of *key*'s process generations, in order, each with its ops (empty
        when it cannot be read): the names run from `-p1` and stop at the first absent."""
        if self.ledger is None:
            raise IsolationUnavailable('mxc_ledger', 'no ledger')
        journals, out = self.ledger.journals(), []
        for n in itertools.count(1):
            name = mxc_ledger.journal_name(key, n)
            if name not in journals:
                return out
            records, invalid = mxc_ledger.read_records(journals[name], name)
            out.append((name, [] if invalid else [r['op'] for r in records]))

    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        key = iso.principal(execution_id).key
        unresolved = [n for n, ops in self._generations(key) if ops[-1:] != ['completion']]
        if unresolved:
            raise IsolationUnavailable('generation_unresolved',
                                       '%s did not end with a completion' % unresolved[0])
        existed = key in self._reserved
        self._reserved[key] = []
        return {'profile': name, 'sid': self.derive_sid(key), 'created': True,
                'existed': existed, 'package_dir': ''}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        key = iso.principal(execution_id).key
        if self.ledger is None:
            raise IsolationUnavailable('mxc_ledger', 'no ledger')
        line = {'op': 'registration_residue', 'execution_id': key, 'profile': name,
                'reason': 'MXC-R10: an MXC registration may remain, Core neither lists '
                          'nor removes it', 'at': self.clock()}
        try:
            with open(os.path.join(self.ledger.root, RESIDUE), 'a', encoding='utf-8') as f:
                f.write(json.dumps(line, sort_keys=True) + '\n')
        except OSError as err:
            raise IsolationUnavailable('residue_unrecorded', str(err)) from err
        self._reserved.pop(key, None)

    def profile_exists(self, execution_id):
        return iso.principal(execution_id).key in self._reserved

    # ── the grants: the policy's path lists ──

    def _key_of(self, sid):
        return next((key for key in self._reserved if self.derive_sid(key) == sid), None)

    def grant_established(self, path, sid, access):
        key = self._key_of(sid)
        if key is None or access not in ('rw', 'rx'):
            return False
        try:
            mxc.scan_grant(path)
        except mxc.MxcUnavailable:
            return False
        self._reserved[key].append((os.path.normpath(path), access))
        return True

    def granted_to(self, path, sid):
        key = self._key_of(sid)
        return key is None or any(iso._within(path, granted) for granted, _ in self._reserved[key])

    def broad_write_grant(self, path, sid):
        return self.jobs.broad_writer(path)

    def capability_grants(self):
        return ()

    # ── the Job: the existing Win32 code ──

    def create_job(self, execution_id):
        return self.jobs.create_job(execution_id)

    def job_facts(self, handle):
        return self.jobs.job_facts(handle)

    def job_active_processes(self, job):
        return self.jobs.job_active_processes(job)

    def assign_job(self, job, process_handle):
        return self.jobs.assign_job(job, process_handle)

    def terminate_job(self, job):
        return self.jobs.terminate_job(job)

    def close_job(self, job):
        return self.jobs.close_job(job)

    def process_started(self, pid):
        return self.jobs.process_started(pid)

    def open_inherited(self, path, mode):
        return self.jobs.open_inherited(path, mode)

    def close_handle(self, handle):
        return self.jobs.close_handle(handle)

    # ── the launch ──

    def _environment(self, env):
        have = {name.upper() for name in env}
        return {**env, **{k: v for k, v in self.env_rows.items() if k.upper() not in have}}

    def launch(self, argv, *, cwd, env, profile, job, stdin, stdout, timeout_ms=None,
               transport=None):
        """`stdin` and `stdout` are the Core-opened handles the detached path hands a
        child. The MXC transport owns the child's stdio, so they are not used here. The
        deadline and the transport's bounds are the launch's own, or the boundary's."""
        launch = self._launch(argv, cwd, env, profile,
                              self.timeout_ms if timeout_ms is None else timeout_ms,
                              transport)
        launch.start(job=job)
        return launch

    def launch_confined(self, argv, *, cwd, env, profile, job, timeout, stdin_path, out_path):
        """A verifier check: the transport's own streams are drained into *out_path*, up
        to the cap that file is held to, by the child this returns (`mxc_verifier`)."""
        launch = self._launch(argv, cwd, env, profile, math.ceil(timeout * 1000),
                              transport={'output_limit': iso.CONFINED_OUT_MAX,
                                         'total_limit': iso.CONFINED_OUT_MAX})
        launch.start(job=job)
        try:
            return mxc_verifier.ConfinedChild(launch, timeout, stdin_path, out_path)
        except BaseException:               # a started launcher nobody drains is ended here
            launch.cancel(reason='the confined child failed to start')
            raise

    def _launch(self, argv, cwd, env, profile, timeout_ms, transport=None):
        key = next((k for k in self._reserved if iso.profile_name(k) == profile), None)
        if key is None:
            raise IsolationUnavailable('profile_unknown', '%s was not reserved' % profile)
        if timeout_ms is None:
            raise IsolationUnavailable('mxc_timeout', 'no process deadline was given')
        granted = self._reserved[key]
        writable = list(dict.fromkeys(p for p, access in granted if access == 'rw'))
        workspace = next((p for p in writable if _same(p, cwd)), None)
        if workspace is None:
            raise IsolationUnavailable('mxc_policy', 'the working directory is not a writable grant')
        return local.MxcLaunch(
            sdk_root=self.sdk_root, pins=self.pins, outcome=self.outcome, workspace=workspace,
            writable=[p for p in writable if p != workspace],
            readonly=list(dict.fromkeys(p for p, access in granted if access == 'rx')),
            cwd=cwd, command_line=subprocess.list2cmdline(argv), env=self._environment(env),
            timeout_ms=timeout_ms, api=self.win32, boundary=self, ledger=self.ledger,
            schema_validator=self.schema_validator, execution_id=key,
            process_seq=len(self._generations(key)) + 1, broker=self.broker,
            resource_reader=self.resource_reader, readback=self.readback,
            watchdog=self.watchdog, transport=transport)
