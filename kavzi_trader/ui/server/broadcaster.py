import asyncio
import logging

logger = logging.getLogger(__name__)

# None is queued in place of messages when a client is evicted; its sender closes.
type ClientQueue = asyncio.Queue[str | None]


class UiBroadcaster:
    """Fans serialized messages out to per-client bounded queues."""

    def __init__(self, queue_size: int) -> None:
        self._queue_size = queue_size
        self._clients: set[ClientQueue] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def subscribe(self) -> ClientQueue:
        queue: ClientQueue = asyncio.Queue(maxsize=self._queue_size)
        self._clients.add(queue)
        logger.info("UI client subscribed, clients=%d", len(self._clients))
        return queue

    def unsubscribe(self, queue: ClientQueue) -> None:
        if queue in self._clients:
            self._clients.discard(queue)
            logger.info("UI client unsubscribed, clients=%d", len(self._clients))

    def broadcast(self, message: str) -> None:
        for queue in list(self._clients):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                self._evict(queue)

    def _evict(self, queue: ClientQueue) -> None:
        # A gap would corrupt the client's state, so a lagging client is cut
        # off and resyncs from a fresh snapshot when it reconnects.
        self._clients.discard(queue)
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait(None)
        logger.warning(
            "Evicted slow UI client, queue_size=%d clients=%d",
            self._queue_size,
            len(self._clients),
        )
