"""LV2-1 H-3: serve the lab to a physical phone for ONE session, then stop.

Two modes, per the user's decision:
  --adb      Android: bind 127.0.0.1 only; reach it from the phone with
             `adb reverse tcp:PORT tcp:PORT` (nothing is exposed on the network).
  (default)  iPhone: bind this machine's private LAN address for the session only.

Either way: a fresh random token per run, carried in the path (/s/<token>/...) so a Home Screen
app saved from that URL keeps working, and remembered in an HttpOnly SameSite=Strict cookie so
the page's root-relative assets load; every other request is 403. The Host header must be the
bound address (DNS-rebinding defence). GET/HEAD only, no directory listings, the same two
read-only roots as serve.py (synthetic fixture data only). Stops after --minutes (default 45) or
Ctrl+C, and says so. Windows will ask once to allow the LAN bind through the firewall: allow it
for PRIVATE networks only.
Prototype tooling.   py prototypes/v2-later/tools/serve_lan.py [--adb] [--port N] [--minutes M]
"""
import argparse
import hmac
import http.server
import ipaddress
import secrets
import socket
import threading
import time

from serve import _H

TOKEN = secrets.token_urlsafe(18)
COOKIE = 'lv21k'


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1', 9))  # TEST-NET: no packet is sent for a UDP connect
        ip = s.getsockname()[0]
    finally:
        s.close()
    if not ipaddress.ip_address(ip).is_private:
        raise SystemExit('refusing to serve on a non-private address: %s' % ip)
    return ip


class _Gate(_H):
    allowed_host = ''

    def _ok(self):
        if self.headers.get('Host', '') != self.allowed_host:
            return False
        p = self.path
        pre = '/s/%s/' % TOKEN
        if p.startswith(pre):
            self.path = '/' + p[len(pre):]
            self._set_cookie = True
            return True
        for part in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == COOKIE and hmac.compare_digest(v.encode('utf-8', 'replace'), TOKEN.encode()):
                return True
        return False

    def end_headers(self):
        if getattr(self, '_set_cookie', False):
            self.send_header('Set-Cookie', '%s=%s; Path=/; HttpOnly; SameSite=Strict' % (COOKIE, TOKEN))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def do_GET(self):
        if not self._ok():
            return self.send_error(403)
        return super().do_GET()

    def do_HEAD(self):
        if not self._ok():
            return self.send_error(403)
        return super().do_HEAD()

    def do_POST(self):
        self.send_error(405)

    do_PUT = do_DELETE = do_PATCH = do_POST

    def list_directory(self, path):
        self.send_error(404)


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--adb', action='store_true')
    a.add_argument('--port', type=int, default=0)
    a.add_argument('--minutes', type=float, default=45)
    o = a.parse_args()
    ip = '127.0.0.1' if o.adb else lan_ip()
    srv = http.server.ThreadingHTTPServer((ip, o.port), _Gate)
    port = srv.server_address[1]
    _Gate.allowed_host = '%s:%d' % (ip, port)
    base = 'http://%s:%d/s/%s/proto/v2-later/lab/' % (ip, port, TOKEN)
    print('LV2-1 session server: %s mode, stops in %g min' % ('adb (loopback)' if o.adb else 'LAN (private)', o.minutes))
    if o.adb:
        print('  on the PC:   adb reverse tcp:%d tcp:%d' % (port, port))
    print('  harness "Phone base URL":  %s' % base)
    print('  on the phone open:         %sia.html?v=b&log=1' % base)
    print('  LV2-X.4 phone pass:        %s' % base.replace('/lab/', '/lvx/') + 'pass.html')
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        time.sleep(o.minutes * 60)
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    srv.server_close()
    print('stopped; the token is void.')


if __name__ == '__main__':
    main()
