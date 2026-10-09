import { request } from "./core";

export type DirectorField = { id: string; label: string; placeholder: string; required: boolean; long: boolean };

export type DirectorTemplate = {
  id: string;
  label: string;
  tagline: string;
  orientation: "portrait" | "landscape";
  seconds: { min: number; default: number; max: number };
  fields: DirectorField[];
  music: string | null;
  narration: boolean;
  badge: string | null;
  series: boolean;
  image: string;
};

export type DirectorShot = {
  id: string;
  duration: number;
  description: string;
  narration: string;
  status: "queued" | "running" | "done" | "error";
  video_id: string | null;
  clip_url: string | null;
  keyframe_url: string | null;
  error: string | null;
};

export type DirectorProject = {
  id: string;
  template: string;
  label: string;
  brief: Record<string, string>;
  seconds: number;
  orientation: "portrait" | "landscape";
  music: boolean;
  narration: boolean;
  voice_id: string | null;
  planner: "fast" | "best";
  series_id: string | null;
  episode: number | null;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  stage: string;
  message: string;
  title: string;
  shots: DirectorShot[];
  plan: {
    title: string;
    synopsis: string;
    characters: { id: string; name: string; description: string }[];
    locations: { id: string; name: string; description: string }[];
  } | null;
  notes: string[];
  result_url: string | null;
  error: string | null;
  credits_estimate: { clips_low: number; clips_high: number; per_clip: number; total_low: number; total_high: number };
  created_at: string;
};

export type DirectorSeries = {
  id: string;
  title: string;
  characters: { name: string; description: string }[];
  episodes: { number: number; project_id: string; synopsis: string }[];
};

export type StartInput = {
  template: string;
  brief: Record<string, string>;
  seconds: number;
  music: boolean;
  narration: boolean;
  voice_id?: string | null;
  planner?: "fast" | "best";
};

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const directorApi = {
  templates: () => request<{ credits_per_clip: number; templates: DirectorTemplate[] }>("/api/director/templates"),
  start: (input: StartInput) => post<DirectorProject>("/api/director/projects", input),
  projects: () => request<DirectorProject[]>("/api/director/projects"),
  project: (id: string) => request<DirectorProject>(`/api/director/projects/${id}`),
  cancel: (id: string) => post<{ cancelling: boolean }>(`/api/director/projects/${id}/cancel`),
  remove: (id: string) => request<void>(`/api/director/projects/${id}`, { method: "DELETE" }),
  series: (id: string) => request<DirectorSeries>(`/api/director/series/${id}`),
  nextEpisode: (seriesId: string, body: { direction: string; music: boolean; seconds?: number; planner?: "fast" | "best" }) =>
    post<DirectorProject>(`/api/director/series/${seriesId}/next`, body),
};

export function formatLength(seconds: number): string {
  const s = Math.round(seconds);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
