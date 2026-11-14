import io
import http.server
import itertools
import json
import multiprocessing
import os
import re
import socket
import stat
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from tools.pv20_mxc.native import n2_check as n2
from tools.pv20_mxc.native.common import Recorder, StopRun, redact, safe_root
from tools.pv20_mxc.protocol import STAGES

STAGE = 'N3'
CASES = STAGES[STAGE].cases
AUTHORIZATION = 'N3b-owner-authorization.json'
SCOPES = ('fixture-files', 'mxc-profiles', 'jobs-processes', 'loopback-ipv4-ipv6',
          'synthetic-broker', 'fixture-core-death', 'launcher-death')
PROD = ('archeus.api.origin', 'archeus.api.server', 'archeus.api.routes',
        'archeus.node.origin_native', 'archeus.node.origin_windows',
        'archeus.node.broker', 'archeus.node.broker_listener')
MODEL = 'fixture-model'


def authorization(parent, filename, scopes):
    if not n2.parent_ok(parent):
        raise n2.SetupError('noncanonical fixture parent')
    path = os.path.join(parent, filename)
    cursor = parent
    while os.path.dirname(cursor) != cursor:
        if getattr(os.lstat(cursor), 'st_file_attributes', 0) & 0x400 or os.path.islink(cursor):
            raise n2.SetupError('authorization parent is an alias')
        cursor = os.path.dirname(cursor)
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8192
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        raise n2.SetupError('authorization marker is an alias')
    with open(path, encoding='utf-8') as stream:
        data = json.loads(stream.read(8193))
    if (set(data) != {'authorization_id', 'script', 'scopes', 'approved'}
            or data['script'] != filename.removesuffix('-owner-authorization.json')
            or data['approved'] is not True
            or not isinstance(data['authorization_id'], str)
            or re.fullmatch(r'[A-Za-z0-9_-]{1,64}', data['authorization_id']) is None
            or data['scopes'] != list(scopes)):
        raise n2.SetupError('explicit owner authorization missing or scope differs')
    return data['authorization_id']


