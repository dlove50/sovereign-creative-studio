import { API_BASE, formRequest, getActiveUserId, request } from "./core";
import type { IntegrationProvider } from "../types";

export type CloudOperation = "avatar-video" | "tts" | "sound-effects" | "voice-changer" | "transcribe" | "dubbing" | "isolate";
export type CloudJob = {
  id: string; provider: string; operation: CloudOperation; title: string;
  status: "queued" | "submitting" | "processing" | "completed" | "failed";
  created_at: string; remote_id: string | null; files: string[]; error: string | null;
};
export type CatalogItem = {
  id: string; name: string; image_url: string | null; audio_url: string | null;
  default_voice_id: string | null; engines: string[]; tags: string[]; category: string | null;
};
export type CatalogPage = { items: CatalogItem[]; next_token: string | null };
export type CloudStatus = { providers: IntegrationProvider[]; output_directory: string; max_upload_mb: number };
export const cloudApi = {
  status: () => request<CloudStatus>("/api/cloud/status"),
  jobs: () => request<CloudJob[]>("/api/cloud/jobs"),
  catalog: (provider: string, kind: "voices" | "avatars", token = "", ownership = "public", search = "") =>
    request<CatalogPage>(`/api/cloud/${provider}/catalog/${kind}?${new URLSearchParams({ token, ownership, search })}`),
  submit: (payload: Record<string, unknown>, file?: File) => {
    if (file) {
      const form = new FormData();
      form.set("payload", JSON.stringify(payload)); form.set("file", file);
      return formRequest<CloudJob>("/api/cloud/upload-jobs", form);
    }
    return request<CloudJob>("/api/cloud/jobs", { method: "POST", body: JSON.stringify(payload) });
  },
  refresh: (id: string) => request<CloudJob>(`/api/cloud/jobs/${id}/refresh`, { method: "POST" }),
  file: async (job: CloudJob, name: string): Promise<Blob> => {
    const userId = getActiveUserId();
    const response = await fetch(`${API_BASE}/api/cloud/jobs/${job.id}/files/${encodeURIComponent(name)}`, {
      credentials: "include", headers: userId ? { "X-SCS-Family-User-Id": userId } : {},
    });
    if (!response.ok) throw new Error("Could not download this output. Check your session and try again.");
    return response.blob();
  },
  download: async (job: CloudJob, name: string) => {
    const url = URL.createObjectURL(await cloudApi.file(job, name));
    const link = document.createElement("a"); link.href = url; link.download = `${job.operation}-${job.id.slice(0, 8)}-${name}`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};
