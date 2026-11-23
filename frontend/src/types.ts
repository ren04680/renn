export type TraceEvent = {
  seq: number;
  run_id: string;
  ts: number;
  agent: string;
  type: string;
  msg: string;
  payload: any;
};

export type Settings = {
  inject_fault: boolean;
  offline: boolean;
  offline_forced: boolean;
  offline_reason: string;
  llm_available: boolean;
  model: string;
};

export type Patient = {
  id: string;
  name: string;
  age: number;
  locality: string;
  plan: string;
  preferred_time: string | null;
  preferred_mode: string | null;
  family: { relation: string; patient_id: string }[];
};

export type Cost = {
  fee: number;
  insurer_pays: number;
  patient_pays: number;
  plan_name: string;
  coverage_pct: number;
  basis: string;
  copay: number;
};

export type ProposalItem = {
  goal_ref: string;
  patient_id: string;
  patient_name: string;
  slot_id: string;
  doctor_id: string;
  doctor_name: string;
  specialty: string;
  hospital_id: string;
  hospital_name: string;
  locality: string;
  date: string;
  start: string;
  end: string;
  mode: string;
  fee: number;
  rating: number;
  cost?: Cost;
};

export type Proposal = {
  proposal_id: string;
  kind: string;
  items: ProposalItem[];
  disclosures: string[];
  relaxations: { step: string; disclosure: string }[];
  skipped_steps: string[];
  rationale: string;
  preference_notes: string[];
  coupling?: Record<string, any> | null;
  total_patient_pays?: number;
  reschedule_of?: { appointment_id: string; date: string; start: string; doctor_name: string };
};

export type Interrupt =
  | { kind: "approval"; run_id: string; proposal: Proposal; question: string }
  | { kind: "clarification"; run_id: string; question: string; purpose?: string; suggestions?: string[] };

export type RunResult = {
  run_id: string;
  status: "waiting" | "done" | "error";
  interrupt: Interrupt | null;
  response: { kind: string; text: string; outcome?: any } | null;
  stats?: any;
};

export type ChatMsg = {
  id: string;
  role: "user" | "assistant";
  kind: string;
  text: string;
  runId?: string;
  proposal?: Proposal;
  suggestions?: string[];
  resolved?: "approved" | "rejected";
  ts: number;
};

export type Offer = {
  offer_id: string;
  run_id: string;
  event_id: string;
  patient_id: string;
  patient_name: string;
  kind: "reschedule" | "waitlist_fill";
  status: string;
  created_at: number;
  slot: ProposalItem & { slot_id: string };
  why: string[];
  old_appointment?: { appointment_id: string; doctor_name: string; date: string; start: string } | null;
  cost?: Cost;
  critic?: string;
  expires_in_min?: number;
};
