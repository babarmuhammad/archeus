"""Streams cannot starve commands, and a slow reader cannot block the writer
(p3.5b design gate §5.2, §6.2; §10 C1, C2)."""

import socket
import time

from archeus.core.application import commands
from v1.integration.test_api_auth import observe_device
from v1.judge.http import SSEClient


def test_eight_open_streams_leave_requests_answering_and_a_ninth_is_429(tc):
    tokens = [tc.token] + [observe_device(tc)[1] for _ in range(4)]
    streams = []
    try:
        for token in tokens[:4]:
            for _ in range(2):
                s = SSEClient(tc.base_url, token)
                assert s.status == 200
                streams.append(s)
        assert tc.core.api.sse.count() == 8
        for method, path, body in (('GET', '/v1/version', None),
                                   ('POST', '/v1/missions', {'title': 't', 'objective': 'o',
                                                             'idempotency_key': 'c1'})):
            t0 = time.monotonic()
            assert tc.http(method, path, body=body).status == 200
            assert time.monotonic() - t0 < 1.0, path
        ninth = SSEClient(tc.base_url, tokens[4])                  # the pool is full
        assert ninth.status == 429 and b'too_many_streams' in ninth.body()
        streams.pop().close()
        deadline = time.monotonic() + 5
        while tc.core.api.sse.count() != 7:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        third = SSEClient(tc.base_url, tokens[0])                  # per device: 2 at most
        assert third.status == 429
        fifth_device = SSEClient(tc.base_url, tokens[4])
        assert fifth_device.status == 200
        streams.append(fifth_device)
    finally:
        for s in streams:
            s.close()


def test_a_reader_that_never_reads_does_not_slow_the_writer(tc):
    raw = socket.create_connection(('127.0.0.1', tc.port))
    raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
    raw.sendall(('GET /v1/events/stream?after=0 HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n'
                 'Authorization: Bearer %s\r\n\r\n' % (tc.port, tc.token)).encode())
    try:
        deadline = time.monotonic() + 5
        while tc.core.api.sse.count() != 1:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        t0 = time.monotonic()
        for i in range(200):
            tc.core.db.writer.execute(commands.create_mission, {
                'actor': tc.core.system, 'title': 'm%d' % i, 'objective': 'o' * 2000})
        assert time.monotonic() - t0 < 20, 'the writer waited on a reader'
        assert tc.http('GET', '/v1/version').status == 200
    finally:
        raw.close()
