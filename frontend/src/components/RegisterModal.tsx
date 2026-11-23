import { UserPlus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Patient } from "../types";

const LOCALITIES = ["Kothrud", "Baner", "Hadapsar", "Viman Nagar", "Shivajinagar", "Loni Kalbhor"];
const RELATIONS = ["mother", "father", "spouse", "son", "daughter", "sibling"];

type Props = { open: boolean; onClose: () => void; onCreated: (id: string) => void; patients: Patient[] };

export default function RegisterModal({ open, onClose, onCreated, patients }: Props) {
  const [plans, setPlans] = useState<{ id: string; name: string; notes: string }[]>([]);
  const [f, setF] = useState({
    name: "",
    age: "",
    gender: "F",
    phone: "",
    locality: "",
    insurance_plan_id: "INS0",
    preferred_time: "",
    preferred_mode: "",
    language: "English",
    family_of: "",
    relation: "mother",
  });
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) api("/insurance_plans").then(setPlans).catch(() => {});
  }, [open]);
  if (!open) return null;
  const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }));

  const submit = async () => {
    setErr("");
    if (f.name.trim().length < 2) return setErr("Please enter the patient's full name.");
    const age = parseInt(f.age, 10);
    if (Number.isNaN(age) || age < 0 || age > 120) return setErr("Please enter a valid age (0–120).");
    setSaving(true);
    try {
      const r = await api<{ id: string }>("/patients", {
        name: f.name,
        age,
        gender: f.gender,
        phone: f.phone,
        locality: f.locality,
        insurance_plan_id: f.insurance_plan_id,
        preferred_time: f.preferred_time || null,
        preferred_mode: f.preferred_mode || null,
        language: f.language,
        family: f.family_of ? { patient_id: f.family_of, relation: f.relation } : null,
      });
      onCreated(r.id);
      setF((x) => ({ ...x, name: "", age: "", phone: "", family_of: "" }));
    } catch (e) {
      setErr(String(e).replace(/^Error: \d+ /, ""));
    } finally {
      setSaving(false);
    }
  };

  const input = "w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white";
  const others = patients.filter((p) => p.id !== "GUEST");
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 grid place-items-center p-4" onClick={onClose}>
      <div className="card w-full max-w-lg p-5 animate-slideIn" onClick={(e) => e.stopPropagation()} data-testid="register-modal">
        <div className="flex items-center gap-2 mb-1">
          <div className="h-8 w-8 rounded-lg bg-indigo-600 text-white grid place-items-center">
            <UserPlus className="h-4 w-4" />
          </div>
          <div className="font-semibold text-lg">Register a new patient</div>
          <button onClick={onClose} className="ml-auto text-slate-400 hover:text-slate-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Saved to the hospital database. Preferences become long-term memories, so the agents won't ask for them again.
        </p>
        <div className="grid grid-cols-6 gap-3 text-sm">
          <label className="col-span-4">
            <span className="label">Full name *</span>
            <input data-testid="reg-name" className={input} value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Priya Deshmukh" />
          </label>
          <label className="col-span-1">
            <span className="label">Age *</span>
            <input data-testid="reg-age" className={input} value={f.age} onChange={(e) => set("age", e.target.value.replace(/\D/g, ""))} placeholder="34" />
          </label>
          <label className="col-span-1">
            <span className="label">Gender</span>
            <select className={input} value={f.gender} onChange={(e) => set("gender", e.target.value)}>
              <option value="F">F</option>
              <option value="M">M</option>
              <option value="U">Other</option>
            </select>
          </label>
          <label className="col-span-3">
            <span className="label">Phone</span>
            <input className={input} value={f.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+91-98…" />
          </label>
          <label className="col-span-3">
            <span className="label">Area (home)</span>
            <select data-testid="reg-locality" className={input} value={f.locality} onChange={(e) => set("locality", e.target.value)}>
              <option value="">— not specified —</option>
              {LOCALITIES.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </label>
          <label className="col-span-6">
            <span className="label">Insurance</span>
            <select data-testid="reg-plan" className={input} value={f.insurance_plan_id} onChange={(e) => set("insurance_plan_id", e.target.value)}>
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {p.notes}
                </option>
              ))}
            </select>
          </label>
          <label className="col-span-2">
            <span className="label">Preferred time</span>
            <select data-testid="reg-time" className={input} value={f.preferred_time} onChange={(e) => set("preferred_time", e.target.value)}>
              <option value="">No preference</option>
              <option value="morning">Morning</option>
              <option value="evening">Evening</option>
            </select>
          </label>
          <label className="col-span-2">
            <span className="label">Consultation</span>
            <select className={input} value={f.preferred_mode} onChange={(e) => set("preferred_mode", e.target.value)}>
              <option value="">No preference</option>
              <option value="in_person">In person</option>
              <option value="tele">Online (video)</option>
            </select>
          </label>
          <label className="col-span-2">
            <span className="label">Language</span>
            <select className={input} value={f.language} onChange={(e) => set("language", e.target.value)}>
              <option>English</option>
              <option>Hindi</option>
              <option>Marathi</option>
            </select>
          </label>
          <div className="col-span-6 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <span className="label">Family link (optional)</span>
            <div className="flex items-center gap-2 mt-1 text-sm text-slate-600">
              This patient is the
              <select className={`${input} !w-auto`} value={f.relation} onChange={(e) => set("relation", e.target.value)}>
                {RELATIONS.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              of
              <select data-testid="reg-family" className={`${input} !w-auto flex-1`} value={f.family_of} onChange={(e) => set("family_of", e.target.value)}>
                <option value="">— nobody —</option>
                {others.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.id} · {p.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
        {err && <div className="mt-3 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{err}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="btn-ghost">
            Cancel
          </button>
          <button data-testid="reg-submit" onClick={submit} disabled={saving} className="btn-primary">
            <UserPlus className="h-4 w-4" /> {saving ? "Saving…" : "Register & switch to patient"}
          </button>
        </div>
      </div>
    </div>
  );
}
