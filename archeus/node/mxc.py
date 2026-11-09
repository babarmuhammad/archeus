"""Closed MXC policy seam. Native execution requires an explicitly injected backend.

UNVERIFIED: no pin is recorded yet (mxc_pins.json holds UNSET), so no schema
validator can be built, and native identity/resource read-back, streaming and owned
disposal contract are not supplied. Validation below covers the documented closed
policy subset; it is not certification by the pinned schema artifact.
F1 establishes host-user tokens plus PSEC, not distinct AppContainer SIDs.
"""

import copy
import io
import ipaddress
import json
import os
import stat
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from . import linkscan


NATIVE_RUN_ENABLED = False
#: the one desktop posture beyond blocked (OD-1 default a): node, git and powershell fail
#: 0xC0000142 with the UI subsystem off (F4). Only the clipboard and injection stay closed;
#: a caller names it for a code_change execution, never as a default or as a retry
UI_CODE_CHANGE = 'code_change'
#: the container capabilities a loopback proxy route may carry; F3 measured this one. Another
#: needs a reviewed bump here and in the evidence, never a caller's choice
CAPABILITIES = ('internetClient',)


class MxcUnavailable(ValueError):
    pass


def _text(value):
    return isinstance(value, str) and bool(value) and '\0' not in value


def _path(value):
    try:
        value = os.fspath(value)
    except TypeError:
        raise MxcUnavailable('policy paths must be absolute') from None
    if not _text(value) or not os.path.isabs(value):
        raise MxcUnavailable('policy paths must be absolute')
    value = os.path.normpath(value)
    if os.name == 'nt':
        # commonpath raises across \?\, UNC and rooted forms, which would skip the overlap
        # gates; Windows also resolves `ws.`, `ws ` and `ws::$INDEX_ALLOCATION` to `ws`, which
        # those string comparisons read as another path
        drive, rest = os.path.splitdrive(value)
        if (not (len(drive) == 2 and drive[0].isascii() and drive[0].isalpha() and drive[1] == ':')
                or ':' in rest or any(s[-1] in '. ' for s in rest.split('\\') if s)):
            raise MxcUnavailable('policy paths must be plain drive paths')
    return value


def _within(path, parent):
    try:
        return os.path.commonpath([os.path.normcase(path), os.path.normcase(parent)]) == os.path.normcase(parent)
    except ValueError:
        return False


def scan_grant(root):
    """Refuse aliases, unreadable entries and multiply linked regular files.

    F2: MXC grants paths, so a hardlink can expose an outside file. Repeated
    scans reduce exposure but do not eliminate concurrent host mutation races.
    """
    root = _path(root)
    ancestor = os.path.dirname(root)
    while ancestor:
        try:
            info = os.lstat(ancestor)
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, 'st_file_attributes', 0) & 0x400):
                raise MxcUnavailable('alias in grant ancestor: %s' % ancestor)
        except OSError as err:
            raise MxcUnavailable('unreadable grant ancestor: %s' % ancestor) from err
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent
    linkscan.check_grants((root,), MxcUnavailable)
    pending = [root]
    while pending:
        path = pending.pop()
        try:
            info = os.lstat(path)
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, 'st_file_attributes', 0)
                    & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
                raise MxcUnavailable('alias in grant: %s' % path)
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as entries:
                    pending.extend(entry.path for entry in entries)
            elif not stat.S_ISREG(info.st_mode):
                raise MxcUnavailable('unsupported grant object: %s' % path)
        except OSError as err:
            raise MxcUnavailable('unreadable grant: %s' % path) from err


@dataclass(frozen=True)
class MxcPolicy:
    raw: dict

    def __post_init__(self):
        object.__setattr__(self, 'raw', copy.deepcopy(self.raw))
        validate_policy(self)


def _capabilities(value, proxy):
    """The capability list, sorted: a route needs its capability and nothing else may
    carry one, so a named set is checked and an absent one is the route's own."""
    if value is None:
        return list(CAPABILITIES) if proxy else []
    if isinstance(value, (str, bytes)) or not hasattr(value, '__iter__'):
        raise MxcUnavailable('capabilities must be a list of names')
    value = list(value)
    if (bool(value) != bool(proxy) or len(set(map(str, value))) != len(value)
            or any(c not in CAPABILITIES for c in value)):
        raise MxcUnavailable('capabilities must be the reviewed set, and only with a proxy')
    return sorted(value)


