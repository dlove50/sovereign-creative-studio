"use client";

import { useRef, useState } from "react";
import { Loader2, Upload, Video } from "lucide-react";

import { api } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";

export function CloneStep({ onCancel, onCloned }: { onCancel: () => void; onCloned: (avatar: AvatarAsset, note: string | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!file || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("name", name.trim());
      form.append("file", file);
      const made = await api.cloneRealPerson(form);
      onCloned(made.avatar, made.voice_note);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The person could not be cloned.");
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 className="text-3xl font-extrabold tracking-tight">Clone a real person</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Upload a video of one person talking to the camera. We pick the sharpest still as the avatar&apos;s face and clone the voice from the speech.
        Your movement and expressions are not copied: the avatar moves the way the talking-avatar model moves.
      </p>
      <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>30 to 60 seconds, face lit evenly and looking at the camera.</li>
        <li>A quiet room, no music, and natural speech in full sentences.</li>
      </ul>
      <label className="mt-5 block text-sm font-semibold">
        Name *
        <input value={name} onChange={(e) => setName(e.target.value.slice(0, 60))} className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm font-normal" />
      </label>
      <button type="button" onClick={() => input.current?.click()}
        className="mt-4 flex w-full flex-col items-center gap-2 rounded-3xl border-2 border-dashed border-border bg-card/40 py-9 hover:bg-card/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {file ? <Video className="h-7 w-7 text-primary" /> : <Upload className="h-7 w-7 text-muted-foreground" />}
        <span className="text-sm font-semibold">{file ? file.name : "Choose a video"}</span>
        <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1e6).toFixed(1)} MB · click to change` : "MP4, MOV, WEBM or MKV"}</span>
      </button>
      <input ref={input} type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mkv,.m4v" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
      <label className="mt-4 flex items-start gap-2 text-sm text-muted-foreground">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />
        This is me, or the person in the video has agreed to being cloned.
      </label>
      {error ? <p className="mt-4 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <div className="mt-6 flex justify-between border-t border-border pt-5">
        <button type="button" onClick={onCancel} className="rounded-full bg-raised px-6 py-3 text-sm font-semibold hover:bg-raised/70">Cancel</button>
        <button type="button" disabled={busy || !file || !name.trim() || !consent} onClick={run} className="inline-flex items-center gap-2 rounded-full bg-primary px-7 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} {busy ? "Cloning…" : "Create avatar"}
        </button>
      </div>
    </div>
  );
}
