import { isNextSeq } from "@/lib/seq";
import type { ServerMessage } from "@/lib/protocol";

export type ConnectionStatus = "connecting" | "live" | "reconnecting";

export interface SocketHandlers {
  onMessage: (msg: ServerMessage) => void;
  onStatus: (status: ConnectionStatus) => void;
}

const MIN_DELAY_MS = 500;
const MAX_DELAY_MS = 10_000;

export function backoffDelayMs(attempt: number, random = Math.random()): number {
  const ceiling = Math.min(MAX_DELAY_MS, MIN_DELAY_MS * 2 ** attempt);
  // Jitter between 50% and 100% so reconnecting tabs don't stampede the server.
  return ceiling * (0.5 + random * 0.5);
}

function socketUrl(): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws`;
}

export function startSocket({ onMessage, onStatus }: SocketHandlers): () => void {
  let ws: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let stopped = false;

  const open = (): void => {
    const socket = new WebSocket(socketUrl());
    ws = socket;
    let lastSeq: number | null = null;

    socket.onmessage = (ev: MessageEvent<string>) => {
      if (socket !== ws) return;
      const msg = JSON.parse(ev.data) as ServerMessage;
      if (msg.type === "snapshot") {
        lastSeq = msg.seq;
        attempt = 0;
        onStatus("live");
      } else if (isNextSeq(lastSeq, msg.seq)) {
        lastSeq = msg.seq;
      } else {
        console.warn("seq gap, reconnecting", { lastSeq, got: msg.seq });
        lastSeq = null;
        socket.close();
        return;
      }
      onMessage(msg);
    };

    socket.onclose = () => {
      if (socket !== ws || stopped) return;
      onStatus("reconnecting");
      timer = setTimeout(open, backoffDelayMs(attempt++));
    };
  };

  onStatus("connecting");
  open();

  return () => {
    stopped = true;
    clearTimeout(timer);
    ws?.close();
  };
}
