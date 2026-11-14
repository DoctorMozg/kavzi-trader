import { create } from "zustand";
import type { ServerMessage } from "@/lib/protocol";
import type { ConnectionStatus } from "@/lib/socket";
import { applyMessage, initialState, type DashboardState } from "@/state/reducer";

interface DashboardStore {
  data: DashboardState;
  status: ConnectionStatus;
  lastMessageMs: number | null;
  lastAccountMs: number | null;
  messageCount: number;
  ingest: (msg: ServerMessage) => void;
  setStatus: (status: ConnectionStatus) => void;
}

let buffer: ServerMessage[] = [];
let flushScheduled = false;

export const useStore = create<DashboardStore>()((set) => {
  const flush = (): void => {
    flushScheduled = false;
    const batch = buffer;
    buffer = [];
    const now = Date.now();
    set((s) => {
      const data = batch.reduce(applyMessage, s.data);
      const sawAccount = batch.some(
        (m) => (m.type === "event" ? m.event.type === "account" : m.snapshot.account !== null),
      );
      return {
        data,
        lastMessageMs: now,
        lastAccountMs: sawAccount ? now : s.lastAccountMs,
        messageCount: s.messageCount + batch.length,
      };
    });
  };

  return {
    data: initialState,
    status: "connecting",
    lastMessageMs: null,
    lastAccountMs: null,
    messageCount: 0,
    ingest: (msg) => {
      buffer.push(msg);
      if (flushScheduled) return;
      flushScheduled = true;
      // rAF is paused in background tabs, so fall back to a timer to keep the buffer bounded.
      if (document.hidden) setTimeout(flush, 1000);
      else requestAnimationFrame(flush);
    },
    setStatus: (status) => set({ status }),
  };
});
