import { formRequest, request, requestVoid } from "./core";

export type VoiceEngine = {
  installed: boolean;
  online: boolean;
  ready: boolean;
  loading: string | null;
  model: string | null;
  kind: "full" | "realtime" | null;
  generating: boolean;
  voices: number;
};

export type VoiceModel = { label: string; kind: "full" | "realtime" };
export type VoiceSample = { name: string; file: string; preset: boolean };
export type VoiceList = { voices: VoiceSample[]; realtime: string[] };
export type VoiceExample = { num_speakers: number; script: string };

export type VoiceClip = {
  id: string;
  kind: "podcast" | "realtime";
  script: string;
  duration_seconds: number;
  created_at: string;
  render_seconds?: number | null;
  model?: string;
  speakers?: string[];
  voice?: string;
  cfg_scale?: number;
  inference_steps?: number;
  steps?: number;
  seed?: number;
  audio_url: string;
};

export type VoiceJob = {
  id: string;
  kind: "podcast" | "realtime";
  status: "running" | "done" | "error" | "stopped";
  log: string;
  error: string | null;
  chunk_count: number;
  streamed_seconds: number;
  elapsed: number;
  has_audio: boolean;
  clip?: Omit<VoiceClip, "audio_url">;
};

export type GenerateInput = {
  script: string;
  num_speakers: number;
  speakers: string[];
  cfg_scale: number;
  inference_steps: number;
  seed: number;
  disable_voice_cloning: boolean;
};

export type Chunks = { sample_rate: number; next: number; chunks: string[]; status: string };

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const voiceStudioApi = {
  status: () => request<VoiceEngine>("/api/voice-studio/status"),
  start: (model?: string) => post<VoiceEngine & { started: boolean }>("/api/voice-studio/start", { model: model ?? null }),
  stop: () => post<{ stopped: boolean }>("/api/voice-studio/stop"),
  models: () => request<{ current: string | null; models: VoiceModel[] }>("/api/voice-studio/models"),
  switchModel: (label: string) => post<{ message: string; current: string; kind: "full" | "realtime" }>("/api/voice-studio/model", { label }),
  voices: () => request<VoiceList>("/api/voice-studio/voices"),
  voiceAudioUrl: (name: string) => `/api/voice-studio/voices/${encodeURIComponent(name)}/audio`,
  addVoice: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return formRequest<{ added: string; voices: string[] }>("/api/voice-studio/voices", form);
  },
  examples: () => request<{ examples: VoiceExample[] }>("/api/voice-studio/examples"),
  generate: (input: GenerateInput) => post<{ id: string }>("/api/voice-studio/generate", input),
  realtime: (input: { text: string; voice: string; cfg_scale: number; steps: number }) =>
    post<{ id: string }>("/api/voice-studio/realtime", input),
  job: (id: string) => request<VoiceJob>(`/api/voice-studio/jobs/${id}`),
  chunks: (id: string, after: number) => request<Chunks>(`/api/voice-studio/jobs/${id}/chunks?after=${after}`),
  stopJob: (id: string) => post<{ stopping: boolean }>(`/api/voice-studio/jobs/${id}/stop`),
  clips: () => request<VoiceClip[]>("/api/voice-studio/clips"),
  deleteClip: (id: string) => requestVoid(`/api/voice-studio/clips/${id}`, { method: "DELETE" }),
};
