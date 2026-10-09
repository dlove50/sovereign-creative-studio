"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Circle, Loader2, Monitor, Square } from "lucide-react";

import { api } from "@/lib/api";

const MAX_SECONDS = 30 * 60; // stops by itself; the upload limit is 512 MB

type Phase = "idle" | "recording" | "review" | "saving" | "saved";

function clock(seconds: number) {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function pickMimeType() {
  const options = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
  return options.find((type) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) ?? "";
}

export function ScreenRecorderView() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [useMic, setUseMic] = useState(true);
  const [title, setTitle] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ result_url: string; duration_seconds: number } | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const streams = useRef<MediaStream[]>([]);
  const chunks = useRef<Blob[]>([]);
  const blob = useRef<Blob | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioContext = useRef<AudioContext | null>(null);
  const supported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia && typeof MediaRecorder !== "undefined";

  function releaseCapture() {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
    streams.current.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    streams.current = [];
    audioContext.current?.close().catch(() => undefined);
    audioContext.current = null;
  }

  useEffect(() => () => { releaseCapture(); if (recorder.current?.state === "recording") recorder.current.stop(); }, []);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  async function start() {
    setError(null);
    setSaved(null);
    try {
      const screen = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 30 }, audio: true });
      streams.current = [screen];
      const tracks: MediaStreamTrack[] = [...screen.getVideoTracks()];
      let microphone: MediaStream | null = null;
      if (useMic) {
        try {
          microphone = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
          streams.current.push(microphone);
        } catch {
          setError("The microphone was not available, so this recording has no voice. You can record again after allowing it.");
        }
      }
      // Mix the shared tab's sound and the microphone into one audio track.
      const sources = [screen, microphone].filter((s): s is MediaStream => !!s && s.getAudioTracks().length > 0);
      if (sources.length) {
        const context = new AudioContext();
        audioContext.current = context;
        const destination = context.createMediaStreamDestination();
        sources.forEach((s) => context.createMediaStreamSource(s).connect(destination));
        tracks.push(...destination.stream.getAudioTracks());
      }
      const mimeType = pickMimeType();
      const media = new MediaRecorder(new MediaStream(tracks), mimeType ? { mimeType, videoBitsPerSecond: 4_000_000 } : undefined);
      chunks.current = [];
      media.ondataavailable = (e) => { if (e.data.size > 0) chunks.current.push(e.data); };
      media.onstop = () => {
        releaseCapture();
        const made = new Blob(chunks.current, { type: media.mimeType || "video/webm" });
        blob.current = made;
        setPreviewUrl(URL.createObjectURL(made));
        setPhase(made.size > 0 ? "review" : "idle");
        if (made.size === 0) setError("Nothing was recorded.");
      };
      // Stopping from the browser's own "Stop sharing" button ends the recording the same way.
      screen.getVideoTracks()[0].addEventListener("ended", () => { if (media.state === "recording") media.stop(); });
      recorder.current = media;
      media.start(1000);
      setSeconds(0);
      setPhase("recording");
      timer.current = setInterval(() => {
        setSeconds((s) => {
          if (s + 1 >= MAX_SECONDS && media.state === "recording") media.stop();
          return s + 1;
        });
      }, 1000);
    } catch (e) {
      releaseCapture();
      setPhase("idle");
      setError(e instanceof DOMException && e.name === "NotAllowedError"
        ? "Screen sharing was cancelled or blocked. Choose a screen, window or tab to record."
        : e instanceof Error ? e.message : "Recording could not start.");
    }
  }

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  function discard() {
    blob.current = null;
    setPreviewUrl(null);
    setSaved(null);
    setPhase("idle");
  }

  async function save() {
    if (!blob.current) return;
    setPhase("saving");
    setError(null);
    try {
      const form = new FormData();
      form.append("file", blob.current, "screen-recording.webm");
      form.append("title", title);
      const made = await api.saveScreenRecording(form);
      setSaved({ result_url: made.result_url, duration_seconds: made.duration_seconds });
      setPhase("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The recording could not be saved.");
      setPhase("review");
    }
  }

  return (
    <div className="mx-auto max-w-[760px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Screen recorder</h1>
      <p className="mx-auto mt-2 max-w-md text-center text-sm text-muted-foreground">
        Record your screen and your voice, then keep the clip in your library to use in videos and interactive lessons. Everything stays on this computer.
      </p>
      {!supported ? <p className="mt-6 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">This browser cannot record the screen. Use a recent Chrome, Edge or Firefox.</p> : null}
      {error ? <p role="alert" className="mt-4 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      {phase === "idle" || phase === "recording" ? (
        <section className="mt-6 rounded-3xl border border-border bg-card/60 p-6 text-center">
          {phase === "recording" ? (
            <>
              <p className="flex items-center justify-center gap-2 text-2xl font-semibold tabular-nums" role="timer" aria-live="off">
                <Circle className="h-4 w-4 animate-pulse fill-destructive text-destructive" aria-hidden /> {clock(seconds)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">Recording stops by itself at {MAX_SECONDS / 60} minutes.</p>
              <button type="button" onClick={stop} className="mt-5 inline-flex items-center gap-2 rounded-full bg-destructive px-6 py-2.5 text-sm font-semibold text-destructive-foreground">
                <Square className="h-4 w-4" /> Stop recording
              </button>
            </>
          ) : (
            <>
              <Monitor className="mx-auto h-9 w-9 text-muted-foreground" aria-hidden />
              <label className="mt-4 inline-flex items-center gap-2 text-sm">
                <input type="checkbox" checked={useMic} onChange={(e) => setUseMic(e.target.checked)} className="h-4 w-4" />
                Add my microphone
              </label>
              <div className="mt-4">
                <button type="button" disabled={!supported} onClick={start} className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                  <Circle className="h-4 w-4 fill-current" /> Start recording
                </button>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">Your browser will ask which screen, window or tab to share. Tick “share audio” to include its sound.</p>
            </>
          )}
        </section>
      ) : null}

      {phase === "review" || phase === "saving" || phase === "saved" ? (
        <section className="mt-6 space-y-3 rounded-3xl border border-border bg-card/60 p-4">
          {previewUrl ? <video src={previewUrl} controls className="w-full rounded-xl bg-black" aria-label="Your recording" /> : null}
          {phase !== "saved" ? (
            <>
              <label className="block text-sm font-medium">Title
                <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="Screen recording" className="mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm" />
              </label>
              <div className="flex flex-wrap justify-end gap-2">
                <button type="button" disabled={phase === "saving"} onClick={discard} className="rounded-full border border-border px-4 py-2 text-sm hover:bg-raised disabled:opacity-60">Discard</button>
                <button type="button" disabled={phase === "saving"} onClick={save} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60">
                  {phase === "saving" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {phase === "saving" ? "Saving…" : `Save to my library (${clock(seconds)})`}
                </button>
              </div>
            </>
          ) : (
            <div role="status" className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <span>Saved to your library{saved ? ` · ${saved.duration_seconds.toFixed(0)} seconds` : ""}.</span>
              <span className="flex gap-2">
                <Link href="/interactive" className="rounded-full border border-border px-4 py-2 hover:bg-raised">Use in an interactive lesson</Link>
                <button type="button" onClick={discard} className="rounded-full bg-primary px-4 py-2 font-semibold text-primary-foreground">Record another</button>
              </span>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
