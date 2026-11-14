import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/App";
import { startSocket } from "@/lib/socket";
import { useStore } from "@/state/store";
import "@/index.css";

const { ingest, setStatus } = useStore.getState();
startSocket({ onMessage: ingest, onStatus: setStatus });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
