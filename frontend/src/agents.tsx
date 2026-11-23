import {
  BellRing,
  Brain,
  CalendarClock,
  Cpu,
  Network,
  Radar,
  Receipt,
  ShieldCheck,
  Siren,
  Stethoscope,
  User,
} from "lucide-react";
import type { ComponentType } from "react";

export type AgentMeta = {
  key: string;
  label: string;
  role: string;
  icon: ComponentType<{ className?: string }>;
  dot: string; // bg colour
  text: string; // text colour
  soft: string; // soft bg
  ring: string;
};

export const AGENTS: AgentMeta[] = [
  { key: "supervisor", label: "Supervisor", role: "decomposes & dispatches", icon: Network, dot: "bg-violet-500", text: "text-violet-700", soft: "bg-violet-50", ring: "ring-violet-400" },
  { key: "triage", label: "Triage", role: "symptoms → specialty", icon: Stethoscope, dot: "bg-rose-500", text: "text-rose-700", soft: "bg-rose-50", ring: "ring-rose-400" },
  { key: "memory", label: "Memory", role: "long-term recall", icon: Brain, dot: "bg-emerald-500", text: "text-emerald-700", soft: "bg-emerald-50", ring: "ring-emerald-400" },
  { key: "scheduling", label: "Scheduling", role: "ReAct · picks tools", icon: CalendarClock, dot: "bg-blue-500", text: "text-blue-700", soft: "bg-blue-50", ring: "ring-blue-400" },
  { key: "billing", label: "Billing", role: "fees & insurance", icon: Receipt, dot: "bg-amber-500", text: "text-amber-700", soft: "bg-amber-50", ring: "ring-amber-400" },
  { key: "critic", label: "Critic", role: "verifies proposals", icon: ShieldCheck, dot: "bg-cyan-500", text: "text-cyan-700", soft: "bg-cyan-50", ring: "ring-cyan-400" },
  { key: "notification", label: "Notify", role: "drafts & sends", icon: BellRing, dot: "bg-teal-500", text: "text-teal-700", soft: "bg-teal-50", ring: "ring-teal-400" },
  { key: "event_watcher", label: "Event Watcher", role: "proactive, no prompt", icon: Radar, dot: "bg-fuchsia-500", text: "text-fuchsia-700", soft: "bg-fuchsia-50", ring: "ring-fuchsia-400" },
];

const EXTRA: Record<string, AgentMeta> = {
  guardrail: { key: "guardrail", label: "Guardrail", role: "hard rules", icon: Siren, dot: "bg-red-600", text: "text-red-700", soft: "bg-red-50", ring: "ring-red-400" },
  human: { key: "human", label: "Patient", role: "human", icon: User, dot: "bg-slate-500", text: "text-slate-700", soft: "bg-slate-100", ring: "ring-slate-400" },
  system: { key: "system", label: "System", role: "", icon: Cpu, dot: "bg-slate-400", text: "text-slate-500", soft: "bg-slate-50", ring: "ring-slate-300" },
};

export function agentMeta(key: string): AgentMeta {
  return AGENTS.find((a) => a.key === key) ?? EXTRA[key] ?? EXTRA.system;
}
