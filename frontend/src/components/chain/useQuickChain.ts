"use client";

// Quick Chain state machine (Phase 2.2). Guided flow:
// Image -> Video -> (optional) Upscale -> (optional) Audio/Voice (with selection + preview)
// -> Transcribe -> Download

import { useState, useEffect } from "react";

import { api } from "@/lib/api";
import type { AudioMergeOut, AudioPreviewOut, Generation, TranscriptionJob, VideoGeneration } from "@/lib/types";

export type ChainStep = "image" | "video" | "upscale" | "audio" | "transcribe" | "download";

export const CHAIN_STEPS: { id: ChainStep; label: string; optional?: boolean }[] = [
  { id: "image", label: "Image" },
  { id: "video", label: "Video" },
  { id: "upscale", label: "Upscale", optional: true },
  { id: "audio", label: "Voice", optional: true },
  { id: "transcribe", label: "Transcribe" },
  { id: "download", label: "Download" },
];

export interface ChainState {
  current: ChainStep;
  completed: ChainStep[];
  skipped: ChainStep[];
  running: ChainStep | null;
  runningPreview: boolean;
  error: string | null;
  image: Generation | null;
  video: VideoGeneration | null;
  upscaled: VideoGeneration | null;
  audioVideo: AudioMergeOut | null;
  audioPreview: AudioPreviewOut | null;
  selectedVoiceId: string | null;
  transcript: TranscriptionJob | null;
  projectId: string | null;
}

const QUICK_CHAIN_PROJECT = "Quick Chain";
const CHAIN_SESSION_KEY = "scs_quick_chain";

const INITIAL: ChainState = {
  current: "image",
  completed: [],
  skipped: [],
  running: null,
  runningPreview: false,
  error: null,
  image: null,
  video: null,
  upscaled: null,
  audioVideo: null,
  audioPreview: null,
  selectedVoiceId: null,
  transcript: null,
  projectId: null,
};

