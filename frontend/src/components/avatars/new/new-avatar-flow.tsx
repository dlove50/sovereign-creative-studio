"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles, Upload, UserRound, X } from "lucide-react";

import { api } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import { CloneStep } from "./clone-step";
import { DesignStep } from "./design-step";
import { VoiceStep } from "./voice-step";

type Step = "choose" | "design" | "clone" | "voice";

function ChoiceCard({ title, text, badge, children, onClick }: { title: string; text: string; badge?: string; children?: React.ReactNode; onClick?: () => void }) {
  const body = (
    <>
      <div className="relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-primary/25 via-raised to-background">
        {title.startsWith("Clone") ? <UserRound className="h-20 w-20 text-primary/70" aria-hidden /> : <Sparkles className="h-20 w-20 text-primary/70" aria-hidden />}
        {children ? <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/70 opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">{children}</div> : null}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <h2 className="text-lg font-bold">{title}</h2>
        {badge ? <span className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-semibold text-primary">{badge}</span> : null}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{text}</p>
    </>
  );
  const shell = "group block w-full rounded-3xl border border-border bg-card/50 p-3 text-left transition-colors hover:border-primary/60 focus-within:border-primary/60";
  return onClick ? <button type="button" onClick={onClick} className={shell}>{body}</button> : <div className={shell}>{body}</div>;
}

export function NewAvatarFlow() {
  const router = useRouter();
  const photoInput = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<Step>("choose");
  const [avatar, setAvatar] = useState<AvatarAsset | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const leave = () => router.push("/avatars");
  const finish = (a: AvatarAsset) => router.push(`/avatars/${a.id}`);
  const toVoice = (a: AvatarAsset, voiceNote: string | null = null) => { setAvatar(a); setNote(voiceNote); setStep("voice"); };

  async function uploadPhoto(file: File) {
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", file.name.replace(/\.[^.]+$/, ""));
      toVoice(await api.createPhotoAvatar(form));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The photo could not be uploaded.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1040px] px-4 pb-16">
      <div className="flex justify-end pt-2">
        <button type="button" onClick={leave} aria-label="Close" className="flex h-10 w-10 items-center justify-center rounded-full border border-border hover:bg-raised"><X className="h-5 w-5" /></button>
      </div>
      {step === "choose" ? (
        <div>
          <h1 className="text-center text-4xl font-extrabold tracking-[-0.03em]">Create a new avatar</h1>
          <p className="mx-auto mt-2 max-w-lg text-center text-sm text-muted-foreground">Create an identity that looks and sounds consistent in any outfit and setting.</p>
          {error ? <p className="mx-auto mt-4 max-w-lg rounded-xl bg-destructive/15 px-3 py-2 text-center text-sm text-destructive">{error}</p> : null}
          <div className="mt-8 grid gap-5 md:grid-cols-2">
            <ChoiceCard title="Clone a real person" badge="Photo and voice" text="Upload a video of someone talking. Their best still becomes the face and their speech becomes the voice." onClick={() => setStep("clone")} />
            <ChoiceCard title="Create a virtual character" text="Start with an image and bring it to life with a voice.">
              <button type="button" onClick={() => photoInput.current?.click()} disabled={uploading} className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload photo
              </button>
              <button type="button" onClick={() => setStep("design")} className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground">
                <Sparkles className="h-4 w-4" /> Design with AI
              </button>
            </ChoiceCard>
          </div>
          <input ref={photoInput} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void uploadPhoto(f); }} />
        </div>
      ) : (
        <div className="mx-auto max-w-[720px] rounded-3xl border border-border bg-card/60 p-6 sm:p-8">
          {step === "design" ? <DesignStep onCancel={() => setStep("choose")} onSaved={(a) => toVoice(a)} /> : null}
          {step === "clone" ? <CloneStep onCancel={() => setStep("choose")} onCloned={toVoice} /> : null}
          {step === "voice" && avatar ? (
            <>
              {note ? <p className="mb-4 rounded-xl bg-raised px-3 py-2 text-sm text-muted-foreground">{note}</p> : null}
              <VoiceStep avatar={avatar} onDone={finish} />
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
