"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Clapperboard,
  Download,
  ExternalLink,
  Loader2,
  Mic,
  RefreshCw,
  Volume2,
  Sparkles,
  Type,
  Wand2,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AudioMergeReadiness, ImagePresets } from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { CHAIN_STEPS, useQuickChain, type ChainStep } from "@/components/chain/useQuickChain";
import { VoiceInputButton } from "@/components/chain/VoiceInputButton";

/** Map known backend error patterns to plain-English user messages. */
function friendlyError(raw: string | null, step?: ChainStep): string | null {
  if (!raw) return null;
  if (/ollama|copy provider|connection attempts failed/i.test(raw))
    return "The summary engine (Ollama) is not running. Start Ollama and try again, or continue without a summary. Your transcript is saved.";
  if (/piper|voice.*not ready/i.test(raw))
    return "Voice generation failed. Check that Piper TTS is set up, then retry or skip this step.";
  if (/ffmpeg/i.test(raw))
    return "Audio tools are not available on this system. Install FFmpeg to enable voice narration.";
  if (step === "upscale" && /not ready|upscale|comfyui|comfy/i.test(raw))
    return "Video upscale failed. Make sure ComfyUI is running and the LTX upscale model is installed (see docs/MODEL_AND_DEPENDENCY_MANIFEST.md), or skip this step.";
  if (/comfyui|comfy.*not.*ready|generation.*failed/i.test(raw))
    return "Image or video generation failed. Make sure ComfyUI is running and try again.";
  if (/no audio|silent/i.test(raw))
    return "This video has no audio, so there is nothing to transcribe. Add a voice or skip transcription.";
  return raw;
}

function isSummarizeErr(raw: string | null): boolean {
  return !!raw && /ollama|copy provider|connection attempts/i.test(raw);
}

