import { Bug, Cloud, CloudOff, HeartPulse, RotateCcw, UserPlus, Wifi, WifiOff } from "lucide-react";
import type { Patient, Settings } from "../types";

type Props = {
  patients: Patient[];
  pid: string;
  setPid: (p: string) => void;
  settings: Settings | null;
  updateSettings: (s: any) => void;
  onReset: () => void;
  resetting: boolean;
  connected: boolean;
  meta: any;
  onNewPatient: () => void;
};

export default function TopBar({ patients, pid, setPid, settings, updateSettings, onReset, resetting, connected, meta, onNewPatient }: Props) {
  const featured = patients.filter((p) => ["P001", "P014", "P023", "P031", "GUEST"].includes(p.id));
  const others = patients.filter((p) => !["P001", "P014", "P023", "P031", "GUEST"].includes(p.id));
  const cur = patients.find((p) => p.id === pid);
  return (
    <header className="bg-gradient-to-r from-ink-950 via-ink-900 to-indigo-950 text-white">
      <div className="px-5 py-3 flex items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-indigo-500/90 grid place-items-center shadow-lg shadow-indigo-900/50">
            <HeartPulse className="h-5 w-5" />
          </div>
          <div>
            <div className="font-semibold tracking-tight text-[17px] leading-tight">Hospital Agent OS</div>
            <div className="text-[11px] text-indigo-200/80 leading-tight italic whitespace-nowrap">
              Free to think, gated to act. Permitted to fail — never to invent.
            </div>
          </div>
        </div>

        <div className="ml-6 flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl pl-3 pr-1 py-1">
          <span className="text-[11px] uppercase tracking-wider text-indigo-200/70">Patient</span>
          <select
            data-testid="patient-select"
            value={pid}
            onChange={(e) => (e.target.value === "__new__" ? onNewPatient() : setPid(e.target.value))}
            className="bg-transparent text-sm font-medium focus:outline-none pr-1 [&>*]:text-slate-900"
          >
            <optgroup label="Demo patients">
              {featured.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id === "GUEST" ? "Guest (walk-in)" : `${p.id} · ${p.name}`}
                </option>
              ))}
            </optgroup>
            {others.length > 0 && (
              <optgroup label="Registered by you">
                {others.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.id} · {p.name}
                  </option>
                ))}
              </optgroup>
            )}
            <option value="__new__">＋ Register new patient…</option>
          </select>
        </div>
        <button data-testid="new-patient" onClick={onNewPatient} className="btn bg-indigo-500/90 hover:bg-indigo-500 text-white !py-1.5">
          <UserPlus className="h-4 w-4" /> New patient
        </button>
        {cur && cur.id !== "GUEST" && (
          <div className="hidden min-[1850px]:flex items-center gap-2 text-[11px] text-indigo-100/80">
            <span className="chip bg-white/10">{cur.locality}</span>
            <span className="chip bg-white/10">{cur.plan}</span>
            {cur.preferred_time && <span className="chip bg-white/10">prefers {cur.preferred_time}</span>}
            {cur.family.length > 0 && (
              <span className="chip bg-white/10">
                family: {cur.family.map((f) => `${f.relation} ${f.patient_id}`).join(", ")}
              </span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            data-testid="toggle-fault"
            onClick={() => updateSettings({ inject_fault: !settings?.inject_fault })}
            className={`btn border ${
              settings?.inject_fault ? "bg-amber-400 text-amber-950 border-amber-300" : "bg-white/5 border-white/15 text-indigo-100 hover:bg-white/10"
            }`}
            title="Debug: the Scheduling agent's first proposal is deliberately wrong so the Critic can catch it"
          >
            <Bug className="h-4 w-4" />
            Inject fault {settings?.inject_fault ? "ON" : "off"}
          </button>
          <button
            data-testid="toggle-offline"
            onClick={() => settings?.llm_available && updateSettings({ offline: !settings?.offline_forced })}
            className={`btn border ${
              settings?.offline ? "bg-slate-200/10 border-amber-300/40 text-amber-200" : "bg-emerald-500/15 border-emerald-300/40 text-emerald-200"
            }`}
            title={settings?.offline ? `Offline: ${settings.offline_reason}. Deterministic planner, same agents & tools.` : `Online: ${settings?.model}`}
          >
            {settings?.offline ? <CloudOff className="h-4 w-4" /> : <Cloud className="h-4 w-4" />}
            {settings?.offline ? "Offline mode" : `Online · ${settings?.model ?? ""}`}
          </button>
          <span
            className={`chip ${connected ? "bg-emerald-500/20 text-emerald-200" : "bg-rose-500/20 text-rose-200"}`}
            title="Live trace stream (SSE)"
          >
            {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />} live
          </span>
          <button data-testid="reset-demo" onClick={onReset} disabled={resetting} className="btn bg-white text-ink-900 hover:bg-indigo-50">
            <RotateCcw className={`h-4 w-4 ${resetting ? "animate-spin" : ""}`} />
            {resetting ? "Resetting…" : "Reset demo"}
          </button>
        </div>
      </div>
      {meta && (
        <div className="px-5 pb-2 -mt-1 text-[10.5px] text-indigo-200/60 flex gap-4">
          <span>Memory: {meta.vector_store} · {meta.embedder}</span>
          <span>Today: {meta.today}</span>
        </div>
      )}
    </header>
  );
}
