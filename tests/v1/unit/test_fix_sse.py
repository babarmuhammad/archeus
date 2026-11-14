import types

from archeus.api import sse


class _Conn:
    def __init__(self):
        self.shut = False

    def shutdown(self, how):
        self.shut = True


def test_a_revoked_stream_that_never_finishes_is_hung_up_after_the_deadline():
    st = sse.Streams(types.SimpleNamespace(writer=types.SimpleNamespace(wake=lambda: None)))
    wedged, _ = st._register('dvc_a', _Conn())
    other, _ = st._register('dvc_b', _Conn())
    st.close_device('dvc_a', timeout=0.05)
    assert wedged.closing.is_set() and wedged.conn.shut
    assert not other.closing.is_set() and not other.conn.shut


def test_streams_that_finish_in_time_are_not_hung_up():
    st = sse.Streams(types.SimpleNamespace(writer=types.SimpleNamespace(wake=lambda: None)))
    s, _ = st._register('dvc_a', _Conn())
    s.done.set()
    st.close_device('dvc_a', timeout=0.05)
    assert not s.conn.shut


def test_a_superseded_stream_is_never_the_last_one_open():
    st = sse.Streams(types.SimpleNamespace(writer=types.SimpleNamespace(wake=lambda: None)))
    a1, _ = st._register('dvc_a', _Conn())
    a2, _ = st._register('dvc_a', _Conn())
    a3, _ = st._register('dvc_a', _Conn())
    assert [st._unregister(a3), st._unregister(a2)] == [False, True]
    assert st._unregister(a1) is False