function loadSavedState(): ChainState {
  if (typeof window === "undefined") return INITIAL;
  try {
    const raw = sessionStorage.getItem(CHAIN_SESSION_KEY);
    // A step that was running when the page closed is gone with it: never restore "running", or every control stays disabled.
    if (raw) return { ...INITIAL, ...JSON.parse(raw), running: null, runningPreview: false } as ChainState;
  } catch { /* quota exceeded or JSON parse error */ }
  return INITIAL;
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

async function poll<T extends { status: string }>(
  fetchOne: () => Promise<T>,
  { tries = 260, interval = 2500 }: { tries?: number; interval?: number } = {},
): Promise<T> {
  let last = await fetchOne();
  for (let i = 0; i < tries; i++) {
    if (last.status === "completed" || last.status === "failed") return last;
    await sleep(interval);
    last = await fetchOne();
  }
  return last;
}

function errText(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

export function useQuickChain() {
  const [state, setState] = useState<ChainState>(loadSavedState);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      sessionStorage.setItem(CHAIN_SESSION_KEY, JSON.stringify(state));
    } catch { /* quota exceeded */ }
  }, [state]);

  function patch(p: Partial<ChainState>) {
    setState((s) => ({ ...s, ...p }));
  }

  function advance(from: ChainStep, to: ChainStep, extra: Partial<ChainState> = {}) {
    setState((s) => ({
      ...s,
      ...extra,
      running: null,
      error: null,
      completed: s.completed.includes(from) ? s.completed : [...s.completed, from],
      current: to,
    }));
  }

  async function ensureProject(): Promise<string> {
    if (state.projectId) return state.projectId;
    const existing = await api.listProjects().catch(() => []);
    const found = existing.find((p) => p.name === QUICK_CHAIN_PROJECT);
    const project = found ?? (await api.createProject(QUICK_CHAIN_PROJECT, "Quick Chain guided outputs"));
    setState((s) => ({ ...s, projectId: project.id }));
    return project.id;
  }

  async function generateImage(prompt: string, imageMode: string | null, qualityPreset?: string | null) {
    if (!prompt.trim() || state.running) return;
    patch({ running: "image", error: null });
    try {
      const created = await api.createGeneration({
        prompt: prompt.trim(),
        media_type: "image",
        provider: "local_comfyui",
        image_mode: qualityPreset ? null : (imageMode ?? null),
        quality_preset: qualityPreset ?? null,
      });
      const done = await poll(() => api.getGeneration(created.id));
      if (done.status !== "completed" || !done.file_url) {
        patch({ running: null, error: done.error || "Image generation failed." });
        return;
      }
      advance("image", "video", { image: done });
    } catch (e) {
      patch({ running: null, error: errText(e, "Image generation failed.") });
    }
  }

  async function generateVideo(prompt: string) {
    if (!state.image?.file_url || state.running) return;
    patch({ running: "video", error: null });
    try {
      const projectId = await ensureProject();
      const created = await api.createVideo({
        project_id: projectId,
        source_image_url: state.image.file_url,
        prompt: prompt.trim() || "",
        motion_preset: "subtle_breathing",
        duration_seconds: 3,
        mode: "image_to_video",
        provider: "local_ltx",
        quality_preset: "standard_local",
      });
      const done = await poll(() => api.getVideo(created.id));
      if (done.status !== "completed" || !done.result_url) {
        patch({ running: null, error: done.error || "Video generation failed." });
        return;
      }
      advance("video", "upscale", { video: done });
    } catch (e) {
      patch({ running: null, error: errText(e, "Video generation failed.") });
    }
  }

  async function runUpscale() {
    if (!state.video?.result_url || state.running) return;
    patch({ running: "upscale", error: null });
    try {
      const projectId = await ensureProject();
      const created = await api.createVideo({
        project_id: projectId,
        source_image_url: state.video.result_url,
        prompt: state.video.prompt || "upscale",
        motion_preset: state.video.motion_preset,
        duration_seconds: state.video.duration_seconds,
        mode: "video_upscale",
        provider: "local_ltx",
        quality_preset: "standard_local",
      });
      const done = await poll(() => api.getVideo(created.id));
      if (done.status !== "completed" || !done.result_url) {
        patch({ running: null, error: done.error || "Upscale failed." });
        return;
      }
      advance("upscale", "audio", { upscaled: done });
    } catch (e) {
      patch({ running: null, error: errText(e, "Upscale failed.") });
    }
  }

  function skipUpscale() {
    if (state.running) return;
    setState((s) => ({
      ...s,
      skipped: s.skipped.includes("upscale") ? s.skipped : [...s.skipped, "upscale"],
      current: "audio",
      error: null,
    }));
  }

  function selectVoice(voiceId: string) {
    patch({ selectedVoiceId: voiceId, audioPreview: null });
  }

  async function previewVoice(ttsText: string) {
    if (!ttsText.trim() || state.runningPreview) return;
    patch({ runningPreview: true, error: null, audioPreview: null });
    try {
      const result = await api.previewVoice({
        tts_text: ttsText.trim(),
        voice_id: state.selectedVoiceId,
      });
      patch({ runningPreview: false, audioPreview: result });
    } catch (e) {
      patch({ runningPreview: false, error: errText(e, "Voice preview failed.") });
    }
  }

  async function addAudio(ttsText: string) {
    const sourceUrl = (state.upscaled ?? state.video)?.result_url;
    if (!sourceUrl || !ttsText.trim() || state.running) return;
    patch({ running: "audio", error: null });
    try {
      const result = await api.createAudioMerge({
        source_video_url: sourceUrl,
        tts_text: ttsText.trim(),
        voice_id: state.selectedVoiceId,
      });
      if (result.status !== "completed" || !result.result_url) {
        patch({ running: null, error: "Audio merge failed." });
        return;
      }
      advance("audio", "transcribe", { audioVideo: result });
    } catch (e) {
      patch({ running: null, error: errText(e, "Audio merge failed.") });
    }
  }

  function skipAudio() {
    if (state.running) return;
    setState((s) => ({
      ...s,
      skipped: s.skipped.includes("audio") ? s.skipped : [...s.skipped, "audio"],
      current: "transcribe",
      error: null,
    }));
  }

  /** The video URL used for transcription: audio-merged > upscaled > original. */
  function transcriptionSource(): { result_url: string | null } | null {
    if (state.audioVideo) return state.audioVideo;
    return state.upscaled ?? state.video;
  }

  async function transcribe() {
    const src = transcriptionSource();
    if (!src?.result_url || state.running) return;
    patch({ running: "transcribe", error: null });
    try {
      const projectId = await ensureProject();
      const created = await api.createTranscription({
        project_id: projectId,
        source_video_url: src.result_url,
      });
      const done = await poll(() => api.getTranscription(created.id), { tries: 180 });
      if (done.status !== "completed") {
        patch({ running: null, transcript: done, error: done.error_message || "Transcription failed." });
        return;
      }
      advance("transcribe", "download", { transcript: done });
    } catch (e) {
      patch({ running: null, error: errText(e, "Transcription failed.") });
    }
  }

  async function summarize(summaryType: Parameters<typeof api.summarizeTranscription>[1]) {
    if (!state.transcript || state.running) return;
    patch({ running: "transcribe", error: null });
    try {
      const updated = await api.summarizeTranscription(state.transcript.id, summaryType);
      patch({ running: null, transcript: updated });
    } catch (e) {
      patch({ running: null, error: errText(e, "Summary failed.") });
    }
  }

  function skipTranscribe() {
    if (state.running) return;
    setState((s) => ({
      ...s,
      skipped: s.skipped.includes("transcribe") ? s.skipped : [...s.skipped, "transcribe"],
      current: "download",
      error: null,
    }));
  }

  function clearError() {
    patch({ error: null });
  }

  function reset() {
    try { sessionStorage.removeItem(CHAIN_SESSION_KEY); } catch { /* */ }
    setState(INITIAL);
  }

  function goTo(step: ChainStep) {
    const stepIdx = CHAIN_STEPS.findIndex((cs) => cs.id === step);
    const maxCompletedIdx =
      state.completed.length === 0
        ? -1
        : Math.max(...state.completed.map((s) => CHAIN_STEPS.findIndex((cs) => cs.id === s)));
    // Allow: any completed step, the current step, or the step immediately
    // following the highest completed step (so "Continue to Download" works
    // after navigating back to Transcribe for Summarize).
    if (state.completed.includes(step) || step === state.current || stepIdx <= maxCompletedIdx + 1) {
      patch({ current: step, error: null });
    }
  }

  return {
    state,
    generateImage,
    generateVideo,
    runUpscale,
    skipUpscale,
    selectVoice,
    previewVoice,
    addAudio,
    skipAudio,
    skipTranscribe,
    transcribe,
    summarize,
    transcriptionSource,
    clearError,
    reset,
    goTo,
  };
}
