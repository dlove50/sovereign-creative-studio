import { formRequest, request, requestVoid } from "./core";

export type PerformerState = "SINGING" | "SPEAKING" | "BACKGROUND_VOCAL" | "LISTENING" | "MOVING" | "IDLE";
export type PerformanceMode = "alternating" | "call_response" | "harmony" | "lead_background" | "shared_stage";
export type PerformerRole = "lead" | "co_lead" | "background" | "actor";
export type ShotKind = "wide" | "two_shot" | "close_up" | "alternating";

export const VOICED: PerformerState[] = ["SINGING", "SPEAKING", "BACKGROUND_VOCAL"];

export type Region = {
  id: string;
  start: number;
  end: number;
  state: PerformerState;
  intensity: number;
  lyric: string;
  source: "own" | "shared";
  manual: boolean;
};

export type JointEdit = { joint: string; keyframes: { time: number; dx: number; dy: number }[] };

export type Performer = {
  visual_delay_ms?: number;
  reference?: { id: string; status: string; duration: number; edits: JointEdit[] };
  reference_pending?: { status: string; error?: string } | null;
  id: string;
  name: string;
  role: PerformerRole;
  voice_id: string | null;
  motion: { seed: number; sway: number; energy: number; phase: number; head?: number; shoulders?: number; hands?: number;
    expression?: "natural" | "joyful" | "intense" | "tender" | "restrained";
    gaze?: "automatic" | "audience" | "partner" | "left" | "right" };
  stage: { x: number; scale: number; facing: "audience" | "left" | "right" | "partner" };
  regions: Region[];
  stem_url: string | null;
  identity_url: string | null;
  drive_audio_url: string | null;
};

export type CameraShot = { start: number; end: number; shot: ShotKind; focus: string | null };

export type SheetRow = { start: number; end: number; performers: Record<string, PerformerState>; camera: string };

export type PerformanceRender = {
  status: "queued" | "running" | "done" | "error" | "cancelled";
  stage: string;
  progress: number;
  error: string | null;
  video_url: string | null;
  preview_url?: string | null;
  master_shot_url: string | null;
};

export type Performance = {
  visual_delay_ms?: number;
  id: string;
  title: string;
  mode: PerformanceMode;
  render_strategy?: "shared_pass" | "independent_layers";
  duration: number;
  performers: Performer[];
  camera: CameraShot[];
  stage: { prompt: string; aspect: string; image_url: string | null };
  master_audio_url: string | null;
  shared_vocal_url: string | null;
  sheet: SheetRow[];
  render?: PerformanceRender;
  created_at: string;
  updated_at: string;
};

export type RenderPlan = { ready: boolean; missing: string[]; strategy: string };

const base = "/api/performances";
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const file = (f: File) => {
  const form = new FormData();
  form.append("file", f);
  return form;
};

export const performancesApi = {
  modes: () => request<{ modes: Record<PerformanceMode, string> }>(`${base}/modes`),
  readiness: () => request<{ ready: boolean; missing: string[] }>(`${base}/readiness`),
  list: () => request<Performance[]>(base),
  get: (id: string) => request<Performance>(`${base}/${id}`),
  create: (title: string, performers: string[], mode: PerformanceMode) =>
    request<Performance>(base, json("POST", { title, performers, mode })),
  patch: (id: string, body: { visual_delay_ms?: number; title?: string; mode?: PerformanceMode; render_strategy?: Performance["render_strategy"]; camera?: CameraShot[]; stage?: { prompt: string; aspect: string } }) =>
    request<Performance>(`${base}/${id}`, json("PATCH", body)),
  remove: (id: string) => requestVoid(`${base}/${id}`, { method: "DELETE" }),
  uploadMaster: (id: string, f: File) => formRequest<Performance>(`${base}/${id}/master`, file(f)),
  uploadStage: (id: string, f: File) => formRequest<Performance>(`${base}/${id}/stage-image`, file(f)),
  uploadStem: (id: string, pid: string, f: File) => formRequest<Performance>(`${base}/${id}/performers/${pid}/stem`, file(f)),
  uploadIdentity: (id: string, pid: string, f: File) =>
    formRequest<Performance>(`${base}/${id}/performers/${pid}/identity`, file(f)),
  patchPerformer: (id: string, pid: string, body: Partial<Pick<Performer, "name" | "role" | "stage" | "voice_id" | "visual_delay_ms">> & { motion?: Partial<Performer["motion"]> }) =>
    request<Performance>(`${base}/${id}/performers/${pid}`, json("PATCH", body)),
  uploadReference: (id: string, pid: string, f: File) => formRequest<Performance>(`${base}/${id}/performers/${pid}/reference`, file(f)),
  referencePose: (id: string, pid: string, time: number) => request<{width: number; height: number; frame: {keypoints: number[][]; scores: number[]}}>(`${base}/${id}/performers/${pid}/reference/pose?time=${time}`),
  referenceEdits: (id: string, pid: string, edits: JointEdit[]) => request<Performance>(`${base}/${id}/performers/${pid}/reference/edits`, json("PUT", {edits})),
  detachReference: (id: string, pid: string) => request<Performance>(`${base}/${id}/performers/${pid}/reference`, {method: "DELETE"}),
  putRegions: (id: string, pid: string, regions: Omit<Region, "manual">[]) =>
    request<Performance>(`${base}/${id}/performers/${pid}/regions`, json("PUT", { regions })),
  analyze: (id: string) => request<Performance>(`${base}/${id}/analyze`, { method: "POST" }),
  plan: (id: string) => request<RenderPlan>(`${base}/${id}/render-plan`),
  render: (id: string) => request<Performance>(`${base}/${id}/render`, { method: "POST" }),
  cancelRender: (id: string) => request<{ cancelling: boolean }>(`${base}/${id}/render/cancel`, { method: "POST" }),
};

export const STATE_STYLE: Record<PerformerState, { label: string; className: string }> = {
  SINGING: { label: "Singing", className: "bg-fuchsia-500/70 border-fuchsia-300/60" },
  SPEAKING: { label: "Speaking", className: "bg-sky-500/70 border-sky-300/60" },
  BACKGROUND_VOCAL: { label: "Backing vocal", className: "bg-violet-500/50 border-violet-300/50" },
  LISTENING: { label: "Listening", className: "bg-emerald-500/25 border-emerald-300/40" },
  MOVING: { label: "Moving", className: "bg-amber-500/40 border-amber-300/50" },
  IDLE: { label: "Idle", className: "bg-white/5 border-white/10" },
};

export function clock(seconds: number): string {
  const s = Math.max(0, seconds);
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}