def compile_policy(*, workspace, readonly=(), denied=(), cwd, command_line, env=None,
                   timeout_ms, ui=False, egress='deny', proxy_url=None, capabilities=None):
    """Compile only Core-owned inputs; never inherit the host environment."""
    if isinstance(workspace, (str, os.PathLike)):
        writable = (workspace,)
    else:
        try:
            writable = tuple(workspace)
        except TypeError:
            raise MxcUnavailable('workspace must be a path or paths') from None
    if (ui is not False and ui != UI_CODE_CHANGE) or egress != 'deny':
        raise MxcUnavailable('unsupported UI or egress policy')
    capabilities = _capabilities(capabilities, proxy_url is not None)
    if env is None:
        env = {}
    if not isinstance(env, dict) or any(not _text(k) or '=' in k or not isinstance(v, str)
                                        or '\0' in v for k, v in env.items()):
        raise MxcUnavailable('invalid explicit environment')
    names = [k.upper() for k in env]
    if len(set(names)) != len(names) or not {'SYSTEMROOT', 'LOCALAPPDATA'} <= set(names):
        raise MxcUnavailable('explicit SYSTEMROOT and LOCALAPPDATA required')
    raw = {
        'version': '1.0.0', 'containment': 'processcontainer',
        'lifecycle': {'destroyOnExit': True, 'preservePolicy': False},
        'process': {'commandLine': command_line, 'cwd': _path(cwd),
                    'env': ['%s=%s' % item for item in sorted(env.items())],
                    'inheritDefaultEnv': False, 'timeout': timeout_ms},
        'filesystem': {'readwritePaths': [_path(p) for p in writable],
                       'readonlyPaths': [_path(p) for p in readonly],
                       'deniedPaths': [_path(p) for p in denied]},
        'network': {'egress': {'default': 'deny'},
                    'ingress': {'default': 'deny', 'hostLoopback': 'deny'}},
        'ui': {'disable': ui is False, 'clipboard': 'none', 'injection': False},
        'telemetry': {'enabled': False},
    }
    if proxy_url is not None:
        try:
            url = urlsplit(proxy_url)
            valid = (url.scheme == 'http' and ipaddress.ip_address(url.hostname).is_loopback
                     and url.port and not url.username and not url.password
                     and url.path in ('', '/') and not url.query and not url.fragment)
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise MxcUnavailable('proxy must be an explicit loopback HTTP endpoint')
        raw['network']['ingress'] = {'default': 'allow', 'hostLoopback': 'allow'}
        raw['runtimeConfig'] = {'networkProxy': proxy_url}
        raw['processContainer'] = {'capabilities': capabilities}
    return MxcPolicy(raw)


