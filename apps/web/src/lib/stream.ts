// External store for the per-project event stream (test.observation / test.serial /
// lifecycle events). Runs emit ~15 events/sec; routing them through React state in
// App re-rendered the whole workspace ~15x/sec and fought scrolling. Instead the
// WS handler pushes here, we batch into a 200ms window, and only the components
// that read useStream() (drawer, history, event flow) re-render.

import { useSyncExternalStore } from "react";
import type { IntegreatEvent, SerialEvent } from "./api";

interface StreamState {
  events: IntegreatEvent[];
  serial: SerialEvent[];
  seq: number;
}

let snapshot: StreamState = { events: [], serial: [], seq: 0 };
let pendingEvents: IntegreatEvent[] = [];
let pendingSerial: SerialEvent[] = [];
let flushTimer = 0;
const listeners = new Set<() => void>();

const FLUSH_MS = 200;

function notify() {
  snapshot = { ...snapshot, seq: snapshot.seq + 1 };
  listeners.forEach((l) => l());
}

export function streamFlush() {
  if (flushTimer) { window.clearTimeout(flushTimer); flushTimer = 0; }
  if (!pendingEvents.length && !pendingSerial.length) return;
  const evs = pendingEvents; pendingEvents = [];
  const sers = pendingSerial; pendingSerial = [];
  const seen = new Set(snapshot.events.map((x) => x.seq));
  const add = evs.filter((e) => !seen.has(e.seq));
  snapshot = {
    events: add.length ? [...snapshot.events, ...add] : snapshot.events,
    serial: sers.length ? [...snapshot.serial, ...sers] : snapshot.serial,
    seq: snapshot.seq,
  };
  notify();
}

export function streamEvent(ev: IntegreatEvent, serialLine?: SerialEvent) {
  pendingEvents.push(ev);
  if (serialLine) pendingSerial.push(serialLine);
  if (!flushTimer) flushTimer = window.setTimeout(streamFlush, FLUSH_MS);
}

export function streamReset() {
  if (flushTimer) { window.clearTimeout(flushTimer); flushTimer = 0; }
  pendingEvents = []; pendingSerial = [];
  snapshot = { events: [], serial: [], seq: snapshot.seq };
  notify();
}

/** Replace the serial log wholesale — e.g. the completed-run refetch fills gaps. */
export function streamReplaceSerial(serial: SerialEvent[]) {
  pendingSerial = [];
  snapshot = { ...snapshot, serial };
  notify();
}

export function useStream(): StreamState {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => snapshot,
  );
}
