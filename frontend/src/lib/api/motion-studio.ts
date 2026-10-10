import { API_BASE, formRequest, request } from "./core";

export type MotionOperation = {
  id: string; kind: "draft" | "final"; status: string; prompt: string; scene: string;
  remote_id: string | null; draft_id: string | null; file: string | null;
  error: string | null; expires_at?: string; created_at: string;
};
export type MotionJob = {
  id: string; title: string; status: string; approved: boolean; seconds: number;
  start: number; created_at: string; updated_at: string; files: string[];
  characters: number[]; operations: MotionOperation[]; error: string | null;
  selected_draft: string | null; final_file: string | null;
  media: { width: number; height: number; duration: number; has_audio: boolean };
};
export type MotionStatus = { local_ready: boolean; cloud_ready: boolean; max_seconds: number; max_upload_mb: number };
const base = "/api/motion-studio";
export const motionApi = {
  status: () => request<MotionStatus>(`${base}/status`),
  jobs: () => request<MotionJob[]>(`${base}/jobs`),
  get: (id: string) => request<MotionJob>(`${base}/jobs/${id}`),
  upload: (body: FormData) => formRequest<MotionJob>(`${base}/jobs`, body),
  character: (id: string, slot: number, file: File) => {
    const body = new FormData(); body.append("file", file);
    return formRequest<MotionJob>(`${base}/jobs/${id}/characters/${slot}`, body);
  },
  approve: (id: string) => request<MotionJob>(`${base}/jobs/${id}/approve`, { method: "POST" }),
  removeCharacter: (id: string, slot: number) => request<MotionJob>(`${base}/jobs/${id}/characters/${slot}`, { method: "DELETE" }),
  render: (id: string, kind: "draft" | "final", payload: object) =>
    request<MotionJob>(`${base}/jobs/${id}/render/${kind}`, { method: "POST", body: JSON.stringify(payload) }),
  refresh: (id: string) => request<MotionJob>(`${base}/jobs/${id}/refresh`, { method: "POST" }),
  file: (id: string, name: string) => `${API_BASE}${base}/jobs/${id}/files/${encodeURIComponent(name)}`,
};
