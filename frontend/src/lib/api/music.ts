import { request } from "./core";

export type MusicProviderId = "yue2" | "elevenlabs";

export type MusicProvider = {
  id: MusicProviderId;
  label: string;
  available: boolean;
  detail: string;
};

export type MusicEngine = {
  online: boolean;
  ready: boolean;
  checkpoint: string;
  checkpoint_present: boolean;
  nodes_present: boolean;
  vram_free_gb: number | null;
  detail: string;
};

export type MusicStatus = {
  default_provider: MusicProviderId;
  providers: MusicProvider[];
  engine: MusicEngine;
  limits: {
    min_seconds: number;
    max_seconds: number;
    max_lyrics_chars: number;
    max_style_chars: number;
    qualities: string[];
    typical_minutes_per_song_minute?: number;
    slow_minutes_per_song_minute?: number;
  };
};

export type Song = {
  id: string;
  title: string;
  style: string;
  lyrics: string;
  instrumental: boolean;
  duration_requested: number;
  seed: number;
  quality: string;
  provider: string;
  favorite: boolean;
  size_bytes: number;
  generation_seconds: number;
  created_at: string;
  audio_url: string;
};

export type MusicJob = {
  id: string;
  status: "queued" | "running" | "done" | "error";
  stage: "queued" | "writing_lyrics" | "starting_engine" | "generating" | "saving" | "done" | "error";
  message: string;
  title: string;
  song_id: string | null;
  error: string | null;
  song?: Song;
};

export type NowPlaying = {
  playing: boolean;
  paused: boolean;
  song: Song | null;
  position: number;
  duration: number;
};

export type VizData = {
  fps: number;
  bands: number;
  frames: number;
  duration: number;
  data: string;
};

export type CustomSongInput = {
  title?: string;
  style: string;
  lyrics?: string;
  instrumental: boolean;
  duration: number;
  seed?: number;
  quality: string;
  auto_play: boolean;
};

export type IdeaSongInput = {
  idea: string;
  genre?: string;
  instrumental: boolean;
  duration: number;
  quality: string;
  auto_play: boolean;
};

export type DubCue = { slot: number; time: number; label: string };
export type DubLoop = { start: number; end: number; label: string };
export type DubState = { cues: DubCue[]; loops: DubLoop[]; bpm: number; beat_offset: number };
export type DubInfo = {
  duration: number;
  points: number;
  peaks: string;
  bpm: number;
  beat_offset: number;
  confidence: number;
  state: DubState;
  has_stems: boolean;
  stems_available: boolean;
};
export type DubDrop = { at: number; beats: number };
export type DubParams = {
  start: number;
  end: number | null;
  tempo_pct: number;
  pitch: number;
  eq_low: number;
  eq_mid: number;
  eq_high: number;
  filter_mode: "off" | "lowpass" | "highpass";
  filter_hz: number;
  echo: boolean;
  echo_division: "1/8" | "1/4" | "3/8" | "1/2" | "1";
  echo_feedback: number;
  echo_mix: number;
  reverb: number;
  drops: DubDrop[];
  fade_in: number;
  fade_out: number;
  master: boolean;
  special_text: string;
  special_placement: "none" | "intro" | "outro" | "both";
  special_voice: string | null;
  special_mode: "spoken" | "sung";
  special_song_id: string | null;
  sides: "vocal" | "version" | "both";
  special_volume: number;
  sound_name: string;
  title: string;
};
export type DubVoices = { ready: boolean; voices: { id: string; label: string; is_default: boolean }[] };

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const musicApi = {
  status: () => request<MusicStatus>("/api/music/status"),
  startEngine: () => post<{ started: boolean; detail: string }>("/api/music/engine/start"),
  generate: (input: CustomSongInput) => post<MusicJob>("/api/music/generate", input),
  createFromIdea: (input: IdeaSongInput) => post<MusicJob>("/api/music/create", input),
  lyricsChat: (input: LyricsChatInput) => post<LyricsChatOutput>("/api/music/lyrics-chat", input),
  job: (id: string) => request<MusicJob>(`/api/music/jobs/${id}`),
  songs: () => request<Song[]>("/api/music/songs"),
  patchSong: (id: string, body: { title?: string; favorite?: boolean }) =>
    request<Song>(`/api/music/songs/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteSong: (id: string) => request<void>(`/api/music/songs/${id}`, { method: "DELETE" }),
  play: (id: string) => post<NowPlaying>(`/api/music/play/${id}`),
  pause: () => post<NowPlaying>("/api/music/pause"),
  resume: () => post<NowPlaying>("/api/music/resume"),
  seek: (position: number) => post<NowPlaying>("/api/music/seek", { position }),
  stop: () => post<{ stopped: boolean }>("/api/music/stop"),
  nowPlaying: () => request<NowPlaying>("/api/music/now-playing"),
  dub: (id: string) => request<DubInfo>(`/api/music/songs/${id}/dub`),
  saveDubState: (id: string, state: DubState) =>
    request<DubState>(`/api/music/songs/${id}/dub/state`, { method: "PUT", body: JSON.stringify(state) }),
  dubPreview: (id: string, params: DubParams, side: "vocal" | "version" = "vocal") =>
    post<{ audio_url: string }>(`/api/music/songs/${id}/dub/preview?side=${side}`, params),
  dubRender: (id: string, params: DubParams) => post<{ songs: Song[] }>(`/api/music/songs/${id}/dub/render`, params),
  dubSpecial: (id: string, body: { text: string; sound_name: string }) => post<MusicJob>(`/api/music/songs/${id}/dub/special`, body),
  splitStems: (id: string) => post<{ has_stems: boolean }>(`/api/music/songs/${id}/stems`),
  dubVoices: () => request<DubVoices>("/api/music/dub/voices"),
  viz: (id: string) => request<VizData>(`/api/music/songs/${id}/viz`),
};

/** Decode the base64 band-energy table (frames x bands, one byte each). */
export function decodeViz(viz: VizData): Uint8Array {
  const bin = atob(viz.data);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export type LyricsChatInput = {
  messages: { role: "user" | "assistant"; content: string }[];
  current?: { title: string; style: string; lyrics: string };
  duration?: number;
};
export type LyricsChatOutput = { reply: string; title: string; style: string; lyrics: string };
