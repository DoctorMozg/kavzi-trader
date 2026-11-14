import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from kavzi_trader.ui.server.broadcaster import ClientQueue, UiBroadcaster
from kavzi_trader.ui.server.projection import UiStateProjection
from kavzi_trader.ui.server.stream_service import UiStreamService

logger = logging.getLogger(__name__)

# RFC 6455 "try again later": the browser reconnects and gets a fresh snapshot.
_CLOSE_TRY_AGAIN_LATER = 1013


class UiWebApp:
    """Starlette app exposing the dashboard WebSocket, snapshot and static UI."""

    def __init__(
        self,
        projection: UiStateProjection,
        broadcaster: UiBroadcaster,
        stream_service: UiStreamService,
        static_dir: Path,
    ) -> None:
        self._projection = projection
        self._broadcaster = broadcaster
        self._stream_service = stream_service
        self._static_dir = static_dir

    def build(self) -> Starlette:
        routes: list[BaseRoute] = [
            WebSocketRoute("/ws", self._websocket),
            Route("/api/snapshot", self._snapshot),
        ]
        if self._static_dir.is_dir():
            routes.append(
                Mount("/", StaticFiles(directory=self._static_dir, html=True))
            )
        else:
            # API-only mode is what the Vite dev server proxies to.
            logger.warning(
                "UI static dir %s missing, serving API only; run `npm run build`"
                " in ui/web",
                self._static_dir,
            )
        return Starlette(routes=routes, lifespan=self._lifespan)

    @contextlib.asynccontextmanager
    async def _lifespan(self, _app: Starlette) -> AsyncIterator[None]:
        await self._stream_service.load_history()
        tail = asyncio.create_task(self._stream_service.run(), name="ui_stream_tail")
        try:
            yield
        finally:
            tail.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tail
            await self._stream_service.close()

    async def _snapshot(self, _request: Request) -> JSONResponse:
        return JSONResponse(self._projection.snapshot_message().model_dump(mode="json"))

    async def _websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        # No await between these two lines, so no event can slip in between
        # the snapshot and the first queued delta.
        queue = self._broadcaster.subscribe()
        snapshot = self._projection.snapshot_message()
        try:
            await websocket.send_text(snapshot.model_dump_json())
            pump = asyncio.create_task(self._pump(websocket, queue))
            listen = asyncio.create_task(self._wait_for_disconnect(websocket))
            done, pending = await asyncio.wait(
                {pump, listen},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
        except WebSocketDisconnect:
            logger.debug("UI client disconnected during send")
        finally:
            self._broadcaster.unsubscribe(queue)

    @staticmethod
    async def _pump(websocket: WebSocket, queue: ClientQueue) -> None:
        while True:
            message = await queue.get()
            if message is None:
                await websocket.close(code=_CLOSE_TRY_AGAIN_LATER)
                return
            await websocket.send_text(message)

    @staticmethod
    async def _wait_for_disconnect(websocket: WebSocket) -> None:
        # The protocol is server-push only; inbound frames are ignored.
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                await websocket.receive_text()
