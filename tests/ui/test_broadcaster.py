from kavzi_trader.ui.server.broadcaster import UiBroadcaster


class TestUiBroadcaster:
    def test_broadcast_reaches_every_client(self) -> None:
        broadcaster = UiBroadcaster(queue_size=8)
        first, second = broadcaster.subscribe(), broadcaster.subscribe()

        broadcaster.broadcast("m1")

        assert first.get_nowait() == "m1"
        assert second.get_nowait() == "m1"

    def test_unsubscribed_client_gets_nothing(self) -> None:
        broadcaster = UiBroadcaster(queue_size=8)
        queue = broadcaster.subscribe()
        broadcaster.unsubscribe(queue)

        broadcaster.broadcast("m1")

        assert queue.empty()
        assert broadcaster.client_count == 0

    def test_slow_client_is_evicted_without_affecting_others(self) -> None:
        broadcaster = UiBroadcaster(queue_size=2)
        slow, fast = broadcaster.subscribe(), broadcaster.subscribe()

        broadcaster.broadcast("m1")
        broadcaster.broadcast("m2")
        fast.get_nowait()
        fast.get_nowait()
        broadcaster.broadcast("m3")

        # The evicted queue holds only the close sentinel, never a gapped stream.
        assert slow.get_nowait() is None
        assert slow.empty()
        assert fast.get_nowait() == "m3"
        assert broadcaster.client_count == 1
