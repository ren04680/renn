import { CheckCircle2, Circle, CircleDashed, Clock3, Loader2, MinusCircle, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { agentMeta } from "../agents";
import { api, fmtTime } from "../api";
import type { TraceEvent } from "../types";

const STATUS: Record<string, { icon: any; cls: string }> = {
  pending: { icon: Circle, cls: "text-slate-400" },
  running: { icon: Loader2, cls: "text-indigo-600 animate-spin" },
  done: { icon: CheckCircle2, cls: "text-emerald-600" },
  failed: { icon: XCircle, cls: "text-rose-600" },
  skipped: { icon: MinusCircle, cls: "text-slate-300" },
  blocked: { icon: Clock3, cls: "text-amber-500" },
};

function Json({ v }: { v: any }) {
  return <pre className="text-[11px] bg-slate-900 text-slate-100 rounded-lg p-2.5 overflow-auto max-h-72 scroll-thin">{JSON.stringify(v, null, 2)}</pre>;
}

export default function BlackboardTab({ events, selected, setSelected }: { events: TraceEvent[]; selected: string | null; setSelected: (r: string) => void }) {
  const [runs, setRuns] = useState<any[]>([]);
  const [bb, setBb] = useState<any>(null);
  const [openFact, setOpenFact] = useState<string | null>(null);

  useEffect(() => {
    api<any[]>("/runs?limit=40").then((r) => {
      setRuns(r);
      if (!selected && r.length) setSelected(r[0].run_id);
    });
  }, [events.length > 0 ? Math.floor(events.length / 25) : 0]);

  const tick = useMemo(() => events.filter((e) => e.run_id === selected && e.type === "blackboard_write").length, [events, selected]);
  const load = useCallback(() => {
    if (selected) api(`/runs/${selected}/blackboard`).then(setBb).catch(() => {});
  }, [selected]);
  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load, tick]);

  return (
    <div className="h-full grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 p-4 min-h-0">
      <div className="card p-3 overflow-y-auto scroll-thin min-h-0">
        <div className="label mb-2">Runs</div>
        {runs.map((r) => (
          <button
            key={r.run_id}
            onClick={() => setSelected(r.run_id)}
            className={`w-full text-left rounded-xl px-2.5 py-2 mb-1 border ${selected === r.run_id ? "bg-indigo-50 border-indigo-200" : "border-transparent hover:bg-slate-50"}`}
          >
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className="font-mono text-slate-400">{r.run_id}</span>
              <span className="chip bg-slate-100 text-slate-600 ml-auto">{r.kind}</span>
            </div>
            <div className="text-[12.5px] text-slate-800 truncate">{r.text || "—"}</div>
            <div className="text-[11px] text-slate-500">
              {r.patient_id ?? "hospital"} · {r.status} {r.outcome ? `· ${r.outcome}` : ""}
            </div>
          </button>
        ))}
      </div>
      <div className="overflow-y-auto scroll-thin min-h-0 space-y-4" data-testid="blackboard">
        {!bb && <div className="card p-6 text-slate-400">Select a run.</div>}
        {bb && (
          <>
            <div className="card p-4">
              <div className="label">Goal</div>
              <div className="text-lg font-semibold text-slate-900 mt-0.5">{bb.goal || "—"}</div>
              <div className="text-xs text-slate-500 mt-1">
                Run <span className="font-mono">{bb.run_id}</span> · {bb.writes?.length ?? 0} blackboard writes · agents coordinate only through this board + Supervisor dispatch
              </div>
            </div>
            <div className="card p-4">
              <div className="label mb-2">Subtasks (decomposition)</div>
              <div className="space-y-1.5">
                {bb.subtasks.map((s: any) => {
                  const st = STATUS[s.status] ?? { icon: CircleDashed, cls: "" };
                  const Icon = st.icon;
                  const a = agentMeta(s.owner === "human" ? "human" : s.owner);
                  return (
                    <div key={s.id} className={`flex items-start gap-2.5 rounded-xl border px-3 py-2 ${s.status === "skipped" ? "opacity-50" : ""} border-slate-200`}>
                      <Icon className={`h-4 w-4 mt-0.5 ${st.cls}`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono text-[11px] text-slate-400">{s.id}</span>
                          <span className="text-[13px] font-medium text-slate-800">{s.title}</span>
                          {s.goal_ref && <span className="chip bg-slate-100 text-slate-600">{s.goal_ref}</span>}
                          {s.params?.coupling && <span className="chip bg-violet-100 text-violet-700">coupled</span>}
                        </div>
                        <div className="text-[11px] text-slate-500">
                          owner <span className={`font-semibold ${a.text}`}>{a.label}</span>
                          {s.depends_on.length > 0 && <> · depends on {s.depends_on.join(", ")}</>} · {s.status}
                          {s.attempts > 1 && <> · attempts {s.attempts}</>}
                        </div>
                        {s.result && Object.keys(s.result).length > 0 && (
                          <div className="text-[11px] text-slate-500 font-mono truncate">{JSON.stringify(s.result)}</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="card p-4">
                <div className="label mb-2">Facts</div>
                <div className="space-y-1">
                  {Object.entries(bb.facts ?? {}).map(([k, v]) => (
                    <div key={k}>
                      <button onClick={() => setOpenFact(openFact === k ? null : k)} className="w-full text-left text-[12.5px] font-mono rounded-lg px-2 py-1 hover:bg-slate-50 flex">
                        <span className="text-indigo-700">{k}</span>
                        <span className="ml-auto text-slate-400 truncate max-w-[60%]">{JSON.stringify(v).slice(0, 60)}</span>
                      </button>
                      {openFact === k && <Json v={v} />}
                    </div>
                  ))}
                </div>
              </div>
              <div className="card p-4">
                <div className="label mb-2">Critic verdicts</div>
                {bb.critic_verdicts.length === 0 && <div className="text-xs text-slate-400">None.</div>}
                {bb.critic_verdicts.map((v: any, i: number) => (
                  <div key={i} className={`rounded-xl border p-2.5 mb-2 text-[12.5px] ${v.verdict === "APPROVE" ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
                    <div className="font-semibold">
                      {v.verdict} · {v.proposal_id}
                    </div>
                    {v.checks?.map((c: any, j: number) => (
                      <div key={j} className="text-[11.5px]">
                        {c.pass ? "✓" : "✗"} {c.check}: {c.detail}
                      </div>
                    ))}
                  </div>
                ))}
                <div className="label mt-3 mb-2">Proposals ({bb.proposals.length} versions)</div>
                {bb.proposals.slice(-4).map((p: any, i: number) => (
                  <div key={i} className="text-[12px] rounded-lg border border-slate-200 px-2.5 py-1.5 mb-1.5">
                    <span className="font-mono text-slate-400">{p.proposal_id}</span> <span className="chip bg-slate-100">{p.stage}</span>
                    {p.items?.map((it: any) => (
                      <div key={it.slot_id}>
                        {it.patient_id}: {it.doctor_name} · {it.date} {it.start} · {it.mode} · ₹{it.fee}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
            <div className="card p-4">
              <div className="label mb-2">Write log (audit trail, persisted to SQLite)</div>
              <div className="max-h-80 overflow-y-auto scroll-thin">
                <table className="w-full text-[11.5px]">
                  <tbody>
                    {bb.writes
                      .slice()
                      .reverse()
                      .map((w: any, i: number) => {
                        const a = agentMeta(w.agent);
                        return (
                          <tr key={i} className="border-t border-slate-100">
                            <td className="py-1 font-mono text-slate-400 pr-2">{fmtTime(w.ts)}</td>
                            <td className={`font-semibold pr-2 ${a.text}`}>{a.label}</td>
                            <td className="pr-2">
                              <span className="chip bg-slate-100 text-slate-600">{w.section}</span>
                            </td>
                            <td className="font-mono text-slate-600 truncate max-w-[520px]">{JSON.stringify(w.content).slice(0, 140)}</td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
