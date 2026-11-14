import os
import secrets
import subprocess
import sys
import threading

from tools.pv20_mxc.native import n2_check as n2
from tools.pv20_mxc.native import n3b_check as shared

AUTHORIZATION = 'F8-owner-authorization.json'
SCOPES = ('fixture-files', 'mxc-profiles', 'jobs-processes', 'synthetic-agent-pipe',
          'synthetic-vault-pipe')


class AuthorityPipe:
    def __init__(self, name, payload):
        from multiprocessing.connection import Listener

        self.name, self.payload = name, payload
        self.listener = Listener(name, family='AF_PIPE', authkey=None)
        self.stop = threading.Event()
        self.hits, self.errors = 0, []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stop.is_set():
            try:
                with self.listener.accept() as connection:
                    if self.stop.is_set():
                        return
                    self.hits += 1
                    connection.send_bytes(self.payload)
            except OSError:
                if not self.stop.is_set():
                    self.errors.append('pipe-error')
                return

    def close(self):
        from multiprocessing.connection import Client

        self.stop.set()
        try:
            with Client(self.name, family='AF_PIPE', authkey=None):
                pass
        finally:
            self.listener.close()
            self.thread.join(3)
        if self.thread.is_alive():
            raise n2.SetupError('authority pipe did not stop')


class Harness(shared.Harness):
    def prepare(self):
        n2.Harness.prepare(self)
        self.work = self.lay['p']['state']
        self.authorities = []

    def pipe(self, label, payload):
        name = r'\\.\pipe\pv20_f8_%s_%s' % (label, secrets.token_hex(16))
        authority = AuthorityPipe(name, payload)
        self.authorities.append(authority)
        return authority

    def wind_down(self):
        failed = 0
        for authority in getattr(self, 'authorities', ()):
            try:
                authority.close()
            except Exception:
                failed += 1
        for job in self.jobs:
            try:
                job.close()
            except Exception:
                failed += 1
        return n2.Harness.wind_down(self) + failed


def probe(h, rec, label, path, payload, authority=None):
    case = 'synthetic-file-agent-ipc-denial'
    control_case = 'authority-positive-controls'
    argv = [h.cmd, '/d', '/c', 'type', path]
    before = authority.hits if authority else 0
    host = subprocess.run(argv, capture_output=True, timeout=8, env=dict(h.env))
    shared.require(rec, control_case,
                   host.returncode == 0 and payload in host.stdout
                   and (authority is None or authority.hits > before),
                   label + ' host SAME-COMMAND positive control before denial')
    marker = secrets.token_hex(16)
    marker_path = os.path.join(h.work, label + '_control.txt')
    with open(marker_path, 'x', encoding='ascii') as stream:
        stream.write(marker)
    before = authority.hits if authority else 0
    chain = ('type %s & type %s & echo F8_DONE' % (marker_path, path))
    launch, _ = h.start('authority', [h.cmd, '/d', '/c', chain])
    code = launch.wait()
    output = launch.stdout.read()
    shared.require(rec, case, type(code) is int and marker.encode() in output
                   and b'F8_DONE' in output,
                   label + ' same-chain container control and terminal marker present')
    shared.require(rec, case, payload not in output
                   and (authority is None or authority.hits == before),
                   label + ' synthetic authority returned no payload and accepted no IPC client')
    host = subprocess.run(argv, capture_output=True, timeout=8, env=dict(h.env))
    shared.require(rec, control_case, host.returncode == 0 and payload in host.stdout,
                   label + ' host SAME-COMMAND positive control after denial')
    if authority:
        shared.require(rec, control_case, not authority.errors,
                       label + ' authority stayed healthy throughout control/denial/control')


def run(h, rec):
    h.prepare()
    payload = ('F8_SYNTHETIC_' + secrets.token_hex(24)).encode('ascii')
    path = os.path.join(h.lay['outside'], 'synthetic_authority.txt')
    with open(path, 'xb') as stream:
        stream.write(payload)
    probe(h, rec, 'file', path, payload)
    for label in ('agent', 'vault'):
        authority = h.pipe(label, payload)
        probe(h, rec, label, authority.name, payload, authority)
    rec.record('synthetic-file-agent-ipc-denial', 'INCONCLUSIVE',
               'synthetic byte-serving agent and vault pipes only; no real credential authority, '
               'vault protocol, inherited-handle transfer, token or registration-disposal read-back; '
               'SDK pins derived from source and schema validator stand-in')


def main(argv=None):
    return shared.entry(sys.argv[1:] if argv is None else argv, filename=AUTHORIZATION,
                        scopes=SCOPES, stage='F8', harness=Harness, runner=run)


if __name__ == '__main__':
    sys.exit(main())
