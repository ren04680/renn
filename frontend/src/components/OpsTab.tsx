import { Bell, CalendarX2, ListOrdered, Mail, MessageSquare, Radar, RefreshCw, Sparkles, Video } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { SPEC_LABEL, api, dayLabel, fmtTime } from "../api";
import type { Offer, TraceEvent } from "../types";

type Doc = { id: string; name: string; specialty: string; hospital: string; locality: string; tele: boolean };
type Sched = {
  day: string;
  times: string[];
  doctors: { doctor_id: string; name: string; specialty: string; hospital: string; locality: string; slots: Record<string, any> }[];
};

const CELL: Record<string, string> = {
  free: "bg-emerald-100 hover:bg-emerald-200 border-emerald-200",
  booked: "bg-slate-300/70 border-slate-300",
  held: "bg-amber-300 border-amber-400",
  cancelled: "bg-rose-100 border-rose-300 striped",
};

export default function OpsTab({ events, meta, resetKey }: { events: TraceEvent[]; meta: any; resetKey: number }) {
  const days: string[] = meta?.days ?? [];
  const [docs, setDocs] = useState<Doc[]>([]);
  const [day, setDay] = useState<string>(days[2] ?? "");
  const [spec, setSpec] = useState<string>("cardiology");
  const [sched, setSched] = useState<Sched | null>(null);
  const [appts, setAppts] = useState<any[]>([]);
  const [wl, setWl] = useState<any[]>([]);
  const [notes, setNotes] = useState<any[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [freeable, setFreeable] = useState<any[]>([]);
  const [cDoc, setCDoc] = useState("D01");
  const [cDay, setCDay] = useState(days[2] ?? "");
  const [cFrom, setCFrom] = useState("09:30");
  const [cTo, setCTo] = useState("12:00");
  const [fSlot, setFSlot] = useState("");
  const [fired, setFired] = useState<string | null>(null);

  useEffect(() => {
    if (days.length && !day) setDay(days[2]);
    if (days.length && !cDay) setCDay(days[2]);
  }, [days, day, cDay]);

  const load = useCallback(() => {
    if (!day) return;
    api<Sched>(`/ops/schedule?day=${day}${spec ? `&specialty=${spec}` : ""}`).then(setSched).catch(() => {});
    api("/ops/appointments").then(setAppts).catch(() => {});
    api("/ops/waitlist").then(setWl).catch(() => {});
    api("/ops/notifications?limit=30").then(setNotes).catch(() => {});
    api<Offer[]>("/offers").then(setOffers).catch(() => {});
    api<any[]>("/ops/freeable_slots").then((f) => {
      setFreeable(f);
      setFSlot((cur) => cur || f[0]?.slot_id || "");
    }).catch(() => {});
  }, [day, spec]);

  useEffect(() => {
    api<Doc[]>("/ops/doctors").then(setDocs).catch(() => {});
  }, [resetKey]);

  const tick = useMemo(() => events.filter((e) => ["tool_result", "run_status", "offer", "notification"].includes(e.type)).length, [events]);
  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load, tick, resetKey]);

  const fireCancel = async () => {
    const r = await api<any>("/events/doctor_cancel", { doctor_id: cDoc, date: cDay, start: cFrom, end: cTo });
    setFired(`Event ${r.event_id} published → Event Watcher woke up (see Patient tab → Agent Activity)`);
    const d = docs.find((x) => x.id === cDoc);
    if (d) {
      setSpec(d.specialty);
      setDay(cDay);
    }
  };
  const fireFreed = async () => {
    if (!fSlot) return;
    const r = await api<any>("/events/slot_freed", { slot_id: fSlot });
    setFired(`Event ${r.event_id} published → slot ${fSlot} offered to the best waitlisted patient`);
  };
  const times = ["09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "16:00", "16:30", "17:00", "17:30", "18:00", "18:30"];

  return (
    <div className="h-full overflow-y-auto scroll-thin p-4 grid grid-cols-1 xl:grid-cols-[400px_1fr] gap-4">
      <div className="space-y-4">
        <div className="card p-4" data-testid="event-sim">
          <div className="flex items-center gap-2 mb-1">
            <Radar className="h-4 w-4 text-fuchsia-600" />
            <div className="font-semibold">Event simulator</div>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            Hospital events go onto an asyncio event bus. The Event Watcher reacts <b>with no user prompt</b>: recall → alternatives → hold → notify.
            Patients still confirm.
          </p>
          <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3 space-y-2">
            <div className="text-sm font-semibold text-rose-800 flex items-center gap-1.5">
              <CalendarX2 className="h-4 w-4" /> Doctor cancels block
            </div>
            <select value={cDoc} onChange={(e) => setCDoc(e.target.value)} className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm bg-white">
              {docs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.id} · {d.name} · {SPEC_LABEL[d.specialty]} · {d.locality}
                </option>
              ))}
            </select>
            <div className="grid grid-cols-3 gap-2">
              <select value={cDay} onChange={(e) => setCDay(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm bg-white">
                {days.map((d) => (
                  <option key={d} value={d}>
                    {dayLabel(d)}
                  </option>
                ))}
              </select>
              <select value={cFrom} onChange={(e) => setCFrom(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm bg-white">
                {times.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
              <select value={cTo} onChange={(e) => setCTo(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm bg-white">
                {times.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <button data-testid="fire-cancel" onClick={fireCancel} className="btn-primary w-full bg-rose-600 hover:bg-rose-700">
              <CalendarX2 className="h-4 w-4" /> Fire “doctor cancels block”
            </button>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 space-y-2 mt-3">
            <div className="text-sm font-semibold text-emerald-800 flex items-center gap-1.5">
              <Sparkles className="h-4 w-4" /> Slot freed (patient cancelled)
            </div>
            <select value={fSlot} onChange={(e) => setFSlot(e.target.value)} className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm bg-white">
              {freeable.length === 0 && <option value="">no booked slot matches a waitlist entry</option>}
              {freeable.map((f) => (
                <option key={f.slot_id} value={f.slot_id}>
                  {f.slot_id} · {f.label} (waitlist: {f.for_waitlist})
                </option>
              ))}
            </select>
            <button data-testid="fire-freed" onClick={fireFreed} disabled={!fSlot} className="btn-primary w-full bg-emerald-600 hover:bg-emerald-700">
              <Sparkles className="h-4 w-4" /> Fire “slot freed”
            </button>
          </div>
          {fired && <div className="mt-2 text-xs text-fuchsia-700 bg-fuchsia-50 rounded-lg px-2 py-1.5">{fired}</div>}
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Bell className="h-4 w-4 text-fuchsia-600" />
            <div className="font-semibold">Proactive offers</div>
            <span className="ml-auto text-xs text-slate-400">{offers.length}</span>
          </div>
          <div className="space-y-1.5 max-h-64 overflow-y-auto scroll-thin">
            {offers.length === 0 && <div className="text-xs text-slate-400">None yet.</div>}
            {offers.map((o) => (
              <div key={o.offer_id} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px]">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10.5px] text-slate-400">{o.offer_id}</span>
                  <span className="font-medium">
                    {o.patient_name} ({o.patient_id})
                  </span>
                  <span
                    className={`ml-auto chip ${
                      o.status === "pending" ? "bg-amber-100 text-amber-800" : o.status === "accepted" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {o.status}
                  </span>
                </div>
                <div className="text-slate-600">
                  {o.slot.doctor_name} · {o.slot.date} {o.slot.start} {o.slot.mode === "tele" && <Video className="inline h-3 w-3" />} — {o.why.join(", ")}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="h-4 w-4 text-teal-600" />
            <div className="font-semibold">Notification outbox</div>
            <span className="text-xs text-slate-400">mock SMS / email</span>
          </div>
          <div className="space-y-1.5 max-h-80 overflow-y-auto scroll-thin" data-testid="outbox">
            {notes.length === 0 && <div className="text-xs text-slate-400">Empty.</div>}
            {notes.map((n) => (
              <div key={n.id} className="rounded-lg bg-slate-50 border border-slate-200 px-2.5 py-1.5 text-[12px]">
                <div className="flex items-center gap-1.5 text-slate-500">
                  {n.channel === "sms" ? <MessageSquare className="h-3 w-3" /> : <Mail className="h-3 w-3" />}
                  <span className="font-medium text-slate-700">{n.patient_id}</span> {n.to}
                  <span
                    className={`chip ml-1 ${n.kind === "emergency" ? "bg-red-100 text-red-700" : n.kind === "offer" ? "bg-fuchsia-100 text-fuchsia-700" : "bg-teal-100 text-teal-700"}`}
                  >
                    {n.kind}
                  </span>
                  <span className="ml-auto font-mono text-[10px]">{fmtTime(n.created_at)}</span>
                </div>
                <div className="font-medium text-slate-800">{n.subject}</div>
                <div className="text-slate-600">{n.body}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-4 min-w-0">
        <div className="card p-4">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="font-semibold">Doctor schedule</div>
            <select value={spec} onChange={(e) => setSpec(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1 text-sm">
              <option value="">All specialties</option>
              {Object.entries(SPEC_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <button onClick={load} className="btn-ghost !py-1">
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <div className="ml-auto flex items-center gap-3 text-[11px] text-slate-500">
              {Object.entries({ free: "free", booked: "booked", held: "held (TTL)", cancelled: "cancelled" }).map(([k, v]) => (
                <span key={k} className="flex items-center gap-1">
                  <span className={`h-3 w-3 rounded border ${CELL[k]}`} /> {v}
                </span>
              ))}
            </div>
          </div>
          <div className="flex gap-1 mt-3 overflow-x-auto scroll-thin pb-1">
            {days.map((d) => (
              <button
                key={d}
                onClick={() => setDay(d)}
                className={`shrink-0 rounded-lg px-2.5 py-1 text-[11.5px] border ${day === d ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200 text-slate-600"}`}
              >
                {dayLabel(d)}
              </button>
            ))}
          </div>
          <div className="mt-3 overflow-x-auto scroll-thin" data-testid="schedule-grid">
            <table className="w-full text-[12px] border-separate border-spacing-1">
              <thead>
                <tr>
                  <th className="text-left font-medium text-slate-500 px-1">Doctor</th>
                  {sched?.times.map((t) => (
                    <th key={t} className="font-mono font-normal text-slate-500 text-[10.5px]">
                      {t}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sched?.doctors.length === 0 && (
                  <tr>
                    <td colSpan={11} className="text-slate-400 text-center py-4">
                      Nobody works this day for this specialty.
                    </td>
                  </tr>
                )}
                {sched?.doctors.map((d) => (
                  <tr key={d.doctor_id}>
                    <td className="pr-2 whitespace-nowrap">
                      <div className="font-medium text-slate-800">{d.name}</div>
                      <div className="text-[10.5px] text-slate-500">
                        {SPEC_LABEL[d.specialty]} · {d.locality}
                      </div>
                    </td>
                    {sched.times.map((t) => {
                      const s = d.slots[t];
                      if (!s) return <td key={t} className="h-8 min-w-[52px] rounded-md bg-slate-50" />;
                      return (
                        <td
                          key={t}
                          title={`${s.slot_id} · ${s.status}${s.patient ? ` · ${s.patient}` : ""}${s.mode === "tele" ? " · tele" : ""}`}
                          className={`h-8 min-w-[52px] rounded-md border text-center align-middle ${CELL[s.status] ?? ""}`}
                        >
                          <div className="flex items-center justify-center gap-0.5 text-[10px] font-medium text-slate-700">
                            {s.mode === "tele" && <Video className="h-3 w-3" />}
                            {s.patient && s.patient !== "walk-in" ? s.patient : s.status === "held" ? "hold" : ""}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
          <div className="card p-4 min-w-0">
            <div className="font-semibold mb-2">Appointments (registered patients, upcoming)</div>
            <div className="max-h-96 overflow-auto scroll-thin">
              <table className="w-full text-[12px]">
                <thead className="text-slate-500 text-left sticky top-0 bg-white">
                  <tr>
                    <th className="py-1">Ref</th>
                    <th>Patient</th>
                    <th>Doctor</th>
                    <th>When</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {appts.map((a) => (
                    <tr key={a.appointment_id} className="border-t border-slate-100">
                      <td className="py-1 font-mono text-[10.5px]">{a.appointment_id}</td>
                      <td>{a.patient_id}</td>
                      <td>
                        {a.doctor} <span className="text-slate-400">{SPEC_LABEL[a.specialty]}</span>
                      </td>
                      <td className="whitespace-nowrap">
                        {a.date} {a.start} {a.mode === "tele" && <Video className="inline h-3 w-3" />}
                      </td>
                      <td>
                        <span
                          className={`chip ${
                            a.status === "booked" && a.slot_status === "cancelled"
                              ? "bg-rose-100 text-rose-700"
                              : a.status === "booked"
                                ? "bg-emerald-100 text-emerald-700"
                                : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {a.status === "booked" && a.slot_status === "cancelled" ? "affected" : a.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="card p-4 min-w-0">
            <div className="font-semibold mb-2 flex items-center gap-1.5">
              <ListOrdered className="h-4 w-4" /> Waitlist
            </div>
            <table className="w-full text-[12px]">
              <thead className="text-slate-500 text-left">
                <tr>
                  <th className="py-1">Id</th>
                  <th>Patient</th>
                  <th>Specialty</th>
                  <th>Window</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {wl.map((w) => (
                  <tr key={w.id} className="border-t border-slate-100">
                    <td className="py-1 font-mono text-[10.5px]">{w.id}</td>
                    <td>
                      {w.patient_name} ({w.patient_id})
                    </td>
                    <td>{SPEC_LABEL[w.specialty]}</td>
                    <td className="whitespace-nowrap">
                      {w.date_from.slice(5)} → {w.date_to.slice(5)} {w.time_pref ?? ""}
                    </td>
                    <td>
                      <span className={`chip ${w.status === "waiting" ? "bg-amber-100 text-amber-800" : w.status === "fulfilled" ? "bg-emerald-100 text-emerald-700" : "bg-fuchsia-100 text-fuchsia-700"}`}>
                        {w.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
