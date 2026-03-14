import type { DlnBridge } from "./types";

declare global {
  interface Window {
    dlnBridge?: DlnBridge;
  }
}

export {};
