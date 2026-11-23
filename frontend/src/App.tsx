import { Activity, BarChart3, Building2, LayoutGrid, MessagesSquare } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, uid, useTraceStream } from "./api";
import ActivityPanel from "./components/ActivityPanel";
import BlackboardTab from "./components/BlackboardTab";
import ChatPanel from "./components/ChatPanel";
import MetricsTab from "./components/MetricsTab";
import OpsTab from "./components/OpsTab";
import RegisterModal from "./components/RegisterModal";
import TopBar from "./components/TopBar";
import type { ChatMsg, Interrupt, Offer, Patient, RunResult, Settings } from "./types";

type Tab = "patient" | "ops" | "blackboard" | "metrics";

export default function App() {
  const [resetKey, setResetKey] = useState(0);
  const { events, connected } = useTraceStream(resetKey);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [pid, setPid] = useState("P001");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("patient");
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  const [pending, setPending] = useState<Record<string, Interrupt | null>>({});
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<Record<string, string[]>>({});
  const [offers, setOffers] = useState<Offer[]>([]);
  const [resetting, setResetting] = useState(false);
  const [bbRun, setBbRun] = useState<string | null>(null);
  const [regOpen, setRegOpen] = useState(false);

  useEffect(() => {
    api<Patient[]>("/patients").then(setPatients).catch(() => {});
    api<Settings>("/settings").then(setSettings).catch(() => {});
    api("/meta").then(setMeta).catch(() => {});
  }, [resetKey]);

  // refresh pending offers whenever proactive activity happens
  const offerTick = useMemo(() => events.filter((e) => e.type === "offer" || (e.type === "run_status" && e.run_id.startsWith("px-"))).length, [events]);
  const loadOffers = useCallback(() => {
    api<Offer[]>(`/offers?patient_id=${pid}&status=pending`).then(setOffers).catch(() => {});
  }, [pid]);
  useEffect(() => {
    const t = setTimeout(loadOffers, 250);
    return () => clearTimeout(t);
  }, [loadOffers, offerTick, resetKey]);

  const push = (p: string, m: Omit<ChatMsg, "id" | "ts">) =>
    setChats((c) => ({ ...c, [p]: [...(c[p] ?? []), { ...m, id: uid(8), ts: Date.now() / 1000 }] }));

  const handleResult = (p: string, r: RunResult) => {
    if (r.status === "waiting" && r.interrupt) {
      setPending((x) => ({ ...x, [p]: r.interrupt }));
      if (r.interrupt.kind === "approval") {
        push(p, { role: "assistant", kind: "approval", text: r.interrupt.question, proposal: r.interrupt.proposal, runId: r.run_id });
      } else {
        push(p, { role: "assistant", kind: "clarification", text: r.interrupt.question, runId: r.run_id, suggestions: r.interrupt.suggestions ?? [] });
      }
    } else {
      setPending((x) => ({ ...x, [p]: null }));
      push(p, { role: "assistant", kind: r.response?.kind ?? "text", text: r.response?.text ?? "…", runId: r.run_id });
    }
  };

  const send = async (text: string) => {
    const p = pid;
    const pend = pending[p];
    push(p, { role: "user", kind: "text", text });
    setBusy(true);
    try {
      let r: RunResult;
      if (pend && pend.kind === "clarification") {
        r = await api<RunResult>("/resume", { run_id: pend.run_id, value: { text } });
      } else {
        const runId = uid(12);
        setRuns((x) => ({ ...x, [p]: [...(x[p] ?? []), runId] }));
        setBbRun(runId);
        r = await api<RunResult>("/chat", { patient_id: p, message: text, run_id: runId });
      }
      handleResult(p, r);
    } catch (e) {
      push(p, { role: "assistant", kind: "failed", text: `Request failed: ${String(e)}` });
    } finally {
      setBusy(false);
    }
  };

  const decide = async (msg: ChatMsg, approved: boolean) => {
    const p = pid;
    setChats((c) => ({ ...c, [p]: (c[p] ?? []).map((m) => (m.id === msg.id ? { ...m, resolved: approved ? "approved" : "rejected" } : m)) }));
    setBusy(true);
    try {
      const r = await api<RunResult>("/resume", { run_id: msg.runId, value: { approved } });
      handleResult(p, r);
    } catch (e) {
      push(p, { role: "assistant", kind: "failed", text: `Request failed: ${String(e)}` });
    } finally {
      setBusy(false);
    }
  };

  const respondOffer = async (o: Offer, accept: boolean) => {
    setBusy(true);
    try {
      const r = await api<any>(`/offers/${o.offer_id}/respond`, { accept });
      push(o.patient_id, {
        role: "assistant",
        kind: r.status === "accepted" ? "booked" : r.status,
        text:
          r.status === "accepted"
            ? `✅ Confirmed: **${r.appointment?.doctor_name}** on ${r.appointment?.date} at ${r.appointment?.start}. Ref **${r.appointment?.appointment_id}**. A confirmation SMS has been sent.`
            : r.status === "declined"
              ? "Okay — I released that slot. Your original appointment stays cancelled by the doctor; tell me what would suit you instead."
              : `That didn't work: ${r.error ?? r.status}. Nothing was changed.`,
        runId: o.run_id,
      });
      loadOffers();
    } finally {
      setBusy(false);
    }
  };

  const updateSettings = async (s: Partial<Settings> & { offline?: boolean }) => {
    const r = await api<Settings>("/settings", s);
    setSettings(r);
  };

  const reset = async () => {
    setResetting(true);
    try {
      await api("/reset", {});
      setChats({});
      setPending({});
      setRuns({});
      setOffers([]);
      setBbRun(null);
      setResetKey((k) => k + 1);
    } finally {
      setResetting(false);
    }
  };

  const patient = patients.find((p) => p.id === pid);
  const myRunIds = runs[pid] ?? [];
  const tabs: { key: Tab; label: string; icon: any }[] = [
    { key: "patient", label: "Patient", icon: MessagesSquare },
    { key: "ops", label: "Hospital Ops", icon: Building2 },
    { key: "blackboard", label: "Blackboard", icon: LayoutGrid },
    { key: "metrics", label: "Metrics", icon: BarChart3 },
  ];
  const proactiveCount = useRef(0);

  return (
    <div className="h-full flex flex-col">
      <TopBar
        patients={patients}
        pid={pid}
        setPid={setPid}
        settings={settings}
        updateSettings={updateSettings}
        onReset={reset}
        resetting={resetting}
        connected={connected}
        meta={meta}
        onNewPatient={() => setRegOpen(true)}
      />
      <RegisterModal
        open={regOpen}
        onClose={() => setRegOpen(false)}
        patients={patients}
        onCreated={async (id) => {
          const ps = await api<Patient[]>("/patients");
          setPatients(ps);
          setPid(id);
          setRegOpen(false);
          setTab("patient");
          const p = ps.find((x) => x.id === id);
          push(id, {
            role: "assistant",
            kind: "text",
            text: `Welcome, **${p?.name ?? id}**! You're registered as **${id}**. I've saved your preferences, so I won't need to ask for them again. How can I help — which doctor or problem?`,
          });
        }}
      />
      <div className="px-5 pt-3 flex items-center gap-1 border-b border-slate-200 bg-white">
        {tabs.map((t) => (
          <button
            key={t.key}
            data-testid={`tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`relative flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-xl transition ${
              tab === t.key ? "text-indigo-700 bg-indigo-50/60" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
            {t.key === "patient" && offers.length > 0 && (
              <span className="chip bg-fuchsia-600 text-white">{offers.length} offer</span>
            )}
            {tab === t.key && <span className="absolute inset-x-3 -bottom-px h-0.5 bg-indigo-600 rounded-full" />}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 pb-2 text-xs text-slate-500">
          <Activity className="h-3.5 w-3.5" /> {events.length} trace events
        </div>
      </div>
      <main className="flex-1 min-h-0 bg-slate-50">
        {tab === "patient" && (
          <div className="h-full grid grid-cols-1 lg:grid-cols-[minmax(380px,5fr)_7fr] gap-4 p-4 min-h-0">
            <ChatPanel
              patient={patient}
              messages={chats[pid] ?? []}
              busy={busy}
              pending={pending[pid] ?? null}
              onSend={send}
              onDecide={decide}
              offers={offers}
              onOffer={respondOffer}
              injectFault={!!settings?.inject_fault}
            />
            <ActivityPanel events={events} myRunIds={myRunIds} patientId={pid} busy={busy} />
          </div>
        )}
        {tab === "ops" && <OpsTab events={events} meta={meta} resetKey={resetKey} />}
        {tab === "blackboard" && <BlackboardTab events={events} selected={bbRun} setSelected={setBbRun} />}
        {tab === "metrics" && <MetricsTab />}
      </main>
      <span className="hidden">{proactiveCount.current}</span>
    </div>
  );
}
