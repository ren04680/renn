import { CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3.5">
      <div className="label">{label}</div>
      <div className="text-2xl font-semibold text-slate-900 mt-1">{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function MetricsTab() {
  const [m, setM] = useState<any>(null);
  useEffect(() => {
    api("/metrics").then(setM).catch(() => {});
  }, []);
  if (!m) return <div className="p-6 text-slate-400">Loading…</div>;
  const rows: any[] = m.scenarios?.results ?? [];
  const pass = rows.filter((r) => r.pass).length;
  const c = m.classifier;
  const std = c?.split_standard_80_20;
  const grp = c?.split_unseen_phrases;
  const pct = (x?: number) => (x === undefined ? "—" : `${(x * 100).toFixed(1)}%`);
  return (
    <div className="h-full overflow-y-auto scroll-thin p-4 space-y-4" data-testid="metrics">
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-3">
        <Stat label="Scenarios passed" value={`${pass}/${rows.length}`} sub={m.scenarios?.mode} />
        <Stat label="Tool calls (all scenarios)" value={String(rows.reduce((a, r) => a + r.tool_calls, 0))} />
        <Stat label="Triage specialty acc." value={pct(std?.specialty?.accuracy)} sub={`macro-F1 ${pct(std?.specialty?.macro_f1)}`} />
        <Stat label="Emergency recall" value={pct(std?.urgency?.emergency_recall)} sub="ML layer; hard rule runs first" />
        <Stat label="Unseen-phrase acc." value={pct(grp?.specialty?.accuracy)} sub="honest generalisation test" />
        <Stat label="Dataset" value={String(c?.dataset_size ?? "—")} sub="symptom sentences (EN + Hinglish)" />
      </div>
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-2">
          <div className="font-semibold">Scenario results</div>
          <span className="text-xs text-slate-500">generated {m.scenarios?.generated} by scripts/run_scenarios.py</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1.5">#</th>
                <th>Scenario</th>
                <th>Outcome</th>
                <th>Pass</th>
                <th>Agents involved</th>
                <th className="text-right">Tools</th>
                <th className="text-right">Retries</th>
                <th className="text-right">Critic loops</th>
                <th className="text-right">Latency</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 align-top" title={r.checks.map((x: any) => `${x.pass ? "✓" : "✗"} ${x.check}`).join("\n")}>
                  <td className="py-1.5 font-mono text-slate-400">{r.id}</td>
                  <td className="font-medium text-slate-800">{r.scenario}</td>
                  <td>
                    <span className="chip bg-slate-100 text-slate-700">{r.outcome}</span>
                  </td>
                  <td>{r.pass ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-rose-600" />}</td>
                  <td className="text-slate-500">{r.agents.join(", ")}</td>
                  <td className="text-right font-mono">{r.tool_calls}</td>
                  <td className="text-right font-mono">{r.retries}</td>
                  <td className="text-right font-mono">{r.critic_loops}</td>
                  <td className="text-right font-mono">{r.latency_s}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_1fr] gap-4">
        <div className="card p-4">
          <div className="font-semibold mb-2">Triage classifier — confusion matrices (held-out 20%)</div>
          <img src="/models/confusion_matrix.png" alt="confusion matrix" className="w-full rounded-xl border border-slate-200" />
        </div>
        <div className="card p-4 space-y-3 text-[13px]">
          <div className="font-semibold">Model card</div>
          <div>
            <span className="label">Model</span>
            <div>{c?.model}</div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Specialty (80/20)" value={pct(std?.specialty?.accuracy)} sub={`F1 ${pct(std?.specialty?.macro_f1)}`} />
            <Stat label="Urgency (80/20)" value={pct(std?.urgency?.accuracy)} sub={`F1 ${pct(std?.urgency?.macro_f1)}`} />
            <Stat label="Specialty (unseen phrases)" value={pct(grp?.specialty?.accuracy)} sub={`F1 ${pct(grp?.specialty?.macro_f1)}`} />
            <Stat label="Urgency (unseen phrases)" value={pct(grp?.urgency?.accuracy)} sub={`F1 ${pct(grp?.urgency?.macro_f1)}`} />
          </div>
          <div className="text-slate-600">
            The large drop on <b>unseen phrasings</b> is reported on purpose: template data inflates in-distribution scores. That is why the Triage agent
            refuses to guess below 45% confidence (asks the patient instead), and why emergencies are caught by a hard rule first.
          </div>
          <div>
            <span className="label">Embeddings comparison</span>
            <div className="text-slate-600">
              {c?.embedding_comparison?.status === "ok"
                ? `MiniLM+LR specialty acc ${pct(c.embedding_comparison.specialty_accuracy)}`
                : `skipped — ${c?.embedding_comparison?.reason}`}
            </div>
          </div>
          <div>
            <span className="label">Vector memory</span>
            <div className="text-slate-600">
              {m.system?.vector_store} · {m.system?.embedder}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