class Evidence(Recorder):
    def __init__(self, stage, root, authorization_id):
        super().__init__(stage)
        self.path = os.path.join(root, stage.lower() + '_review_evidence.jsonl')
        self.authorization_id = authorization_id

    def record(self, case, status, detail=''):
        row = {'stage': self.stage, 'case': case, 'status': status,
               'script': 'N3b' if self.stage == 'N3' else self.stage,
               'authorization_id': self.authorization_id, 'detail': redact(detail),
               'timestamp': time.time()}
        with open(self.path, 'a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(row) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        super().record(case, status, detail)


def require(rec, case, ok, detail):
    rec.record(case, 'PASS' if ok else 'FAIL', detail)


class Response:
    reason = 'fixture'

    def __init__(self, status=200, body=b'fixture-response'):
        self.status, self.body = status, io.BytesIO(body)

    def getheaders(self):
        return [('Content-Type', 'application/json'), ('Location', 'http://127.0.0.1:1/')]

    def read1(self, size):
        return self.body.read(size)


class ObservedBackend:
    def __init__(self, backend, observations):
        self.backend, self.observations = backend, observations

    def attest(self, context):
        evidence = self.backend.attest(context)
        self.observations.append((context, evidence))
        return evidence

    def valid(self, context, evidence):
        return self.backend.valid(context, evidence)

    def release(self, context, evidence):
        self.backend.release(context, evidence)


class Harness(n2.Harness):
    def prepare(self):
        super().prepare()
        modules = n2.import_isolated(PROD, self.lay['envhome'])
        self.p = SimpleNamespace(**{name.rsplit('.', 1)[1]: mod
                                  for name, mod in modules.items()})
        self.origin_api = self.p.origin_native.Win32OriginApi()
        self.observations, self.forwarded = [], []
        self.backends = {}
        self.response_status, self.response_body = 200, b'fixture-response'
        self.curl = os.path.join(self.env['SYSTEMROOT'], 'System32', 'curl.exe')
        self.work = self.lay['p']['state']
        self.principals = {}
        self.broker = self.p.broker_listener.loopback_broker(
            backend_of=self.backend, principal_of=self.principal_of,
            core_instance='fixture_core', live=lambda binding, digest: True,
            credentials=lambda binding: {'x-api-key': 'sk-ant-api03-FIXTURE_ONLY'},
            upstream_of=lambda account: self.p.broker.Upstream(
                'http://127.0.0.1:1', 'provider_proxy'),
            limits=self.p.broker.BrokerLimits(max_requests=5), send=self.send)

    def backend(self, port):
        readers = self.p.origin_native.native_readers(
            self.origin_api, core_port=port,
            jobs=lambda: [job.handle for job in self.jobs if job.handle], reattest=True)
        backend = ObservedBackend(self.p.origin_windows.WindowsOriginBackend(readers=readers),
                                  self.observations)
        self.backends[port] = backend
        return backend

    def principal_of(self, evidence):
        binding = evidence.process_binding
        for handle, principal in self.principals.items():
            process = self.origin_api.process(binding.pid, (handle,))
            if process is not None and process.alive and process.in_jobs:
                return principal
        return None

    def send(self, up, addrs, method, path, headers, body, timeout):
        self.forwarded.append((method, path, len(body)))
        return Response(self.response_status, self.response_body)

    def grant(self, *, max_requests=32, max_body=1024, max_response=1024):
        B = self.p.broker
        eid = self.eid('broker')
        binding = B.BrokerBinding(
            core_instance='fixture_core', execution_id=eid, process_seq=1,
            principal=eid, route_decision_id='fixture_route', account_id='fixture_account',
            harness_id='claude_code', model=MODEL,
            upstream=B.Upstream('http://127.0.0.1:1', 'provider_proxy'),
            limits=B.BrokerLimits(max_requests=max_requests, max_body=max_body,
                                  max_response=max_response))
        token, digest, endpoint, port = self.broker.issue(binding)
        return SimpleNamespace(eid=eid, token=token, endpoint=endpoint, port=port)

    def start(self, tag, argv, *, port=None, principal=None):
        eid = self.eid(tag)
        launch = self.m.local.MxcLaunch(
            api=self.api, boundary=self.boundary, ledger=self.ledger,
            schema_validator=lambda raw: True, execution_id=eid,
            sdk_root=self.lay['sdk'], pins=self.pins,
            outcome=lambda process: process.launcher_exit,
            workspace=self.work, cwd=self.work, command_line=n2.command_line(argv),
            env=dict(self.env), timeout_ms=30000,
            proxy_url=('http://127.0.0.1:%d' % port) if port else None,
            resource_reader=None)
        job = self.job(eid)
        if principal:
            self.principals[job.handle] = principal
        launch.start(job=job.handle)
        return launch, job

    def request(self, grant, *, body=None, target='/v1/messages', token=None,
                extra=(), descendant=False):
        body = body if body is not None else json.dumps({'model': MODEL, 'messages': []})
        path = os.path.join(self.work, 'request_%d.json' % self.seq)
        with open(path, 'x', encoding='utf-8') as stream:
            stream.write(body)
        argv = [self.curl, '--silent', '--show-error', '--max-time', '8', '--noproxy', '*',
                '--request-target', target, '-H', 'Authorization: Bearer ' + (token or grant.token),
                '--data-binary', '@' + path, '--write-out', '\nSTATUS:%{http_code}',
                *extra, 'http://127.0.0.1:%d/' % grant.port]
        if descendant:
            argv = self.descendants(argv)
        launch, job = self.start('request', argv, port=grant.port, principal=grant.eid)
        code = launch.wait()
        output = launch.stdout.read().decode('utf-8', 'replace')
        return code, output, job

    def descendants(self, argv):
        path = os.path.join(self.work, 'descendant_%d.cmd' % self.seq)
        with open(path, 'x', encoding='ascii', newline='\r\n') as stream:
            stream.write('@echo off\n' + n2.command_line(argv).replace('%', '%%')
                         + '\nexit /b %errorlevel%\n')
        return [self.cmd, '/d', '/c', self.cmd, '/d', '/c', path]

    def wind_down(self):
        failures = 0
        try:
            if hasattr(self, 'broker'):
                self.broker.revoke_all()
        except Exception:
            failures += 1
        for job in self.jobs:
            try:
                job.close()
            except Exception:
                failures += 1
        return super().wind_down() + failures


def broker_cases(h, rec):
    host = 'host-controls'
    grant = h.grant()
    before = len(h.forwarded)
    code, output, _ = h.request(grant)
    require(rec, 'broker-reach', code == 0 and 'STATUS:200' in output
            and len(h.forwarded) == before + 1,
            'production listener/native attestor/Job principal admitted fixture request')
    require(rec, host, any(ev.origin is h.p.origin.OriginClass.EXECUTION
                          for _, ev in h.observations), 'native EXECUTION observed at accept')
    context, evidence = h.observations[-1]
    require(rec, 'pid-exit-reuse-races',
            h.backends[grant.port].valid(context, evidence) is False,
            'production binding recheck refuses client after completed container request')
    before = len(h.forwarded)
    code, output, _ = h.request(grant, descendant=True)
    require(rec, 'broker-reach', code == 0 and 'STATUS:200' in output
            and len(h.forwarded) == before + 1,
            'nested cmd descendant reaches allowed production broker as positive control')
    before = len(h.forwarded)
    host_result = subprocess.run(
        [h.curl, '--noproxy', '*', '--max-time', '5', '--silent',
         '-H', 'Authorization: Bearer ' + grant.token,
         'http://127.0.0.1:%d/api/hello' % grant.port],
        capture_output=True, timeout=10, env=dict(h.env))
    require(rec, 'wrong-peer-squatting-replacement', len(h.forwarded) == before
            and host_result.returncode != 0,
            'host child carrying correct token refused before request bytes')
    case = 'malformed-replay-destination-model-redirect-limits'
    probes = [({'body': '{'}, 400), ({'body': '{"model":"wrong"}'}, 403),
              ({'target': 'http://127.0.0.1:1/v1/messages'}, 400),
              ({'body': 'x' * 1025}, 413),
              ({'extra': ('-H', 'Content-Length: 1', '-H', 'Content-Length: 2')}, 400)]
    for options, expected in probes:
        before = len(h.forwarded)
        code, output, _ = h.request(grant, **options)
        require(rec, case, code == 0 and 'STATUS:%d' % expected in output
                and len(h.forwarded) == before, 'local refusal %d; no upstream send' % expected)
    old = grant
    h.broker.revoke(old.eid)
    replacement = h.grant()
    code, output, _ = h.request(replacement, token=old.token)
    require(rec, case, code == 0 and 'STATUS:401' in output, 'revoked token replay refused')
    h.response_status = 302
    before = len(h.forwarded)
    code, output, _ = h.request(replacement)
    require(rec, case, code == 0 and 'STATUS:502' in output
            and len(h.forwarded) == before + 1, 'redirect rejected after exactly one synthetic send')
    h.response_status = 200
    limited = h.grant(max_requests=1, max_response=4)
    h.response_body = b'abcdefgh'
    code, output, _ = h.request(limited)
    require(rec, case, code == 0 and 'STATUS:200' in output
            and len(output.partition('\nSTATUS:')[0].encode()) <= 4,
            'response ceiling cuts oversized synthetic response')
    code, output, _ = h.request(limited)
    require(rec, case, code == 0 and 'STATUS:429' in output, 'request ceiling enforced')
    h.response_body = b'fixture-response'
    rec.record(case, 'INCONCLUSIVE',
               'body, response and request ceilings measured; concurrency, idle/deadline '
               'timing and live upstream destination changes require separate read-back')


def network_cases(h, rec):
    for family, address in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
        listener = socket.socket(family)
        stop, thread = None, None
        try:
            listener.bind((address, 0))
            listener.listen(8)
            listener.settimeout(0.2)
            hits, stop = [], threading.Event()

            def serve(sock=listener, seen=hits, ended=stop):
                while not ended.is_set():
                    try:
                        conn, _ = sock.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        return
                    with conn:
                        conn.settimeout(2)
                        try:
                            conn.recv(4096)
                            seen.append(1)
                            conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
                        except OSError:
                            pass

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            port = listener.getsockname()[1]
            url = 'http://%s:%d/' % ('[::1]' if family == socket.AF_INET6 else address, port)
            control = subprocess.run([h.curl, '--noproxy', '*', '-g', '-s', '-m', '4', url],
                                     capture_output=True, timeout=8, env=dict(h.env))
            require(rec, 'host-controls', control.returncode == 0 and control.stdout == b'OK'
                    and len(hits) == 1, 'forbidden listener positive control family=%d' % family)
            for descendant in (False, True):
                before = len(hits)
                argv = [h.curl, '--noproxy', '*', '-g', '-s', '-m', '4', url]
                if descendant:
                    argv = h.descendants(argv)
                grant = h.grant()
                argv = [h.cmd, '/d', '/c', 'echo N3B_CONTROL & ' + n2.command_line(argv)]
                launch, _ = h.start('forbidden', argv, port=grant.port, principal=grant.eid)
                code = launch.wait()
                require(rec, 'forbidden-ipv4-ipv6-descendants', code == 7
                        and b'N3B_CONTROL' in launch.stdout.read() and len(hits) == before,
                        'live forbidden endpoint blocked family=%d descendant=%s' % (family, descendant))
            before = len(hits)
            argv = [h.curl, '--noproxy', '*', '-g', '-s', '-m', '4', url]
            launch, _ = h.start('denyall', [h.cmd, '/d', '/c',
                                           'echo N3B_CONTROL & ' + n2.command_line(argv)])
            require(rec, 'deny-all-both-directions', launch.wait() == 7
                    and b'N3B_CONTROL' in launch.stdout.read() and len(hits) == before,
                    'deny-all outbound refusal family=%d' % family)
        finally:
            if stop is not None:
                stop.set()
            listener.close()
            if thread is not None:
                thread.join(3)
    rec.record('deny-all-both-directions', 'INCONCLUSIVE',
               'inbound reach into container has no independently discoverable endpoint')


def matrix_cases(h, rec):
    origin = h.p.origin
    case = 'privileged-effect-origin-matrix'
    for context, evidence in list(h.observations):
        registry = origin.CorePathRegistry([context.local_endpoint[1]])
        allowed = registry.approved(context, evidence)
        if evidence.origin is not origin.OriginClass.USER:
            require(rec, case, not allowed, 'native non-USER excluded by production registry')
    for kind in origin.OriginClass:
        evidence = origin.OriginEvidence(origin=kind, path=origin.PathClass.DIRECT_LOCAL)
        for credential in (None, 'local', 'paired'):
            allowed = origin.authorize_transport(evidence, local_host=True, remote_host=False,
                                                 credential_origin=credential)
            require(rec, case, allowed == (kind is origin.OriginClass.USER and credential != 'paired'),
                    'synthetic policy matrix origin=%s credential=%s' % (kind.value, credential))
    rec.record(case, 'INCONCLUSIVE',
               'matrix exercises production registry and transport policy; application effects, '
               'real independent USER and VERIFIER producers require owner fixture API contract')
    rec.record('pid-exit-reuse-races', 'INCONCLUSIVE',
               'native requests bind PID plus creation time; forced PID recycling is not observable on demand')


def effect_cases(h, rec):
    case = 'privileged-effect-origin-matrix'
    effects = []

    class Handler(h.p.server.Handler):
        def effect(self):
            evidence = self.transport_evidence()
            credential = self.headers.get('X-Fixture-Credential')
            credential = None if credential == 'bootstrap' else credential
            approved = h.p.origin.authorize_transport(
                evidence, local_host=self.headers.get('Host') == '127.0.0.1:%d' % server.server_port,
                remote_host=False, credential_origin=credential)
            if approved:
                effects.append((self.command, self.path, credential))
            self.send_response(204 if approved else 403)
            self.send_header('Content-Length', '0')
            self.end_headers()

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = effect

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    port = server.server_port
    server.api = SimpleNamespace(instance='fixture_effect_core', origin_enforcement_enabled=True,
                                 origin_backend=h.backend(port),
                                 origin_registry=h.p.origin.CorePathRegistry([port]))
    server.accept_generations = itertools.count()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        routes = sorted({(route.method, route.path) for route in h.p.routes.ROUTES
                         if h.p.routes.CLASS.get((route.method, route.path), 'privileged')
                         in ('privileged', 'authority')})
        require(rec, case, bool(routes), 'production privileged/authority route inventory nonempty')
        probes = [(method, path, credential) for method, path in routes
                  for credential in ('bootstrap', 'local', 'paired')]
        for offset in range(0, len(probes), 6):
            batch = probes[offset:offset + 6]
            path = os.path.join(h.work, 'effects_%d.cmd' % offset)
            lines = ['@echo off', 'echo EFFECT_CONTROL']
            for index, (method, target, credential) in enumerate(batch):
                target = re.sub(r'\{[^}]+\}', 'fixture', target)
                argv = [h.curl, '--noproxy', '*', '--globoff', '--silent', '--max-time', '3',
                        '-X', method, '-H', 'X-Fixture-Credential: ' + credential,
                        '--write-out', 'EFFECT_%d:%%{http_code}' % index,
                        'http://127.0.0.1:%d%s' % (port, target)]
                # Percent signs in a batch file must survive cmd's expansion.
                lines += [n2.command_line(argv).replace('%', '%%'), 'if errorlevel 1 exit /b 31']
            lines += ['echo EFFECT_DONE', 'exit /b 0']
            with open(path, 'x', encoding='ascii', newline='\r\n') as stream:
                stream.write('\n'.join(lines) + '\n')
            observed_before = len(h.observations)
            launch, _ = h.start('effect_matrix', [h.cmd, '/d', '/c', path], port=port)
            code = launch.wait()
            output = launch.stdout.read()
            observed = [evidence for context, evidence in h.observations[observed_before:]
                        if context.local_endpoint[1] == port]
            require(rec, case, code == 0 and b'EFFECT_CONTROL' in output and b'EFFECT_DONE' in output,
                    'fixture effect batch control and completion observed')
            require(rec, case, len(observed) == len(batch)
                    and all(evidence.origin is h.p.origin.OriginClass.EXECUTION
                            for evidence in observed),
                    'every fixture effect request independently attested EXECUTION at accept')
            for index, (method, target, credential) in enumerate(batch):
                require(rec, case, ('EFFECT_%d:403' % index).encode() in output and not effects,
                        'native EXECUTION refused before fixture effect %s %s credential=%s'
                        % (method, target, credential))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def fixture_core(channel, root, sdk_src, systemroot):
    home = os.path.join(root, 'envhome')
    os.mkdir(home)
    for name in n2.HOME_VARS:
        os.environ[name] = home
    h = Harness(root, sdk_src, systemroot, n2.Budget(90))
    try:
        h.prepare()
        grant = h.grant()
        entered, release = threading.Event(), threading.Event()

        class Streaming(Response):
            def read1(self, size):
                entered.set()
                if not release.wait(20):
                    raise TimeoutError('fixture upstream stalled')
                return b''

        h.send = lambda *args: Streaming()
        h.broker._send = h.send
        path = os.path.join(h.work, 'open.json')
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump({'model': MODEL, 'messages': []}, stream)
        launch, job = h.start('open', [h.curl, '--noproxy', '*', '-s', '-m', '25',
                                      '-H', 'Authorization: Bearer ' + grant.token,
                                      '--data-binary', '@' + path,
                                      'http://127.0.0.1:%d/v1/messages' % grant.port],
                              port=grant.port, principal=grant.eid)
        if not entered.wait(15):
            raise n2.SetupError('no attested open upstream session')
        channel.send((launch.pid, launch.process.create_time, grant.port))
        command = channel.recv()
        if command == 'revoke':
            h.broker.revoke(grant.eid)
            channel.send(h.broker.reach(grant.eid) is None)
        elif command == 'launcher':
            h.api.terminate_process(launch.process.process_handle)
            channel.send(h.wait_dead(launch.pid, launch.process.create_time, 5))
        else:
            raise n2.SetupError('unknown death command')
        release.set()
        launch.wait()
        channel.send(h.wait_job(job, lambda count: count == 0, 5) == 0)
    except BaseException:
        try:
            channel.send(('error',))
        except OSError:
            pass
    finally:
        try:
            if h.wind_down():
                raise n2.SetupError('fixture Core cleanup failed')
        finally:
            channel.close()


def receive(channel, timeout=90):
    if not channel.poll(timeout):
        raise n2.SetupError('fixture Core acknowledgement timed out')
    return channel.recv()


def death_cases(h, rec):
    case = 'revocation-broker-core-death'
    context = multiprocessing.get_context('spawn')
    for mode in ('revoke', 'launcher', 'core'):
        root = safe_root(os.path.dirname(h.lay['root']))
        parent, child = context.Pipe()
        process = context.Process(target=fixture_core,
                                  args=(child, root, h.sdk_src, h.env['SYSTEMROOT']))
        process.start()
        child.close()
        launcher_handle = None
        try:
            ready = receive(parent)
            require(rec, case, isinstance(ready, tuple) and len(ready) == 3,
                    '%s: real fixture Core reached attested open session' % mode)
            pid, created, port = ready
            kernel = h.origin_api.kernel
            launcher_handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
            observed = h.origin_api.process(pid, ())
            require(rec, case, bool(launcher_handle) and observed is not None
                    and observed.alive and observed.creation_time == created,
                    'parent holds launcher handle for exact generation before death')
            if mode == 'core':
                # Process holds its own OS handle, so termination cannot target a recycled PID.
                process.terminate()
                process.join(10)
                require(rec, case, not process.is_alive()
                        and kernel.WaitForSingleObject(launcher_handle, 5000) == 0,
                        'real fixture Core death closed sole Job owner; launcher generation gone')
            else:
                parent.send(mode)
                require(rec, case, receive(parent) is True and receive(parent) is True,
                        '%s acknowledged; owned Job quiescent' % mode)
                process.join(10)
                require(rec, case, not process.is_alive() and process.exitcode == 0,
                        'fixture Core exited after bounded cleanup')
            with socket.socket() as probe:
                probe.settimeout(2)
                require(rec, case, probe.connect_ex(('127.0.0.1', port)) != 0,
                        '%s listener unavailable after end' % mode)
        finally:
            try:
                if process.is_alive():
                    process.terminate()
                    process.join(10)
                    if process.is_alive():
                        raise n2.SetupError('fixture Core survived termination')
            finally:
                try:
                    if launcher_handle:
                        h.origin_api.kernel.CloseHandle(launcher_handle)
                finally:
                    parent.close()
    rec.record(case, 'INCONCLUSIVE',
               'real killed Core is fixture composition, not activated application runtime; '
               'MXC registration disposal and descendant absence after Core death lack read-back')


def run(h, rec):
    h.prepare()
    broker_cases(h, rec)
    network_cases(h, rec)
    effect_cases(h, rec)
    matrix_cases(h, rec)
    death_cases(h, rec)
    rec.record('host-controls', 'INCONCLUSIVE',
               'SDK hashes derived from staged source; schema validator stand-in; no native token, '
               'effective-policy or registration-disposal read-back')
    if {case for case, _ in rec.results} != set(CASES):
        raise n2.SetupError('protocol row coverage incomplete')


def entry(argv, *, filename, scopes, stage, harness, runner):
    if len(argv) != 1 or not n2.parent_ok(argv[0]) or not n2._on_windows():
        return 3
    h, root, code = None, None, 3
    saved = {name: os.environ.get(name) for name in n2.HOME_VARS}
    try:
        authorization_id = authorization(argv[0], filename, scopes)
        systemroot = os.environ.get('SystemRoot', '')
        if not n2._system_ok(systemroot):
            raise n2.SetupError('SystemRoot invalid')
        root = safe_root(argv[0])
        home = os.path.join(root, 'envhome')
        os.mkdir(home)
        for name in n2.HOME_VARS:
            os.environ[name] = home
        rec = Evidence(stage, root, authorization_id)
        h = harness(root, os.path.join(argv[0], *n2.SDK_TAIL), systemroot,
                    n2.Budget(STAGES[stage].budget - 30))
        runner(h, rec)
        code = rec.exit_code()
    except StopRun:
        code = 1
    except (Exception, KeyboardInterrupt) as error:
        print('SETUP/INTERRUPT ' + type(error).__name__, flush=True)
    finally:
        try:
            try:
                if h is not None and h.wind_down():
                    code = 3
            except Exception as error:
                print('CLEANUP ERROR ' + type(error).__name__, flush=True)
                code = 3
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
    if root:
        print(redact('Fixture preserved at ' + root), flush=True)
    return code


def main(argv=None):
    return entry(sys.argv[1:] if argv is None else argv, filename=AUTHORIZATION,
                 scopes=SCOPES, stage=STAGE, harness=Harness, runner=run)


if __name__ == '__main__':
    sys.exit(main())
