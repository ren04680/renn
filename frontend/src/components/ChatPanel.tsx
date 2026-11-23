import {
  AlertTriangle,
  Bot,
  Building2,
  CalendarDays,
  Check,
  Clock,
  IndianRupee,
  Loader2,
  MapPin,
  Radar,
  Send,
  ShieldCheck,
  Siren,
  Sparkles,
  Star,
  Video,
  X,
} from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { SPEC_LABEL, dayLabel } from "../api";
import type { ChatMsg, Interrupt, Offer, Patient, Proposal, ProposalItem } from "../types";

const EXAMPLES: Record<string, string[]> = {
  P001: [
    "Book with my usual doctor next week",
    "Book a cardiologist for me and a dermatologist for my mother on the same day, back to back, same hospital if possible",
    "How much will it cost with my insurance?",
    "I need a dermatologist in Baner tomorrow morning",
  ],
  GUEST: [
    "I want to see a doctor",
    "Pediatrician in Kothrud tomorrow between 10 and 11 am",
    "ENT specialist in Hadapsar tomorrow",
    "I need a gastroenterologist tomorrow",
    "mere ghutne mein dard hai, Kothrud mein dikhana hai",
    "severe chest pain and sweating",
  ],
  DEFAULT: [
    "Neurologist in Shivajinagar tomorrow morning",
    "How much will it cost with my insurance?",
    "I have an itchy rash on my arm, please book something this week",
    "Book with my usual doctor next week",
  ],
};

export function Md({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
            part.startsWith("**") && part.endsWith("**") ? (
              <strong key={j} className="font-semibold">
                {part.slice(2, -2)}
              </strong>
            ) : (
              <Fragment key={j}>{part}</Fragment>
            ),
          )}
        </Fragment>
      ))}
    </>
  );
}

function ItemRow({ it, showPatient }: { it: ProposalItem; showPatient: boolean }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
      {showPatient && <div className="label mb-1.5">For {it.patient_name} ({it.patient_id})</div>}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-slate-900">{it.doctor_name}</div>
          <div className="text-xs text-slate-500 flex items-center gap-2">
            {SPEC_LABEL[it.specialty] ?? it.specialty}
            <span className="inline-flex items-center gap-0.5">
              <Star className="h-3 w-3 fill-amber-400 text-amber-400" /> {it.rating}
            </span>
            <span className="font-mono text-[10px] text-slate-400">
              {it.doctor_id} · {it.slot_id}
            </span>
          </div>
        </div>
        {it.mode === "tele" ? (
          <span className="chip bg-sky-100 text-sky-800">
            <Video className="h-3 w-3" /> Teleconsult
          </span>
        ) : (
          <span className="chip bg-emerald-100 text-emerald-800">
            <Building2 className="h-3 w-3" /> In person
          </span>
        )}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[13px] text-slate-700">
        <div className="flex items-center gap-1.5">
          <CalendarDays className="h-3.5 w-3.5 text-slate-400" /> {dayLabel(it.date)}
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5 text-slate-400" /> {it.start}–{it.end}
        </div>
        <div className="flex items-center gap-1.5 col-span-2">
          <MapPin className="h-3.5 w-3.5 text-slate-400" /> {it.hospital_name}, {it.locality}
        </div>
      </div>
      {it.cost && (
        <div className="mt-2 flex items-center justify-between rounded-lg bg-white border border-slate-200 px-2.5 py-1.5 text-[12.5px]">
          <span className="text-slate-500">
            Fee ₹{it.cost.fee} · {it.cost.plan_name} {it.cost.coverage_pct}% ({it.cost.basis})
            {it.cost.copay ? ` · copay ₹${it.cost.copay}` : ""}
          </span>
          <span className="font-semibold text-slate-900 flex items-center">
            You pay <IndianRupee className="h-3.5 w-3.5 ml-1" />
            {it.cost.patient_pays}
          </span>
        </div>
      )}
    </div>
  );
}

