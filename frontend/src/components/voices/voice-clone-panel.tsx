"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square, Upload } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// A varied script so the clone hears questions, statements and different energy.
const SCRIPT = [
  "Hi, thanks for taking a moment to watch this. I want to walk you through what we have been working on.",
  "First, the basics: what it does, who it helps, and why it matters. Does that sound fair? I think it does.",
  "Now for the exciting part. This is where everything comes together, and I am genuinely proud of it.",
  "Of course, it was not easy. There were late nights, a few wrong turns, and one or two things I would do differently.",
  "So take your time, ask questions, and let me know what you think. I would love to hear from you. Thank you.",
];
const MIN_RECORD_SECONDS = 20;

type Mode = "upload" | "record";

export function VoiceClonePanel({ onCreated, onClose }: { onCreated: (voiceId: string) => void; onClose: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [mode, setMode] = useState<Mode>("upload");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!recording) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [recording]);
  useEffect(() => () => recorder.current?.stream.getTracks().forEach((t) => t.stop()), []);

  async function start() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunks.current = [];
      rec.ondataavailable = (e) => chunks.current.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setFile(new File(chunks.current, "recording.webm", { type: "audio/webm" }));
      };
      rec.start();
      recorder.current = rec;
      setFile(null);
      setSeconds(0);
      setRecording(true);
    } catch {
      setError("The microphone could not be opened. Allow microphone access for this site and try again.");
    }
  }

  function stop() {
    recorder.current?.stop();
    setRecording(false);
  }

  async function run() {
    if (!file || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("name", name.trim());
      form.append("file", file);
      onCreated((await api.cloneVoice(form)).voice_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The voice could not be cloned.");
      setBusy(false);
    }
  }

  const tab = (m: Mode) => cn("flex-1 rounded-full px-4 py-2 text-sm font-medium", mode === m ? "bg-background text-foreground shadow" : "text-muted-foreground");
  const tooShort = mode === "record" && !!file && seconds < MIN_RECORD_SECONDS;
  return (
    <div className="rounded-2xl border border-border bg-card/60 p-4">
      <p className="text-sm font-semibold">Create a voice clone</p>
      <div role="tablist" className="mt-3 flex rounded-full bg-raised p-1">
        <button type="button" role="tab" aria-selected={mode === "upload"} onClick={() => setMode("upload")} className={tab("upload")}>Upload audio</button>
        <button type="button" role="tab" aria-selected={mode === "record"} onClick={() => setMode("record")} className={tab("record")}>Record audio</button>
      </div>
      <input value={name} onChange={(e) => setName(e.target.value.slice(0, 40))} placeholder="Voice name" aria-label="Voice name" className="mt-3 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm" />
      {mode === "upload" ? (
        <>
          <p className="mt-3 text-xs text-muted-foreground">Use a clean recording of one person, 30 to 60 seconds, in a quiet room. Audio or video both work.</p>
          <button type="button" onClick={() => input.current?.click()} className="mt-2 inline-flex h-10 items-center gap-2 rounded-xl border border-border px-4 text-sm hover:bg-raised">
            <Upload className="h-4 w-4" /> {file ? file.name.slice(0, 32) : "Choose a file"}
          </button>
          <input ref={input} type="file" accept="audio/*,video/*,.m4a,.mkv" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
        </>
      ) : (
        <div className="mt-3">
          <p className="text-xs text-muted-foreground">Read this out loud in your natural voice, about {MIN_RECORD_SECONDS} seconds or more. Vary your tone as you read.</p>
          <blockquote className="mt-2 space-y-2 rounded-xl bg-background/60 p-3 text-sm leading-relaxed">
            {SCRIPT.map((line) => <p key={line}>{line}</p>)}
          </blockquote>
          <div className="mt-3 flex items-center gap-3">
            {recording ? (
              <button type="button" onClick={stop} className="inline-flex h-10 items-center gap-2 rounded-full bg-destructive px-5 text-sm font-semibold text-white"><Square className="h-4 w-4" /> Stop</button>
            ) : (
              <button type="button" onClick={start} className="inline-flex h-10 items-center gap-2 rounded-full border border-border px-5 text-sm font-semibold hover:bg-raised"><Mic className="h-4 w-4" /> {file ? "Record again" : "Start recording"}</button>
            )}
            <span className="text-sm tabular-nums text-muted-foreground" role="timer">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span>
          </div>
          {tooShort ? <p className="mt-2 text-xs text-destructive">That was only {seconds} seconds. Record at least {MIN_RECORD_SECONDS} for a good clone.</p> : null}
        </div>
      )}
      <label className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5" />
        This is my own voice, or the person has agreed to it being cloned.
      </label>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={onClose} className="rounded-full px-4 py-2 text-sm text-muted-foreground hover:text-foreground">Cancel</button>
        <button type="button" disabled={busy || recording || !file || tooShort || !name.trim() || !consent} onClick={run} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />} {busy ? "Cloning…" : "Clone voice"}
        </button>
      </div>
    </div>
  );
}