export function QuickChainView() {
  const chain = useQuickChain();
  const { state } = chain;
  const [imagePrompt, setImagePrompt] = useState("");
  const [videoPrompt, setVideoPrompt] = useState("");
  const [ttsText, setTtsText] = useState("");
  const [presets, setPresets] = useState<ImagePresets | null>(null);
  const [qualityPreset, setQualityPreset] = useState("flux1_krea");
  const [audioReadiness, setAudioReadiness] = useState<AudioMergeReadiness | null>(null);
  const voiceInitialized = useRef(false);

  useEffect(() => {
    if (!voiceInitialized.current && audioReadiness?.default_voice && state.selectedVoiceId === null) {
      chain.selectVoice(audioReadiness.default_voice);
      voiceInitialized.current = true;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioReadiness?.default_voice]);

  useEffect(() => {
    api
      .listImagePresets()
      .then((p) => {
        setPresets(p);
        const configuredDefault = p.quality_presets.find((qp) => qp.is_default && qp.ready);
        const firstReady = configuredDefault ?? p.quality_presets.find((qp) => qp.ready);
        if (firstReady) setQualityPreset(firstReady.id);
      })
      .catch(() => {});
    api.getAudioMergeReadiness().then(setAudioReadiness).catch(() => {});
  }, []);

  const CHAIN_PRESET_ORDER = ["flux1_krea", "krea2_turbo_fp8", "z_image_turbo", "flux2_klein", "flux1_dev", "sdxl", "illustrious_xl", "netayume_anime", "local_fast"];

  const progress =
    (state.completed.length + state.skipped.filter((s) => !state.completed.includes(s)).length) /
    CHAIN_STEPS.length;

  const displayError = friendlyError(state.error, state.current);
  const summarizeError = isSummarizeErr(state.error);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">Quick Chain</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Go from a text prompt to a finished video with voice and transcript — step by step.
        </p>
      </div>

      <StepIndicator state={state} onGoTo={chain.goTo} />
      <ProgressBar value={progress} />

      {/* Show global errors except Ollama summarize failures, which appear inline */}
      {state.error && !summarizeError ? (
        <div className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
          {displayError}
          <button
            type="button"
            className="ml-2 underline opacity-70 hover:opacity-100"
            onClick={chain.clearError}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {/* ── Step 1: Image ───────────────────────────────────────────────────── */}
      {state.current === "image" ? (
        <Panel title="Step 1 — Create Your Image" icon={Sparkles}>
          <p className="text-sm text-muted-foreground">
            Describe what you want to see. The AI will generate a still image from your description.
          </p>
          <Label htmlFor="chain-image-prompt">What should the image look like?</Label>
          <div className="flex items-start gap-2">
            <Textarea
              id="chain-image-prompt"
              value={imagePrompt}
              onChange={(e) => setImagePrompt(e.target.value)}
              placeholder="A golden retriever sitting in a sunny park, sharp detail, natural light"
              className="min-h-[90px] flex-1"
              disabled={state.running !== null}
            />
            <VoiceInputButton
              onTranscript={(t) => setImagePrompt((prev) => prev ? `${prev} ${t}` : t)}
              disabled={state.running !== null}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="chain-image-model">Image style / model</Label>
            <select
              id="chain-image-model"
              value={qualityPreset}
              onChange={(e) => setQualityPreset(e.target.value)}
              disabled={state.running !== null || !presets}
              className="flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
            >
              {presets
                ? CHAIN_PRESET_ORDER.flatMap((id) => {
                    const p = presets.quality_presets.find((qp) => qp.id === id);
                    return p ? [p] : [];
                  }).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                      {p.id === "flux1_krea" ? " — Recommended" : ""}
                      {!p.ready ? " (Setup required)" : ""}
                    </option>
                  ))
                : <option value="flux1_krea">Loading models…</option>
              }
            </select>
          </div>
          {state.image?.file_url ? (
            <Preview kind="image" url={state.image.file_url} label="Your generated image" />
          ) : null}
          <RunButton
            label={state.image ? "Regenerate Image" : "Generate Image"}
            runningLabel="Creating your image… this may take a moment."
            running={state.running === "image"}
            onClick={() => chain.generateImage(imagePrompt, null, qualityPreset)}
            disabled={!imagePrompt.trim()}
            icon={Sparkles}
          />
          {state.image ? (
            <ContinueButton label="Continue to Video" onClick={() => chain.goTo("video")} />
          ) : null}
        </Panel>
      ) : null}

      {/* ── Step 2: Video ───────────────────────────────────────────────────── */}
      {state.current === "video" ? (
        <Panel title="Step 2 — Animate Into a Video" icon={Clapperboard}>
          <p className="text-sm text-muted-foreground">
            Your image will be animated into a short video clip. Add optional motion directions to guide the movement.
          </p>
          {state.image?.file_url ? <Preview kind="image" url={state.image.file_url} label="Source image" /> : null}
          <Label htmlFor="chain-video-prompt">Motion description (optional)</Label>
          <div className="flex items-start gap-2">
            <Textarea
              id="chain-video-prompt"
              value={videoPrompt}
              onChange={(e) => setVideoPrompt(e.target.value)}
              placeholder="Subject blinks and smiles gently"
              className="min-h-[70px] flex-1"
              disabled={state.running !== null}
            />
            <VoiceInputButton
              onTranscript={(t) => setVideoPrompt((prev) => prev ? `${prev} ${t}` : t)}
              disabled={state.running !== null}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Tip: for people and characters, small movements look best — try &ldquo;subtle breathing, gentle blink,
            no camera movement&rdquo;. Big motions or camera moves can distort faces.
          </p>
          {state.video?.result_url ? <Preview kind="video" url={state.video.result_url} label="Your video clip" /> : null}
          <RunButton
            label={state.video ? "Regenerate Video" : "Generate Video"}
            runningLabel="Animating your video… this may take a minute."
            running={state.running === "video"}
            onClick={() => chain.generateVideo(videoPrompt)}
            icon={Clapperboard}
          />
          {state.video ? (
            <ContinueButton label="Continue to Upscale" onClick={() => chain.goTo("upscale")} />
          ) : null}
        </Panel>
      ) : null}

      {/* ── Step 3: Upscale ─────────────────────────────────────────────────── */}
      {state.current === "upscale" ? (
        <Panel title="Step 3 — Upscale Your Video (Optional)" icon={Wand2}>
          <p className="text-sm text-muted-foreground">
            Upscaling sharpens your video and improves its resolution. No creative prompt is needed — just click <strong>Upscale Video</strong> to begin. Skip if you are happy with the current quality.
          </p>
          {state.video?.result_url ? <Preview kind="video" url={state.video.result_url} label="Original video" /> : null}
          {state.upscaled?.result_url ? <Preview kind="video" url={state.upscaled.result_url} label="Upscaled video" /> : null}
          <div className="flex flex-wrap gap-2">
            <RunButton
              label={state.upscaled ? "Re-run Upscale" : "Upscale Video"}
              runningLabel="Upscaling your video… this may take a minute."
              running={state.running === "upscale"}
              onClick={chain.runUpscale}
              icon={Wand2}
            />
            <Button type="button" variant="outline" disabled={state.running !== null} onClick={chain.skipUpscale}>
              Skip Upscale
            </Button>
          </div>
          {state.upscaled ? (
            <ContinueButton label="Continue to Voice" onClick={() => chain.goTo("audio")} />
          ) : null}
        </Panel>
      ) : null}

      {/* ── Step 4: Voice ───────────────────────────────────────────────────── */}
      {state.current === "audio" ? (
        <Panel title="Step 4 — Add a Voice to Your Video (Optional)" icon={Mic}>
          <p className="text-sm text-muted-foreground">
            Type what you want spoken aloud, choose a voice, preview it, then add it to your video. Skip this step if you do not need narration.
          </p>
          {(state.upscaled ?? state.video)?.result_url ? (
            <Preview kind="video" url={(state.upscaled ?? state.video)!.result_url} label="Your video" />
          ) : null}
          {state.audioVideo?.result_url ? (
            <Preview kind="video" url={state.audioVideo.result_url} label="Video with voice added" />
          ) : null}

          {audioReadiness === null ? (
            <p className="text-xs text-muted-foreground">Checking audio capability…</p>
          ) : !audioReadiness.ffmpeg ? (
            <div className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
              Audio tools are not available on this system. Install FFmpeg to enable voice narration, or skip this step.
            </div>
          ) : !audioReadiness.piper ? (
            <div className="space-y-2">
              <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                <strong>Voice narration is not set up yet.</strong>{" "}
                {audioReadiness.piper_detail} You can still continue — skip this step.
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Voice selection */}
              <div className="space-y-1">
                <Label htmlFor="chain-voice-select">Choose a voice</Label>
                {audioReadiness.voices.length > 1 ? (
                  <select
                    id="chain-voice-select"
                    value={state.selectedVoiceId ?? audioReadiness.default_voice ?? ""}
                    onChange={(e) => chain.selectVoice(e.target.value)}
                    disabled={state.running !== null || state.runningPreview}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {audioReadiness.voices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.label}{v.is_default ? " (default)" : ""}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Voice:{" "}
                    <strong>
                      {(state.selectedVoiceId ?? audioReadiness.default_voice ?? "en_US-lessac-low")
                        .replace(/_/g, " ")
                        .replace(/-/g, " ")}
                    </strong>
                  </p>
                )}
              </div>

              {/* Narration text */}
              <div className="space-y-1">
                <Label htmlFor="chain-tts-text">What should be spoken aloud?</Label>
                <div className="flex items-start gap-2">
                  <Textarea
                    id="chain-tts-text"
                    value={ttsText}
                    onChange={(e) => setTtsText(e.target.value)}
                    placeholder="Describe what is happening in the video — for example: A golden retriever plays in the park on a sunny afternoon."
                    className="min-h-[80px] flex-1"
                    disabled={state.running !== null}
                  />
                  <VoiceInputButton
                    onTranscript={(t) => setTtsText((prev) => prev ? `${prev} ${t}` : t)}
                    disabled={state.running !== null}
                  />
                </div>
              </div>

              {/* Preview Voice */}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!ttsText.trim() || state.running !== null || state.runningPreview}
                  onClick={() => chain.previewVoice(ttsText)}
                  aria-label="Preview the selected voice reading your narration"
                >
                  {state.runningPreview ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Volume2 className="h-4 w-4" />
                  )}
                  {state.runningPreview ? "Generating preview…" : "Preview Voice"}
                </Button>
              </div>

              {/* Audio preview player */}
              {state.audioPreview?.audio_url ? (
                <div className="space-y-1">
                  <Label>Listen to the preview</Label>
                  {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                  <audio
                    controls
                    src={assetUrl(state.audioPreview.audio_url) ?? undefined}
                    className="w-full"
                    data-testid="voice-preview-player"
                    aria-label="Voice preview audio"
                  />
                  <p className="text-xs text-muted-foreground">
                    Happy with the voice? Click <strong>Add Voice</strong> below.
                  </p>
                </div>
              ) : null}

              <RunButton
                label={state.audioVideo ? "Re-add Voice" : "Add Voice"}
                runningLabel="Adding voice to your video… please wait."
                running={state.running === "audio"}
                onClick={() => chain.addAudio(ttsText)}
                disabled={!ttsText.trim()}
                icon={Mic}
              />
            </div>
          )}

          <Button type="button" variant="outline" disabled={state.running !== null} onClick={chain.skipAudio}>
            Skip Audio
          </Button>
          {state.audioVideo ? (
            <ContinueButton label="Continue to Transcribe" onClick={() => chain.goTo("transcribe")} />
          ) : null}
        </Panel>
      ) : null}

      {/* ── Step 5: Transcribe ──────────────────────────────────────────────── */}
      {state.current === "transcribe" ? (
        <Panel title="Step 5 — Transcribe Your Video" icon={Type}>
          <p className="text-sm text-muted-foreground">
            {state.audioVideo
              ? "Your video has voice narration — transcribing it creates a searchable text version of what was spoken."
              : state.skipped.includes("audio")
                ? "You skipped adding voice, so your video may not have audio to transcribe. You can try anyway, or skip this step."
                : "Create a text transcript of the audio in your video."}
          </p>
          {chain.transcriptionSource()?.result_url ? (
            <Preview
              kind="video"
              url={chain.transcriptionSource()!.result_url}
              label={state.audioVideo ? "Your video with voice" : "Your video"}
            />
          ) : null}

          {state.transcript?.transcript_text ? (
            <div className="space-y-3">
              <div className="space-y-1">
                <Label>Transcript</Label>
                <Textarea readOnly value={state.transcript.transcript_text} className="min-h-[120px]" />
              </div>
              {state.transcript.summary_text ? (
                <div className="space-y-1">
                  <Label>Summary</Label>
                  <Textarea readOnly value={state.transcript.summary_text} className="min-h-[80px]" />
                </div>
              ) : (
                <div className="space-y-2">
                  {summarizeError ? (
                    <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                      {displayError}
                      <button
                        type="button"
                        className="ml-2 underline opacity-70 hover:opacity-100"
                        onClick={chain.clearError}
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : null}
                  <div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={state.running !== null}
                      onClick={() => chain.summarize("short_summary")}
                    >
                      {state.running === "transcribe" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      {state.running === "transcribe" ? "Creating summary…" : "Create a Summary"}
                    </Button>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Get a short written summary of your transcript using local AI.
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <RunButton
              label={state.transcript ? "Re-run Transcription" : "Transcribe Video"}
              runningLabel="Transcribing your video… this may take a moment."
              running={state.running === "transcribe" && !state.transcript}
              onClick={chain.transcribe}
              icon={Type}
            />
            <Button type="button" variant="outline" disabled={state.running !== null} onClick={chain.skipTranscribe}>
              Skip Transcription
            </Button>
          </div>
          {state.transcript?.transcript_text ? (
            <ContinueButton label="Continue to Download" onClick={() => chain.goTo("download")} />
          ) : null}
        </Panel>
      ) : null}

      {/* ── Step 6: Download ────────────────────────────────────────────────── */}
      {state.current === "download" ? (
        <Panel title="Step 6 — Your Outputs Are Ready" icon={Download}>
          <div
            className="flex items-center gap-2 text-sm font-medium text-emerald-600 dark:text-emerald-400"
            data-testid="chain-complete"
          >
            <CheckCircle2 className="h-4 w-4" />
            Your creative chain is complete — download your files below.
          </div>
          <p className="text-sm text-muted-foreground">
            Every file is also saved to your{" "}
            <Link href="/assets-library" className="text-primary hover:underline">
              Asset Library
            </Link>{" "}
            for future reference.
          </p>

          <div className="space-y-2">
            <OutputRow label="Image" url={state.image?.file_url ?? null} filename="image.png" kind="image" />
            <OutputRow label="Original video" url={state.video?.result_url ?? null} filename="video.mp4" kind="video" />
            {state.upscaled ? (
              <OutputRow label="Upscaled video" url={state.upscaled.result_url} filename="video-upscaled.mp4" kind="video" />
            ) : null}
            {state.audioVideo ? (
              <OutputRow label="Video with voice" url={state.audioVideo.result_url} filename="video-with-voice.mp4" kind="video" />
            ) : null}
            {state.transcript?.transcript_text ? (
              <OutputRow
                label="Transcript"
                url={api.transcriptionDownloadUrl(state.transcript.id)}
                filename="transcript.txt"
                kind="text"
                absolute
              />
            ) : null}
            {state.transcript?.summary_text ? (
              <div className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm" data-testid="download-summary">
                <span className="font-medium">Summary</span>
                <span className="text-xs text-muted-foreground italic">
                  {state.transcript.summary_text.slice(0, 60)}
                  {state.transcript.summary_text.length > 60 ? "…" : ""}
                </span>
              </div>
            ) : null}
          </div>

          {state.transcript?.transcript_text ? (
            <div className="rounded-md border bg-muted/50 px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground">Transcript preview</p>
              <p
                data-testid="transcript-text"
                className="mt-1 whitespace-pre-wrap text-xs leading-relaxed"
              >
                {state.transcript.transcript_text}
              </p>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <DownloadAll chain={chain} />
            <Link
              href="/assets-library"
              data-testid="open-asset-library"
              className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
            >
              <ExternalLink className="h-4 w-4" /> Open Asset Library
            </Link>
          </div>

          <Button type="button" variant="ghost" size="sm" onClick={chain.reset}>
            <RefreshCw className="h-4 w-4" /> Start a new chain
          </Button>
        </Panel>
      ) : null}
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────

function StepIndicator({
  state,
  onGoTo,
}: {
  state: ReturnType<typeof useQuickChain>["state"];
  onGoTo: (s: ChainStep) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {CHAIN_STEPS.map((step, i) => {
        const done = state.completed.includes(step.id);
        const skipped = state.skipped.includes(step.id);
        const active = state.current === step.id;
        const maxDoneIdx =
          state.completed.length === 0
            ? -1
            : Math.max(...state.completed.map((s) => CHAIN_STEPS.findIndex((cs) => cs.id === s)));
        const clickable = done || active || i === maxDoneIdx + 1;
        return (
          <div key={step.id} className="flex items-center gap-2">
            <button
              type="button"
              data-testid={`step-pill-${step.id}`}
              disabled={!clickable}
              onClick={() => onGoTo(step.id)}
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                active
                  ? "border-primary bg-primary/15 text-primary"
                  : done
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : "border-border text-muted-foreground",
                clickable && !active && "hover:bg-muted",
              )}
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full border border-current text-[10px]">
                {done ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              {step.label}
              {step.optional ? <span className="opacity-70">(optional)</span> : null}
              {skipped ? <span className="opacity-70">· skipped</span> : null}
            </button>
            {i < CHAIN_STEPS.length - 1 ? <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" /> : null}
          </div>
        );
      })}
    </div>
  );
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div
        className="h-full rounded-full bg-primary transition-all"
        style={{ width: `${Math.round(Math.min(1, value) * 100)}%` }}
      />
    </div>
  );
}

function Panel({ title, icon: Icon, children }: { title: string; icon: typeof Sparkles; children: React.ReactNode }) {
  return (
    <div className="space-y-3 rounded-2xl border border-border bg-card p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <Icon className="h-4 w-4 text-primary" />
        {title}
      </h2>
      {children}
    </div>
  );
}

function Preview({ kind, url, label }: { kind: "image" | "video"; url: string | null; label?: string }) {
  const src = assetUrl(url);
  if (!src) return null;
  return (
    <div className="space-y-1">
      {label ? <p className="text-xs text-muted-foreground">{label}</p> : null}
      {kind === "image" ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={label ?? "preview"} className="max-h-72 w-full rounded-md border border-border object-contain" />
      ) : (
        <video src={src} controls playsInline className="max-h-72 w-full rounded-md border border-border bg-black object-contain" />
      )}
    </div>
  );
}

function RunButton({
  label,
  runningLabel = "Working…",
  running,
  onClick,
  disabled,
  icon: Icon,
}: {
  label: string;
  runningLabel?: string;
  running: boolean;
  onClick: () => void;
  disabled?: boolean;
  icon: typeof Sparkles;
}) {
  return (
    <Button
      type="button"
      onClick={onClick}
      disabled={running || disabled}
      className="gap-2"
      data-testid={running ? "running" : undefined}
    >
      {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
      {running ? runningLabel : label}
    </Button>
  );
}

function ContinueButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button type="button" variant="outline" onClick={onClick} className="gap-1">
      {label} <ArrowRight className="h-4 w-4" />
    </Button>
  );
}

function downloadUrl(url: string, filename: string, absolute = false) {
  const href = absolute ? url : assetUrl(url);
  if (!href) return;
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function OutputRow({
  label,
  url,
  filename,
  kind,
  absolute = false,
}: {
  label: string;
  url: string | null;
  filename: string;
  kind: "image" | "video" | "text";
  absolute?: boolean;
}) {
  if (!url) return null;
  return (
    <div className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
      <span className="font-medium">{label}</span>
      <button
        type="button"
        onClick={() => downloadUrl(url, filename, absolute)}
        className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium hover:bg-muted"
        aria-label={`Download ${label}`}
      >
        <Download className="h-3.5 w-3.5" /> Download
      </button>
    </div>
  );
}

function DownloadAll({ chain }: { chain: ReturnType<typeof useQuickChain> }) {
  const { state } = chain;
  function all() {
    const imageUrl = state.image?.file_url ?? null;
    const videoUrl = state.video?.result_url ?? null;
    const upscaledUrl = state.upscaled?.result_url ?? null;
    const audioVideoUrl = state.audioVideo?.result_url ?? null;
    const transcript = state.transcript;
    if (imageUrl) downloadUrl(imageUrl, "image.png");
    if (videoUrl) window.setTimeout(() => downloadUrl(videoUrl, "video.mp4"), 300);
    if (upscaledUrl) window.setTimeout(() => downloadUrl(upscaledUrl, "video-upscaled.mp4"), 600);
    if (audioVideoUrl) window.setTimeout(() => downloadUrl(audioVideoUrl, "video-with-voice.mp4"), 750);
    if (transcript?.transcript_text)
      window.setTimeout(() => downloadUrl(api.transcriptionDownloadUrl(transcript.id), "transcript.txt", true), 900);
  }
  return (
    <Button type="button" onClick={all} className="gap-2">
      <Download className="h-4 w-4" /> Download Outputs
    </Button>
  );
}