def validate_policy(policy):
    """Validate the exact compiler output, including mutations before launch."""
    if not isinstance(policy, MxcPolicy) or not isinstance(policy.raw, dict):
        raise MxcUnavailable('MxcPolicy object required')
    raw = policy.raw
    try:
        required = {'version', 'containment', 'lifecycle', 'process', 'filesystem',
                    'network', 'ui', 'telemetry'}
        proxy = 'runtimeConfig' in raw
        if set(raw) != required | ({'runtimeConfig', 'processContainer'} if proxy else set()):
            raise ValueError('unknown or missing policy fields')
        if raw['version'] != '1.0.0' or raw['containment'] != 'processcontainer':
            raise ValueError('wrong schema or backend')
        if (set(raw['lifecycle']) != {'destroyOnExit', 'preservePolicy'}
                or raw['lifecycle']['destroyOnExit'] is not True
                or raw['lifecycle']['preservePolicy'] is not False):
            raise ValueError('unsafe lifecycle')
        p = raw['process']
        if (set(p) != {'commandLine', 'cwd', 'env', 'inheritDefaultEnv', 'timeout'}
                or not _text(p['commandLine']) or p['inheritDefaultEnv'] is not False
                or type(p['timeout']) is not int or p['timeout'] <= 0
                or not isinstance(p['env'], list)):
            raise ValueError('invalid process policy')
        env = {}
        for item in p['env']:
            if not _text(item) or '=' not in item:
                raise ValueError('invalid environment entry')
            key, value = item.split('=', 1)
            if not key or key.upper() in env:
                raise ValueError('duplicate environment entry')
            env[key.upper()] = value
        if not all(env.get(k) for k in ('SYSTEMROOT', 'LOCALAPPDATA')):
            raise ValueError('explicit SYSTEMROOT and LOCALAPPDATA required')
        fs = raw['filesystem']
        if set(fs) != {'readwritePaths', 'readonlyPaths', 'deniedPaths'}:
            raise ValueError('invalid filesystem policy')
        for paths in fs.values():
            if not isinstance(paths, list) or len(set(paths)) != len(paths):
                raise ValueError('duplicate or invalid paths')
            for path in paths:
                if _path(path) != path:
                    raise ValueError('noncanonical path')
        rw, ro, denied = (fs[k] for k in ('readwritePaths', 'readonlyPaths', 'deniedPaths'))
        if (not rw or not os.path.isdir(p['cwd'])
                or not any(_within(_path(p['cwd']), path) for path in rw + ro)):
            raise ValueError('cwd outside grants')
        if any(_within(a, b) or _within(b, a) for a in rw for b in ro + denied):
            raise ValueError('writable grant overlaps protected path')
        if any(_within(a, b) or _within(b, a) for a in ro for b in denied):
            raise ValueError('readonly grant overlaps denied path')
        ingress = {'default': 'allow', 'hostLoopback': 'allow'} if proxy else {
            'default': 'deny', 'hostLoopback': 'deny'}
        if raw['network'] != {'egress': {'default': 'deny'}, 'ingress': ingress}:
            raise ValueError('unsafe network policy')
        if proxy:
            if (set(raw['runtimeConfig']) != {'networkProxy'}
                    or set(raw['processContainer']) != {'capabilities'}):
                raise ValueError('invalid proxy policy')
            caps = raw['processContainer']['capabilities']
            try:
                valid = caps == _capabilities(caps, True)
            except MxcUnavailable:
                valid = False
            if not valid:
                raise ValueError('invalid proxy policy')
            url = urlsplit(raw['runtimeConfig']['networkProxy'])
            if not (url.scheme == 'http' and ipaddress.ip_address(url.hostname).is_loopback
                    and url.port and not url.username and not url.password
                    and url.path in ('', '/') and not url.query and not url.fragment):
                raise ValueError('invalid proxy endpoint')
        if (set(raw['ui']) != {'disable', 'clipboard', 'injection'}
                or type(raw['ui']['disable']) is not bool
                or raw['ui']['clipboard'] != 'none' or raw['ui']['injection'] is not False
                or set(raw['telemetry']) != {'enabled'}
                or raw['telemetry']['enabled'] is not False):
            raise ValueError('unsafe UI or telemetry')
        json.dumps(raw, allow_nan=False)
        for path in rw + ro:
            scan_grant(path)
    except (KeyError, TypeError, ValueError, OSError) as err:
        raise MxcUnavailable('invalid MXC policy: %s' % err) from err


class MxcProcess(Protocol):
    pid: int
    create_time: int
    stdin: object
    stdout: object
    stderr: object

    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...
    def is_alive(self) -> bool: ...
    def identity_reader(self, proc) -> 'IdentityReport': ...


@dataclass(frozen=True)
class IdentityReport:
    pid: int
    create_time: int
    user_sid: str
    is_appcontainer: bool
    ac_sid: str | None
    integrity: str
    backend: str
    tier: str
    capability_sids: tuple = ()


def effective_identity(proc: MxcProcess) -> IdentityReport:
    report = proc.identity_reader(proc)
    if (not isinstance(report, IdentityReport) or report.pid != proc.pid
            or type(report.create_time) is not int or report.create_time <= 0
            or report.create_time != proc.create_time or proc.is_alive() is not True
            or not report.user_sid or not report.integrity
            or report.backend != 'processcontainer' or report.tier != 'base-container'
            or report.is_appcontainer or report.ac_sid or report.capability_sids):
        raise MxcUnavailable('dead, reused or unverified process identity')
    return report