function ProposalCard({ m, busy, onDecide }: { m: ChatMsg; busy: boolean; onDecide: (m: ChatMsg, ok: boolean) => void }) {
  const p = m.proposal as Proposal;
  const multi = p.items.length > 1 || p.items.some((i) => i.patient_id !== p.items[0].patient_id);
  return (
    <div data-testid="approval-card" className="card overflow-hidden border-indigo-200 animate-slideIn">
      <div className="px-4 py-2.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white flex items-center gap-2">
        <ShieldCheck className="h-4 w-4" />
        <span className="text-sm font-semibold">{p.kind === "joint" ? "Combined proposal — one approval" : "Proposal — needs your approval"}</span>
        <span className="ml-auto text-[11px] text-indigo-100">Critic ✓ verified · held 5 min</span>
      </div>
      <div className="p-3.5 space-y-2.5">
        {p.reschedule_of && (
          <div className="text-xs text-slate-500">
            Moving appointment {p.reschedule_of.appointment_id} ({p.reschedule_of.doctor_name}, {p.reschedule_of.date} {p.reschedule_of.start})
          </div>
        )}
        {p.items.map((it) => (
          <ItemRow key={it.slot_id} it={it} showPatient={multi} />
        ))}
        {p.items.length > 1 && p.total_patient_pays !== undefined && (
          <div className="text-right text-sm font-semibold">Total you pay: ₹{p.total_patient_pays}</div>
        )}
        {p.disclosures.length > 0 && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 p-2.5 text-[12.5px] text-amber-900">
            <div className="font-semibold flex items-center gap-1.5 mb-1">
              <AlertTriangle className="h-3.5 w-3.5" /> What I changed from your request
            </div>
            <ul className="list-disc pl-5 space-y-0.5">
              {p.disclosures.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          </div>
        )}
        {p.preference_notes.length > 0 && (
          <div className="text-[12px] text-slate-600 flex gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-violet-500 shrink-0 mt-0.5" />
            <span>
              <span className="font-medium">Why this slot:</span> {p.preference_notes.join(" · ")}
            </span>
          </div>
        )}
        {m.resolved ? (
          <div className={`text-sm font-medium ${m.resolved === "approved" ? "text-emerald-700" : "text-slate-500"}`}>
            {m.resolved === "approved" ? "✓ You approved this" : "✕ You rejected this"}
          </div>
        ) : (
          <div className="flex gap-2 pt-1">
            <button data-testid="approve-btn" disabled={busy} onClick={() => onDecide(m, true)} className="btn-primary flex-1 bg-emerald-600 hover:bg-emerald-700">
              <Check className="h-4 w-4" /> Approve & book
            </button>
            <button data-testid="reject-btn" disabled={busy} onClick={() => onDecide(m, false)} className="btn-danger">
              <X className="h-4 w-4" /> Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function OfferCard({ o, busy, onOffer }: { o: Offer; busy: boolean; onOffer: (o: Offer, ok: boolean) => void }) {
  return (
    <div data-testid="offer-card" className="card border-fuchsia-200 overflow-hidden animate-slideIn">
      <div className="px-4 py-2 bg-gradient-to-r from-fuchsia-600 to-pink-600 text-white flex items-center gap-2">
        <Radar className="h-4 w-4" />
        <span className="text-sm font-semibold">{o.kind === "reschedule" ? "Proactive reschedule — your doctor cancelled" : "A slot opened up for you"}</span>
        <span className="ml-auto text-[11px] text-fuchsia-100">held {o.expires_in_min} min · no prompt needed</span>
      </div>
      <div className="p-3.5 space-y-2">
        {o.old_appointment && (
          <div className="text-[12.5px] text-slate-600">
            <span className="line-through">
              {o.old_appointment.doctor_name} · {dayLabel(o.old_appointment.date)} {o.old_appointment.start}
            </span>{" "}
            <span className="chip bg-rose-100 text-rose-700">cancelled by doctor</span>
          </div>
        )}
        <ItemRow it={{ ...o.slot, cost: o.cost, patient_id: o.patient_id, patient_name: o.patient_name, goal_ref: "" } as any} showPatient={false} />
        <div className="text-[12px] text-slate-600 flex gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-fuchsia-500 shrink-0 mt-0.5" />
          <span>
            <span className="font-medium">Chosen using your memory:</span> {o.why.join(" · ")}
          </span>
        </div>
        <div className="flex gap-2">
          <button data-testid="offer-accept" disabled={busy} onClick={() => onOffer(o, true)} className="btn-primary flex-1 bg-fuchsia-600 hover:bg-fuchsia-700">
            <Check className="h-4 w-4" /> Confirm new slot
          </button>
          <button disabled={busy} onClick={() => onOffer(o, false)} className="btn-danger">
            <X className="h-4 w-4" /> Decline
          </button>
        </div>
      </div>
    </div>
  );
}

type Props = {
  patient?: Patient;
  messages: ChatMsg[];
  busy: boolean;
  pending: Interrupt | null;
  onSend: (t: string) => void;
  onDecide: (m: ChatMsg, ok: boolean) => void;
  offers: Offer[];
  onOffer: (o: Offer, ok: boolean) => void;
  injectFault: boolean;
};

export default function ChatPanel({ patient, messages, busy, pending, onSend, onDecide, offers, onOffer, injectFault }: Props) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy, offers.length]);
  const examples = EXAMPLES[patient?.id ?? "DEFAULT"] ?? EXAMPLES.DEFAULT;
  const submit = () => {
    const t = text.trim();
    if (!t || busy) return;
    setText("");
    onSend(t);
  };
  return (
    <section className="card flex flex-col min-h-0 h-full">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-3">
        <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white grid place-items-center text-sm font-semibold">
          {patient?.id === "GUEST" ? "G" : patient?.name?.split(" ").map((x) => x[0]).join("").slice(0, 2)}
        </div>
        <div className="leading-tight">
          <div className="font-semibold text-slate-900">{patient?.id === "GUEST" ? "Guest (walk-in)" : patient?.name ?? "…"}</div>
          <div className="text-xs text-slate-500">
            {patient?.id} {patient?.locality ? `· ${patient.locality}` : ""} {patient?.plan ? `· ${patient.plan}` : ""}
          </div>
        </div>
        {injectFault && (
          <span className="ml-auto chip bg-amber-100 text-amber-800">debug: next proposal will be faulty</span>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin p-4 space-y-3" data-testid="chat-scroll">
        {offers.map((o) => (
          <OfferCard key={o.offer_id} o={o} busy={busy} onOffer={onOffer} />
        ))}
        {messages.length === 0 && offers.length === 0 && (
          <div className="text-center py-8">
            <div className="mx-auto h-12 w-12 rounded-2xl bg-indigo-50 grid place-items-center mb-3">
              <Bot className="h-6 w-6 text-indigo-600" />
            </div>
            <div className="font-semibold text-slate-800">How can I help with your appointment?</div>
            <div className="text-sm text-slate-500 mt-1">I can book, plan for family, use what I remember about you, and explain costs.</div>
          </div>
        )}
        {messages.map((m, idx) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end animate-slideIn">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 text-white px-3.5 py-2 text-[14px] shadow-sm">{m.text}</div>
            </div>
          ) : m.kind === "approval" && m.proposal ? (
            <ProposalCard key={m.id} m={m} busy={busy} onDecide={onDecide} />
          ) : (
            <div key={m.id} className="flex gap-2 animate-slideIn">
              <div
                className={`h-7 w-7 shrink-0 rounded-full grid place-items-center ${
                  m.kind === "emergency" ? "bg-red-600 text-white" : "bg-slate-900 text-white"
                }`}
              >
                {m.kind === "emergency" ? <Siren className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
              </div>
              <div
                data-testid={`assistant-${m.kind}`}
                className={`max-w-[88%] rounded-2xl rounded-tl-md px-3.5 py-2 text-[14px] leading-relaxed border ${
                  m.kind === "emergency"
                    ? "bg-red-50 border-red-200 text-red-900"
                    : m.kind === "booked"
                      ? "bg-emerald-50 border-emerald-200 text-emerald-950"
                      : m.kind === "waitlisted"
                        ? "bg-amber-50 border-amber-200 text-amber-950"
                        : m.kind === "clarification"
                          ? "bg-violet-50 border-violet-200 text-violet-950"
                          : "bg-white border-slate-200"
                }`}
              >
                <Md text={m.text} />
                {m.kind === "clarification" && idx === messages.length - 1 && pending?.kind === "clarification" && (m.suggestions?.length ?? 0) > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5" data-testid="quick-replies">
                    {m.suggestions!.map((sgt) => (
                      <button
                        key={sgt}
                        disabled={busy}
                        onClick={() => onSend(sgt)}
                        className="rounded-full bg-white border border-violet-300 text-violet-800 hover:bg-violet-600 hover:text-white px-3 py-1 text-[12.5px] font-medium transition"
                      >
                        {sgt}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ),
        )}
        {busy && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Agents are working — watch the Agent Activity panel →
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="border-t border-slate-100 p-3 space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {examples.map((e) => (
            <button
              key={e}
              onClick={() => !busy && onSend(e)}
              disabled={busy}
              className="text-left text-[11.5px] rounded-full border border-slate-200 bg-slate-50 hover:bg-indigo-50 hover:border-indigo-200 px-2.5 py-1 text-slate-600 max-w-full truncate"
              title={e}
            >
              {e.length > 70 ? e.slice(0, 68) + "…" : e}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            data-testid="chat-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder={pending?.kind === "clarification" ? "Answer the question…" : "Describe what you need (English or Hinglish)…"}
            className="flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button data-testid="send-btn" onClick={submit} disabled={busy || !text.trim()} className="btn-primary px-4">
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  );
}
