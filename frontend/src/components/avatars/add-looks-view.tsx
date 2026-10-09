"use client";
import { SkeletonGrid } from "@/components/ui/skeleton";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Camera, Check, ImagePlus, Loader2, Square, Upload, Video, X } from "lucide-react";

import { api } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import { cn } from "@/lib/utils";

const MIN_RECORD_SECONDS = 15;
const VIDEO_TIPS = ["Speak expressively for at least 15 seconds", "Use natural expressions and gestures", "Pause between sentences", "Choose a quiet, well-lit space"];
const PHOTO_TIPS = ["Face the camera with your whole face visible", "Use even, soft light with no harsh shadows", "Keep the background simple", "One person only, at least 512 pixels wide"];
const isVideoFile = (f: File) => f.type.startsWith("video/") || /\.(mp4|mov|webm|mkv|m4v)$/i.test(f.name);

export function AddLooksView() {
  const router = useRouter();
  const params = useSearchParams();
  const avatarId = params.get("avatar");
  const input = useRef<HTMLInputElement>(null);
  const preview = useRef<HTMLVideoElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [avatar, setAvatar] = useState<AvatarAsset | null | undefined>(undefined);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [tips, setTips] = useState<"video" | "photo">("video");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [filePreview, setFilePreview] = useState<string | null>(null);

  useEffect(() => {
    if (!file) { setFilePreview(null); return; }
    const url = URL.createObjectURL(file);
    setFilePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFile(selected?: File) {
    if (!selected) return;
    if (!/\.(mp4|mov|webm|mkv|m4v|png|jpe?g|webp)$/i.test(selected.name)) {
      setError("Choose a PNG, JPG or WEBP photo, or an MP4, MOV or WEBM video.");
      return;
    }
    setError(null);
    setFile(selected);
    setTips(isVideoFile(selected) ? "video" : "photo");
    setSeconds(MIN_RECORD_SECONDS);
  }

  useEffect(() => {
    if (!avatarId) { setAvatar(null); return; }
    api.listAvatars().then((all) => setAvatar(all.find((a) => a.id === avatarId) ?? null)).catch(() => setAvatar(null));
  }, [avatarId]);
  useEffect(() => {
    if (!recording) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [recording]);
  useEffect(() => () => recorder.current?.stream.getTracks().forEach((t) => t.stop()), []);

  async function record() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      if (preview.current) { preview.current.srcObject = stream; void preview.current.play(); }
      const rec = new MediaRecorder(stream);
      chunks.current = [];
      rec.ondataavailable = (e) => chunks.current.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (preview.current) preview.current.srcObject = null;
        setFile(new File(chunks.current, "recording.webm", { type: "video/webm" }));
      };
      rec.start();
      recorder.current = rec;
      setFile(null);
      setSeconds(0);
      setRecording(true);
    } catch {
      setError("The camera could not be opened. Allow camera and microphone access for this site and try again.");
    }
  }

  function stopRecording() {
    recorder.current?.stop();
    setRecording(false);
  }

  async function create() {
    if (!file || !avatar) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("look_label", label.trim());
      if (isVideoFile(file)) {
        form.append("group_id", avatar.id);
        await api.createLookFromVideo(form);
      } else {
        form.append("group_id", avatar.id);
        form.append("name", label.trim() || file.name.replace(/\.[^.]+$/, ""));
        await api.createPhotoAvatar(form);
      }
      router.push(`/avatars/${avatar.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The look could not be created.");
      setBusy(false);
    }
  }

  if (avatar === undefined) return <SkeletonGrid count={3} className="grid grid-cols-1 gap-4 py-8 sm:grid-cols-3" />;
  if (!avatar) {
    return (
      <div className="py-16 text-center">
        <p className="font-semibold">Pick an avatar first.</p>
        <Link href="/avatars" className="mt-2 inline-block text-sm text-primary hover:underline">Back to avatars</Link>
      </div>
    );
  }
  const tooShort = recording === false && !!file && file.name === "recording.webm" && seconds < MIN_RECORD_SECONDS;
  const tipList = tips === "video" ? VIDEO_TIPS : PHOTO_TIPS;
  return (
    <div className="mx-auto max-w-[720px] px-4 pb-16">
      <div className="flex justify-end pt-2">
        <Link href={`/avatars/${avatar.id}`} aria-label="Close" className="flex h-10 w-10 items-center justify-center rounded-full border border-border hover:bg-raised"><X className="h-5 w-5" /></Link>
      </div>
      <h1 className="text-center text-3xl font-extrabold tracking-[-0.03em]">Add more looks for {avatar.name}</h1>

      <div onDragOver={(e) => { e.preventDefault(); if (!recording && !busy) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); if (!recording && !busy) selectFile(e.dataTransfer.files[0]); }}
        className={cn("mt-6 rounded-3xl border-2 border-dashed bg-card/40 p-6 text-center", dragging ? "border-primary" : "border-border")}>
        <video ref={preview} muted playsInline className={cn("mx-auto mb-4 max-h-[260px] rounded-2xl bg-black", recording ? "block" : "hidden")} />
        {recording ? (
          <div className="flex flex-col items-center gap-3">
            <p className="text-sm font-semibold" role="timer">Recording {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</p>
            <button type="button" onClick={stopRecording} className="inline-flex items-center gap-2 rounded-full bg-destructive px-5 py-2 text-sm font-semibold text-white"><Square className="h-4 w-4" /> Stop recording</button>
          </div>
        ) : (
          <>
            {filePreview && file ? (isVideoFile(file)
              ? <video src={filePreview} controls playsInline className="mx-auto mb-4 max-h-[260px] rounded-2xl" />
              : <img src={filePreview} alt="Selected avatar look" className="mx-auto mb-4 max-h-[260px] rounded-2xl object-contain" />) : null}
            <button type="button" disabled={busy} onClick={() => input.current?.click()} className="mx-auto flex flex-col items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              {file ? <Check className="h-7 w-7 text-primary" /> : <Upload className="h-7 w-7 text-muted-foreground" />}
              <span className="text-sm font-semibold">{file ? file.name : "Drag and drop or click to upload"}</span>
              <span className="text-xs text-muted-foreground">Video (MP4, MOV, WEBM) or photo (PNG, JPG, WEBP)</span>
            </button>
            <p className="my-3 text-xs text-muted-foreground">or</p>
            <button type="button" onClick={record} className="inline-flex items-center gap-2 rounded-full border border-border px-5 py-2 text-sm font-semibold hover:bg-raised"><Camera className="h-4 w-4" /> Record now</button>
          </>
        )}
        <input ref={input} type="file" accept="video/mp4,video/quicktime,video/webm,image/png,image/jpeg,image/webp,.mkv,.m4v" className="hidden" onChange={(e) => { selectFile(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">For files on your phone or Google Drive, download or transfer them to this device first, then upload them here.</p>

      <label className="mt-5 block text-sm font-semibold">
        Look name (optional)
        <input value={label} onChange={(e) => setLabel(e.target.value.slice(0, 60))} placeholder="e.g. Office, Studio" className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm font-normal" />
      </label>

      <div className="mt-5 rounded-2xl border border-border bg-card/50 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Tips for better uploads</h2>
          <div role="tablist" className="flex rounded-full bg-raised p-0.5 text-xs">
            <button type="button" role="tab" aria-selected={tips === "video"} onClick={() => setTips("video")} className={cn("flex items-center gap-1 rounded-full px-3 py-1", tips === "video" && "bg-background shadow")}><Video className="h-3.5 w-3.5" /> Video</button>
            <button type="button" role="tab" aria-selected={tips === "photo"} onClick={() => setTips("photo")} className={cn("flex items-center gap-1 rounded-full px-3 py-1", tips === "photo" && "bg-background shadow")}><ImagePlus className="h-3.5 w-3.5" /> Photo</button>
          </div>
        </div>
        <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
          {tipList.map((t) => <li key={t} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{t}</li>)}
        </ul>
        <p className="mt-3 text-xs text-muted-foreground">A video look uses its sharpest still, not your movement.</p>
      </div>

      {tooShort ? <p className="mt-3 text-sm text-destructive">That recording was {seconds} seconds. Record at least {MIN_RECORD_SECONDS}.</p> : null}
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <div className="mt-6 flex items-center justify-center gap-3">
        <Link href={`/avatars/${avatar.id}`} className="rounded-full px-6 py-3 text-sm font-semibold hover:bg-raised">Back</Link>
        <button type="button" disabled={!file || busy || recording || tooShort} onClick={create} className="inline-flex items-center gap-2 rounded-full bg-primary px-8 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Create look
        </button>
      </div>
    </div>
  );
}
