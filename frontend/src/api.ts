import { useEffect, useRef, useState } from "react";
import type { TraceEvent } from "./types";

export async function api<T = any>(path: string, body?: unknown, method?: string): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export function uid(n = 12) {
  const s = "abcdef0123456789";
  let o = "";
  for (let i = 0; i < n; i++) o += s[Math.floor(Math.random() * s.length)];
  return o;
}

/** Live trace over Server-Sent Events, with backfill on (re)connect. */
export function useTraceStream(resetKey: number) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const lastSeq = useRef(0);

  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;
    lastSeq.current = 0;
    setEvents([]);
    api<TraceEvent[]>("/events/recent?since=0&limit=1500")
      .then((evs) => {
        if (closed) return;
        setEvents(evs);
        lastSeq.current = evs.length ? evs[evs.length - 1].seq : 0;
      })
      .catch(() => {})
      .finally(() => {
        if (closed) return;
        es = new EventSource(`/api/stream?since=${lastSeq.current}`);
        es.onopen = () => setConnected(true);
        es.onerror = () => setConnected(false);
        es.addEventListener("trace", (m) => {
          const e: TraceEvent = JSON.parse((m as MessageEvent).data);
          if (e.seq <= lastSeq.current) return;
          lastSeq.current = e.seq;
          setEvents((prev) => (prev.length > 4000 ? [...prev.slice(-2500), e] : [...prev, e]));
        });
      });
    return () => {
      closed = true;
      es?.close();
    };
  }, [resetKey]);

  return { events, connected };
}

export function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function dayLabel(iso: string) {
  const d = new Date(iso + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  const base = d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  return diff === 0 ? `${base} · today` : diff === 1 ? `${base} · tomorrow` : base;
}

export const SPEC_LABEL: Record<string, string> = {
  cardiology: "Cardiology",
  dermatology: "Dermatology",
  orthopedics: "Orthopedics",
  neurology: "Neurology",
  ent: "ENT",
  pediatrics: "Pediatrics",
  general_medicine: "General Medicine",
  gastroenterology: "Gastroenterology",
};
