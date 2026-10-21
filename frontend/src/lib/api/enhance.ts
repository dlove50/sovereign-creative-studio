import { formRequest, request, requestVoid } from "./core";

export type MediaKind = "image" | "audio" | "video";

export type EnhanceParam = { id: string; label: string; min: number; max: number; default: number; step: number };

export type EnhanceOperation = {
  id: string;
  label: string;
  kinds: MediaKind[];
  engine: string;
  params: EnhanceParam[];
  available: boolean;
  unavailable_reason: string | null;
};

export type EnhanceOpInput = { op: string; params: Record<string, number> };

export type EnhanceJob = {
  id: string;
  kind: MediaKind;
  name: string;
  ops: EnhanceOpInput[];
  status: "queued" | "running" | "done" | "error" | "cancelled";
  progress: number;
  error: string | null;
  source_url: string;
  outputs: { label: string; kind: MediaKind; url: string }[];
  applied: { index: number; at: string } | null;
  created_at: string;
};

export type EnhancePreset = { id: string; name: string; kind: MediaKind; ops: EnhanceOpInput[] };

const base = "/api/enhance";
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const enhanceApi = {
  operations: () => request<{ operations: EnhanceOperation[] }>(`${base}/operations`),
  jobs: () => request<EnhanceJob[]>(`${base}/jobs`),
  job: (id: string) => request<EnhanceJob>(`${base}/jobs/${id}`),
  upload: (file: File, ops: EnhanceOpInput[]) => {
    const form = new FormData();
    form.append("file", file);
    form.append("ops", JSON.stringify(ops));
    form.append("name", file.name);
    return formRequest<EnhanceJob>(`${base}/jobs`, form);
  },
  fromLibrary: (url: string, ops: EnhanceOpInput[]) => request<EnhanceJob>(`${base}/jobs/from-library`, json("POST", { url, ops })),
  cancel: (id: string) => request<{ cancelling: boolean }>(`${base}/jobs/${id}/cancel`, { method: "POST" }),
  apply: (id: string, index: number) => request<EnhanceJob>(`${base}/jobs/${id}/apply`, json("POST", { index })),
  remove: (id: string) => requestVoid(`${base}/jobs/${id}`, { method: "DELETE" }),
  presets: () => request<EnhancePreset[]>(`${base}/presets`),
  savePreset: (name: string, kind: MediaKind, ops: EnhanceOpInput[]) =>
    request<EnhancePreset[]>(`${base}/presets`, json("POST", { name, kind, ops })),
  deletePreset: (id: string) => request<EnhancePreset[]>(`${base}/presets/${id}`, { method: "DELETE" }),
};

export function kindOfName(name: string): MediaKind | null {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  if (["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"].includes(ext)) return "image";
  if (["wav", "mp3", "flac", "m4a", "ogg", "aac", "opus"].includes(ext)) return "audio";
  if (["mp4", "mov", "mkv", "webm", "m4v"].includes(ext)) return "video";
  return null;
}