def spawn(policy: MxcPolicy, *, exe, job, backend=None, native_run=False) -> MxcProcess:
    validate_policy(policy)
    if backend is None or (not isinstance(backend, FakeMxc)
                           and not (NATIVE_RUN_ENABLED and native_run)):
        raise MxcUnavailable('native MXC execution disabled')
    if job is None:
        raise MxcUnavailable('Core-held Job required')
    return backend.spawn(policy, exe=exe, job=job)


class NativeMxc:
    """Ordering contract for an injected, reviewed native implementation.

    UNVERIFIED: no concrete Win32/CLI transport or resource disposal adapter is
    admitted here. The transport owns retained handles and explicit stdio only.
    """
    def __init__(self, transport, schema_validator, *, switches=None):
        self.switches = switches
        self.transport, self.schema_validator = transport, schema_validator

    def spawn(self, policy, *, exe, job, before_resume=None):
        """The seam the ledger needs: `before_resume` runs after membership has been
        verified and before the single resume, so the ownership facts are durable
        before the launcher can run. A hook that raises never resumes: the suspended
        child is terminated and retained for Core to quarantine, exactly as for any
        other fault in this sequence."""
        if not (self.switches.native_run if self.switches is not None else NATIVE_RUN_ENABLED):
            raise MxcUnavailable('native MXC execution disabled')
        validate_policy(policy)
        try:
            accepted = self.schema_validator(policy.raw) is True
        except Exception:
            accepted = False
        if not accepted:
            raise MxcUnavailable('pinned schema validation failed')
        if job is None:
            raise MxcUnavailable('Core-held Job required')
        launcher = _path(exe)
        # The transport stages a protected policy file and creates only suspended.
        policy_path = self.transport.stage_policy(policy.raw)
        child = self.transport.create_suspended(
            [launcher, '--debug', policy_path], policy=policy)
        try:
            self.transport.assign_job(job, child)
            if self.transport.in_job(job, child) is not True:
                raise MxcUnavailable('launcher Job membership unverified')
            if before_resume is not None:
                before_resume(child)
            resumed = self.transport.resume(child)
            if type(resumed) is not int or resumed != 1:
                raise MxcUnavailable('launcher did not resume exactly once')
        except BaseException as err:
            # Retain the child even when termination fails; Core must quarantine it.
            err.child = child
            try:
                child.terminate()
                child.wait(5)
            except Exception as cleanup:
                err.cleanup_error = cleanup
            raise
        return child


@dataclass(frozen=True)
class FakeOutcome:
    launcher_exit: int = 0
    agent_outcome: object = None
    stdout: bytes = b''
    stderr: bytes = b''


class FakeProcess:
    def __init__(self, outcome, pid):
        self.pid, self.create_time = pid, pid * 100
        self.agent_outcome = outcome.agent_outcome
        self._exit, self._alive = outcome.launcher_exit, True
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(outcome.stdout), io.BytesIO(outcome.stderr)
        self.identity_reader = lambda proc: IdentityReport(
            proc.pid, proc.create_time, 'S-1-5-21-fake', False, None, '0x2000',
            'processcontainer', 'base-container')

    def is_alive(self):
        return self._alive

    def wait(self, timeout=None):
        self._alive = False
        return self._exit

    def poll(self):
        return None if self._alive else self._exit

    @property
    def returncode(self):
        return self.poll()

    def terminate(self):
        self._exit, self._alive = 1, False

    kill = terminate


class FakeMxc:
    """Script launcher status separately from the agent's authoritative result."""
    def __init__(self, outcomes=()):
        self.outcomes = iter(outcomes)
        self.calls = []
        self.events = []

    def spawn(self, policy, *, exe, job, before_resume=None):
        validate_policy(policy)
        if job is None:
            raise MxcUnavailable('Core-held Job required')
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        proc = FakeProcess(outcome, 1000 + len(self.calls))
        self.calls.append((policy, exe, job))
        # the same ordering the transport owes: ownership is recorded before the resume
        self.events.extend(('create_suspended', 'assign_job', 'verify_job'))
        if before_resume is not None:
            before_resume(proc)
        self.events.append('resume')
        return proc
