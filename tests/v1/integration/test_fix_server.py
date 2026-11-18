import socket

import pytest


def _exchange(tc, head, tail=b''):
    """Send *head* (a request) then *tail* on one connection; everything the server answers."""
    s = socket.create_connection(('127.0.0.1', tc.port), timeout=5)
    try:
        s.sendall(head + tail)
        data = b''
        while True:
            try:
                chunk = s.recv(65536)
            except (socket.timeout, ConnectionError):
                break
            if not chunk:
                break
            data += chunk
        return data
    finally:
        s.close()


def _status(out):
    return out.split(b'\r\n')[0].split()[1]


POST = b'POST /v1/missions HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n%s\r\n'
GET = b'GET /v1/version HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n'


@pytest.mark.parametrize('framing', [
    b'Content-Length: 1_0\r\n',
    b'Content-Length: 2\r\nContent-Length: 2\r\n',
    b'Transfer-Encoding: chunked\r\n',
])
def test_a_body_framing_the_server_does_not_read_is_refused(tc, framing):
    assert _status(_exchange(tc, POST % (tc.port, framing), GET % tc.port)) == b'400'


def test_a_deeply_nested_body_is_400_not_500(tc):
    body = b'[' * 100000 + b']' * 100000
    head = POST % (tc.port, b'Authorization: Bearer %s\r\nContent-Length: %d\r\n' % (
        tc.token.encode(), len(body)))
    assert _status(_exchange(tc, head, body)) == b'400'
