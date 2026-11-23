import { Bug, Cloud, CloudOff, RotateCcw, UserPlus, Wifi, WifiOff } from "lucide-react";
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
  onNewPatient: () => void;
  advanced: boolean;
};

export default function TopBar({ patients, pid, setPid, settings, updateSettings, onReset, resetting, connected, onNewPatient, advanced }: Props) {
  const featured = patients.filter((p) => ["P001", "P014", "P023", "P031", "GUEST"].includes(p.id));
  const others = patients.filter((p) => !["P001", "P014", "P023", "P031", "GUEST"].includes(p.id));
  return (
    <header className="bg-ink-950 text-white">
      <div className="px-5 py-3 flex items-center gap-4">
        <div className="font-semibold tracking-tight text-[18px] whitespace-nowrap">Hospital Agent OS</div>

        <div className="ml-6 flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl pl-3 pr-1 py-1">
          <span className="text-[11px] uppercase tracking-wider text-slate-400">Patient</span>
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
        <button data-testid="new-patient" onClick={onNewPatient} className="btn bg-white/10 hover:bg-white/15 text-white !py-1.5">
          <UserPlus className="h-4 w-4" /> New patient
        </button>

        <div className="ml-auto flex items-center gap-2">
          {advanced && (
            <>
              <button
                data-testid="toggle-fault"
                onClick={() => updateSettings({ inject_fault: !settings?.inject_fault })}
                className={`btn border ${
                  settings?.inject_fault ? "bg-amber-400 text-amber-950 border-amber-300" : "bg-white/5 border-white/15 text-slate-200 hover:bg-white/10"
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
                  settings?.offline ? "bg-white/5 border-amber-300/40 text-amber-200" : "bg-emerald-500/15 border-emerald-300/40 text-emerald-200"
                }`}
                title={settings?.offline ? `Offline: ${settings.offline_reason}` : `Online: ${settings?.model}`}
              >
                {settings?.offline ? <CloudOff className="h-4 w-4" /> : <Cloud className="h-4 w-4" />}
                {settings?.offline ? "Offline mode" : `Online · ${settings?.model ?? ""}`}
              </button>
            </>
          )}
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-rose-400"}`} title={connected ? "Live" : "Reconnecting…"}>
            <span className="sr-only">{connected ? <Wifi /> : <WifiOff />}</span>
          </span>
          <button data-testid="reset-demo" onClick={onReset} disabled={resetting} className="btn bg-white text-ink-900 hover:bg-slate-100">
            <RotateCcw className={`h-4 w-4 ${resetting ? "animate-spin" : ""}`} />
            {resetting ? "Resetting…" : "Reset demo"}
          </button>
        </div>
      </div>
    </header>
  );
}
