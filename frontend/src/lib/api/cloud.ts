import { API_BASE, formRequest, getActiveUserId, request } from "./core";
import type { IntegrationProvider } from "../types";

export type CloudOperation = "avatar-video" | "tts" | "sound-effects" | "voice-changer" | "transcribe" | "dubbing" | "isolate" | "music" | "align" | "voice-clone" | "sts";
export type MockJob = {
  id: string; operation: CloudOperation; title: string; status: "processing" | "completed" | "failed";
  progress: number; files: string[]; error?: string; created_at: string;
};

let _mockTimers = new Map<string, number>();

const MOCK_DURATION_MS: Record<CloudOperation, number> = {
  "avatar-video": 10_000, tts: 4_000, "sound-effects": 3_000,
  "voice-changer": 5_000, transcribe: 6_000, dubbing: 8_000,
  isolate: 4_000, music: 6_000, align: 5_000,
  "voice-clone": 7_000, sts: 12_000,
};

function outputFilesFor(operation: CloudOperation): string[] {
  const m: Record<string, string[]> = {
    "tts": ["output.mp3"], "voice-changer": ["output.mp3"],
    "sound-effects": ["output.mp3"], "music": ["output.mp3"],
    "avatar-video": ["output.mp4"], "transcribe": ["timing.json", "transcript.txt"],
    "dubbing": ["dubbed.mp4", "audio-only.mp3"], "align": ["timing.json"],
    "voice-clone": ["cloned.wav", "cloned.mp3"], "sts": ["output.mp4"],
  };
  return m[operation] || ["output.txt"];
}

/** Simulated cloud studio for development — zero API calls, zero credits. Defaults enabled. */
export const mockApi = { enabled: true };

export function startSimulatedJob(operation: CloudOperation, title = ""): MockJob {
  const now = Date.now();
  const duration = MOCK_DURATION_MS[operation] || 5_000;
  const job: MockJob = {
    id: crypto.randomUUID(), operation,
    title: title || `${operation} (simulated)`,
    status: "processing", progress: 0, files: [], created_at: new Date().toISOString(),
  };

  // Clear any previous mock session
  for (const id of _mockTimers.values()) clearInterval(id);
  _mockTimers.clear();

  const tickMs = 200;
  let tick = 0;
  const progressTimer = setInterval(() => {
    tick++;
    job.progress = Math.min(Math.round((tick * tickMs / duration) * 100), 99);
    if (job.progress >= 95 && !_mockTimers.size) finishMock(job);
  }, tickMs);
  _mockTimers.set(job.id, progressTimer as unknown as number);

  // Completion timer
  const doneTimer = setTimeout(() => { finishMock(job); }, duration);
  _mockTimers.set(`${job.id}:done`, doneTimer as unknown as number);

  return job;
}

function finishMock(job: MockJob) {
  for (const key of [..._mockTimers.keys()]) {
    if (key.startsWith(job.id)) {
      clearInterval(_mockTimers.get(key) as unknown as number);
      clearTimeout(_mockTimers.get(key) as unknown as number);
      _mockTimers.delete(key);
    }
  }
  job.status = "completed"; job.progress = 100; job.files = outputFilesFor(job.operation);
}

export function mockOutputFiles(operation: CloudOperation): string[] {
  return outputFilesFor(operation);
}
export type CloudJob = {
  id: string; provider: string; operation: CloudOperation | "imported-audio"; title: string;
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
    if (mockApi.enabled && !file) {
      // Mock mode: simulate avatar-video and tts as real operations.
      // Video-heavy modes (voice-clone, sts) need file input, so they bypass mock when a file is present.
      const job = startSimulatedJob((payload.operation as CloudOperation) ?? "tts", (payload.title as string) ?? "");
      return Promise.resolve({ ...job, provider: "mock", remote_id: null } as CloudJob);
    }
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
