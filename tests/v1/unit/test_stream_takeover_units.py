"""F4 (p20-design-gate D2) in `Streams._register` alone: which stream a
takeover picks, and that the superseded one is told three ways — taken out of
the pool, flagged closing with its reason, and hung up, so a write blocked on a
client that stopped reading fails instead of holding its thread."""

import types

import pytest

from archeus.api import sse


class _Conn:
    def __init__(self):
        self.shut = False

    def shutdown(self, how):
        self.shut = True


def _streams():
    woke = []
    db = types.SimpleNamespace(writer=types.SimpleNamespace(wake=lambda: woke.append(1)))
    return sse.Streams(db), woke


def test_the_oldest_of_the_device_is_superseded_and_told_every_way():
    st, woke = _streams()
    other, _ = st._register('dvc_b', _Conn())
    (a1, first), (a2, _) = st._register('dvc_a', _Conn()), st._register('dvc_a', _Conn())
    assert first
    a1.started = True                                   # its 200 is out: it is hung up
    a3, first = st._register('dvc_a', _Conn())
    assert not first                                    # not a presence transition
    assert st.connections('dvc_a') == [a2.connection_id, a3.connection_id]
    assert a1.closing.is_set() and a1.why == 'superseded' and a1.conn.shut and woke
    for s in (a2, a3, other):
        assert not s.closing.is_set() and not s.conn.shut and s.why == 'revoked'
    assert st.connections('dvc_b') == [other.connection_id]


def test_a_stream_superseded_before_its_200_is_not_cut_mid_handshake():
    """It is flagged and leaves the pool, but its socket is left alone: it
    answers 200, sees `closing` at its first check and ends with an EOF."""
    st, _ = _streams()
    a1, _ = st._register('dvc_a', _Conn())
    st._register('dvc_a', _Conn())
    st._register('dvc_a', _Conn())
    assert a1.closing.is_set() and a1.why == 'superseded' and not a1.conn.shut


def test_the_pools_cap_refuses_a_new_device_but_not_a_capped_ones_takeover():
    st, _ = _streams()
    held = [st._register('dvc_%d' % (i // 2), _Conn())[0] for i in range(sse.MAX_STREAMS)]
    with pytest.raises(sse.TooManyStreams):
        st._register('dvc_new', _Conn())
    st._register('dvc_0', _Conn())
    assert st.count() == sse.MAX_STREAMS and held[0].closing.is_set()
    assert not any(s.closing.is_set() for s in held[1:])
