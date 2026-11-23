import { ChevronRight, Filter, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { AGENTS, agentMeta } from "../agents";
import { fmtTime } from "../api";
import type { TraceEvent } from "../types";

type Props = { events: TraceEvent[]; myRunIds: string[]; patientId: string; busy: boolean };

const TYPE_STYLE: Record<string, string> = {
  tool_call: "bg-blue-50 text-blue-700 border-blue-200",
  tool_result: "bg-slate-50 text-slate-600 border-slate-200",
  thought: "bg-violet-50 text-violet-700 border-violet-200",
  decision: "bg-indigo-50 text-indigo-700 border-indigo-200",
  memory_hit: "bg-emerald-50 text-emerald-700 border-emerald-200",
  relaxation: "bg-amber-50 text-amber-800 border-amber-200",
  critic_verdict: "bg-cyan-50 text-cyan-800 border-cyan-200",
  approval_request: "bg-indigo-600 text-white border-indigo-600",
  notification: "bg-teal-50 text-teal-700 border-teal-200",
  event_trigger: "bg-fuchsia-600 text-white border-fuchsia-600",
  offer: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  error: "bg-red-50 text-red-700 border-red-200",
  fallback: "bg-orange-50 text-orange-700 border-orange-200",
  blackboard_write: "bg-slate-50 text-slate-500 border-slate-200",
  message: "bg-slate-900 text-white border-slate-900",
};

function EventRow({ e }: { e: TraceEvent }) {
  const [open, setOpen] = useState(false);
  const a = agentMeta(e.agent);
  const Icon = a.icon;
  const p = e.payload ?? {};
  let body: JSX.Element;
  if (e.type === "tool_call") {
    const [call, why] = e.msg.split("  ← why: ");
    body = (
      <div>
        <div className="font-mono text-[12px] text-slate-800 break-all">
          <span className="text-blue-600">→ </span>
          {call}
          {p.gated && <span className="chip bg-rose-100 text-rose-700 ml-1.5 align-middle">GATED</span>}
        </div>
        {why && <div className="text-[12px] text-slate-500 italic mt-0.5">why: {why}</div>}
      </div>
    );
  } else if (e.type === "tool_result") {
    body = (
      <div className={`text-[12px] ${p.ok === false ? "text-red-700" : "text-slate-600"}`}>
        <span className={p.ok === false ? "text-red-500" : "text-emerald-600"}>← </span>
        {e.msg}
      </div>
    );
  } else if (e.type === "critic_verdict") {
    const ok = p.verdict === "APPROVE";
    body = (
      <div className={`rounded-lg border px-2.5 py-1.5 text-[12.5px] ${ok ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-red-50 border-red-200 text-red-900"}`}>
        <span className="font-bold">{p.verdict}</span>
        {ok ? " — ids exist · slot free · matches request · relaxations disclosed" : ""}
        {!ok && (
          <ul className="list-disc pl-4 mt-0.5">
            {(p.reasons ?? []).map((r: string, i: number) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    );
  } else if (e.type === "event_trigger") {
    body = (
      <div className="rounded-lg bg-gradient-to-r from-fuchsia-600 to-pink-600 text-white px-2.5 py-1.5 text-[12.5px] font-medium flex items-center gap-1.5">
        <Zap className="h-3.5 w-3.5" /> {e.msg}
      </div>
    );
  } else if (e.type === "relaxation") {
    body = (
      <div className={`text-[12.5px] ${p.rejected ? "text-red-700 font-medium" : p.skipped ? "text-slate-500" : "text-amber-800 font-medium"}`}>
        {p.skipped ? "⤼ " : p.rejected ? "⛔ " : "↔ "}
        {e.msg}
      </div>
    );
  } else if (e.type === "memory_hit") {
    body = (
      <div className="text-[12.5px] text-emerald-900 bg-emerald-50/70 rounded-md px-2 py-1 border border-emerald-100">
        <span className="font-mono text-[10.5px] text-emerald-600 mr-1">{p.score?.toFixed?.(2)}</span>
        {p.text ?? e.msg}
      </div>
    );
  } else if (e.type === "message") {
    body = (
      <div className={`text-[12.5px] ${p.role === "user" ? "text-slate-900 font-medium" : "text-slate-700"}`}>
        {p.role === "user" ? "💬 " : "🤖 "}
        {e.msg.replace(/\*\*/g, "").slice(0, 260)}
      </div>
    );
  } else {
    body = (
      <div
        className={`text-[12.5px] ${
          e.type === "thought" ? "text-slate-700" : e.type === "decision" ? "text-slate-900 font-medium" : e.type === "error" ? "text-red-700" : "text-slate-600"
        }`}
      >
        {e.msg}
      </div>
    );
  }
  return (
    <div className="group flex gap-2.5 py-1 animate-slideIn">
      <div className="flex flex-col items-center">
        <div className={`h-6 w-6 rounded-full ${a.soft} ${a.text} grid place-items-center ring-1 ring-inset ring-black/5`}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="flex-1 w-px bg-slate-200 group-last:hidden" />
      </div>
      <div className="flex-1 min-w-0 pb-1">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className={`text-[11px] font-semibold ${a.text}`}>{a.label}</span>
          <span className={`chip border ${TYPE_STYLE[e.type] ?? "bg-slate-50 text-slate-500 border-slate-200"} !py-0 !text-[10px]`}>{e.type.replace("_", " ")}</span>
          <span className="text-[10px] text-slate-400 font-mono">{fmtTime(e.ts)}</span>
          {e.payload && Object.keys(e.payload).length > 0 && (
            <button onClick={() => setOpen(!open)} className="ml-auto text-slate-400 hover:text-slate-700 opacity-0 group-hover:opacity-100">
              <ChevronRight className={`h-3.5 w-3.5 transition ${open ? "rotate-90" : ""}`} />
            </button>
          )}
        </div>
        {body}
        {open && (
          <pre className="mt-1 text-[10.5px] bg-slate-900 text-slate-100 rounded-lg p-2 overflow-x-auto max-h-64 scroll-thin">
            {JSON.stringify(e.payload, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

export default function ActivityPanel({ events, myRunIds, patientId, busy }: Props) {
  const [scope, setScope] = useState<"all" | "mine">("all");
  const [showBB, setShowBB] = useState(false);
  const [now, setNow] = useState(Date.now() / 1000);
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const lastAuto = useRef(0);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 500);
    return () => clearInterval(t);
  }, []);

  const relevantRuns = useMemo(() => {
    const s = new Set(myRunIds);
    for (const e of events) {
      if (e.run_id.startsWith("px-") && e.type === "run_status" && e.payload?.patient_id === patientId) s.add(e.run_id);
      if (e.run_id.startsWith("ev-") && e.type === "offer" && e.payload?.patient_id === patientId) s.add(e.run_id);
    }
    return s;
  }, [events, myRunIds, patientId]);

  const shown = useMemo(
    () =>
      events.filter(
        (e) =>
          e.run_id !== "system" &&
          (showBB || e.type !== "blackboard_write") &&
          (scope === "all" || relevantRuns.has(e.run_id)),
      ),
    [events, scope, showBB, relevantRuns],
  );
  const visible = shown.slice(-600);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) {
      lastAuto.current = Date.now();
      el.scrollTop = el.scrollHeight;
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, [visible.length, scope, showBB]);

  const lastByAgent = useMemo(() => {
    const m: Record<string, number> = {};
    const c: Record<string, number> = {};
    for (const e of events) {
      m[e.agent] = e.ts;
      if (e.type === "tool_call") c[e.agent] = (c[e.agent] ?? 0) + 1;
    }
    return { m, c };
  }, [events]);

  let lastRun = "";
  return (
    <section className="card flex flex-col min-h-0 h-full" data-testid="activity-panel">
      <div className="px-4 pt-3 pb-2 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className="font-semibold text-slate-900">Agent Activity</div>
          <span className="text-xs text-slate-500">live · every thought, tool call and verdict</span>
          <div className="ml-auto flex items-center gap-1 text-xs">
            <Filter className="h-3.5 w-3.5 text-slate-400" />
            <div className="flex rounded-lg border border-slate-200 overflow-hidden">
              {(["all", "mine"] as const).map((s) => (
                <button key={s} onClick={() => setScope(s)} className={`px-2 py-1 ${scope === s ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}>
                  {s === "all" ? "Everything" : "This patient"}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-1 ml-2 text-slate-600 cursor-pointer">
              <input type="checkbox" checked={showBB} onChange={(e) => setShowBB(e.target.checked)} /> blackboard writes
            </label>
          </div>
        </div>
        <div className="mt-2.5 grid grid-cols-4 xl:grid-cols-8 gap-1.5">
          {AGENTS.map((a) => {
            const active = now - (lastByAgent.m[a.key] ?? 0) < 2.2;
            const Icon = a.icon;
            return (
              <div
                key={a.key}
                data-testid={`agent-${a.key}`}
                className={`rounded-xl border px-2 py-1.5 transition-all ${
                  active ? `${a.soft} border-transparent ring-2 ${a.ring} shadow-md scale-[1.03]` : "bg-white border-slate-200"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`h-5 w-5 rounded-md grid place-items-center ${active ? `${a.dot} text-white animate-pulseRing` : `${a.soft} ${a.text}`}`}>
                    <Icon className="h-3 w-3" />
                  </span>
                  <span className={`text-[11.5px] font-semibold truncate ${active ? a.text : "text-slate-700"}`}>{a.label}</span>
                </div>
                <div className="text-[10px] text-slate-400 truncate mt-0.5">
                  {a.role} · {lastByAgent.c[a.key] ?? 0} calls
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div
        ref={box}
        onScroll={(e) => {
          if (Date.now() - lastAuto.current < 400) return; // ignore our own programmatic scrolls
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
        }}
        className="flex-1 min-h-0 overflow-y-auto scroll-thin px-4 py-2"
      >
        {visible.length === 0 && (
          <div className="text-sm text-slate-400 text-center py-16">
            Send a request or fire a hospital event — every agent step will stream here live.
          </div>
        )}
        {visible.map((e) => {
          const header = e.run_id !== lastRun;
          lastRun = e.run_id;
          return (
            <div key={e.seq}>
              {header && (
                <div className="flex items-center gap-2 mt-3 mb-1">
                  <div className="h-px flex-1 bg-slate-200" />
                  <span className="text-[10px] font-mono text-slate-400">
                    {e.run_id.startsWith("ev-") ? "⚡ event run " : e.run_id.startsWith("px-") ? "proactive offer " : "run "}
                    {e.run_id}
                  </span>
                  <div className="h-px flex-1 bg-slate-200" />
                </div>
              )}
              {e.type === "run_status" ? (
                <div className="text-[10.5px] text-slate-400 text-center py-0.5">{e.msg}</div>
              ) : (
                <EventRow e={e} />
              )}
            </div>
          );
        })}
        {busy && <div className="text-xs text-slate-400 py-2 animate-pulse">…</div>}
      </div>
    </section>
  );
}
