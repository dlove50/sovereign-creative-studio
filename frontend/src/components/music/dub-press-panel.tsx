"use client";

import { CheckCircle2, Disc3, Headphones, Loader2, Mic, Music4 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { assetUrl } from "@/lib/api/core";
import type { DubParams, DubVoices, Song } from "@/lib/api/music";

import { Fader, Panel, Segmented, Toggle } from "./dub-ui";

export type PressBusy = "audition-vocal" | "audition-version" | "press" | null;

type Props = {
  params: DubParams;
  patch: (p: Partial<DubParams>) => void;
  voices: DubVoices | null;
  songTitle: string;
  busy: PressBusy;
  message: { kind: "ok" | "error"; text: string } | null;
  auditionUrl: string | null;
  stemsAvailable: boolean;
  special: { song: Song | null; making: boolean; status: string; error: string | null };
  onMakeSpecial: () => void;
  onAudition: (side: "vocal" | "version") => void;
  onPress: () => void;
  onOpenLibrary: () => void;
};

const specialTemplate = (sound: string) => `${sound || "Your sound"}, this one is a dubplate special, for you only. Respect.`;

/** The voice special (spoken or sung), the sides to press and the two buttons: audition, then press. */
export function DubPressPanel(props: Props) {
  const { params, patch, voices, songTitle, busy, message, auditionUrl, stemsAvailable, special } = props;
  const voiceReady = voices?.ready ?? false;
  const sung = params.special_mode === "sung";
  const wantsVersion = params.sides !== "vocal";
  const working = busy !== null || special.making;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Voice special" hint="A voice drop naming the sound">
        <div className="space-y-3">
          <label className="block space-y-1.5 text-xs font-medium">
            Sound system or artist name
            <Input
              value={params.sound_name}
              maxLength={60}
              placeholder="e.g. Tin Roof Sound"
              onChange={(e) => {
                const name = e.target.value;
                const untouched = params.special_text === "" || params.special_text === specialTemplate(params.sound_name);
                patch({ sound_name: name, ...(untouched && name ? { special_text: specialTemplate(name) } : {}) });
              }}
            />
          </label>
          <label className="block space-y-1.5 text-xs font-medium">
            {sung ? "What the singer sings" : "What the voice says"}
            <Textarea
              value={params.special_text}
              maxLength={200}
              rows={3}
              placeholder="Dubplate special, for the sound that never sleeps."
              onChange={(e) => patch({ special_text: e.target.value })}
            />
          </label>
          <div className="space-y-1.5">
            <span className="text-xs font-medium">Where it plays</span>
            <Segmented
              label="Voice drop placement"
              value={params.special_placement}
              onChange={(v) => patch({ special_placement: v })}
              options={[
                { id: "none", label: "None" },
                { id: "intro", label: "Intro" },
                { id: "outro", label: "Outro" },
                { id: "both", label: "Both" },
              ]}
            />
          </div>
          {params.special_placement !== "none" ? (
            <>
              <div className="space-y-1.5">
                <span className="text-xs font-medium">Delivery</span>
                <Segmented
                  label="Special delivery"
                  value={params.special_mode}
                  onChange={(v) => patch({ special_mode: v })}
                  options={[
                    { id: "spoken", label: "Spoken (instant)" },
                    { id: "sung", label: "Sung by YuE2" },
                  ]}
                />
              </div>
              {sung ? (
                <div className="space-y-2 rounded-xl border border-border bg-background/40 p-3">
                  <Button size="sm" onClick={props.onMakeSpecial} disabled={working || !params.special_text.trim() || !stemsAvailable}>
                    {special.making ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Music4 className="mr-2 h-4 w-4" aria-hidden="true" />}
                    {special.song ? "Sing it again" : "Make the sung special"}
                  </Button>
                  {special.making ? <p className="text-xs text-muted-foreground">{special.status || "Working..."}</p> : null}
                  {!stemsAvailable ? <p className="text-xs text-destructive">The vocal splitter (Demucs) is not installed, so a sung special cannot be isolated.</p> : null}
                  {special.error ? <p className="text-xs text-destructive">{special.error}</p> : null}
                  {special.song ? (
                    <div className="space-y-1.5">
                      <p className="text-xs text-muted-foreground">
                        Made: {special.song.title}. The singer&apos;s voice is isolated and fitted to the riddim&apos;s tempo and key when you audition or press.
                      </p>
                      <audio src={assetUrl(special.song.audio_url) ?? special.song.audio_url} controls className="h-9 w-full" />
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">YuE2 sings your lines in this song&apos;s style (about 30 to 60 seconds the first time).</p>
                  )}
                </div>
              ) : voiceReady ? (
                <label className="block space-y-1.5 text-xs font-medium">
                  Voice
                  <select
                    value={params.special_voice ?? ""}
                    onChange={(e) => patch({ special_voice: e.target.value || null })}
                    className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm"
                  >
                    <option value="">Default voice</option>
                    {voices?.voices.map((v) => (
                      <option key={v.id} value={v.id}>{v.label}</option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className="rounded-lg bg-destructive/10 p-3 text-xs text-destructive">
                  No local voice is ready, so the spoken drop will not work. Use Sung by YuE2, set it to None, or fix Voice settings.
                </p>
              )}
              <Fader label="Voice level" value={params.special_volume} min={0.3} max={2} step={0.1} reset={1} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch({ special_volume: v })} />
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Mic className="h-3.5 w-3.5" aria-hidden="true" /> The music dips under the voice, then comes back.
              </p>
            </>
          ) : null}
        </div>
      </Panel>

      <Panel title="Press the dub plate" hint="Audition first, then save it to your library">
        <div className="space-y-4">
          <label className="block space-y-1.5 text-xs font-medium">
            Title
            <Input
              value={params.title}
              maxLength={80}
              placeholder={params.sound_name ? `${songTitle} (Dubplate for ${params.sound_name})` : `${songTitle} (Dubplate)`}
              onChange={(e) => patch({ title: e.target.value })}
            />
          </label>
          <div className="space-y-1.5">
            <span className="text-xs font-medium">Sides to press</span>
            <Segmented
              label="Sides to press"
              value={params.sides}
              onChange={(v) => patch({ sides: v })}
              options={[
                { id: "vocal", label: "Vocal cut" },
                { id: "version", label: "Version only" },
                { id: "both", label: "Both sides" },
              ]}
            />
            {wantsVersion ? (
              <p className="text-xs text-muted-foreground">The version is the same cut with the vocal taken out: the riddim with your mixer, FX and drop-outs. The first time, the song is split into vocal and instrumental (about 20 seconds).</p>
            ) : null}
          </div>
          <Toggle on={params.master} onChange={(v) => patch({ master: v })}>Loud sound-system master (-10 LUFS, limiter)</Toggle>
          <div className="flex flex-wrap gap-2">
            {params.sides !== "version" ? (
              <Button variant="outline" onClick={() => props.onAudition("vocal")} disabled={working}>
                {busy === "audition-vocal" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Headphones className="mr-2 h-4 w-4" aria-hidden="true" />}
                Audition {wantsVersion ? "vocal side" : "the cut"}
              </Button>
            ) : null}
            {wantsVersion ? (
              <Button variant="outline" onClick={() => props.onAudition("version")} disabled={working}>
                {busy === "audition-version" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Headphones className="mr-2 h-4 w-4" aria-hidden="true" />}
                Audition version side
              </Button>
            ) : null}
            <Button onClick={props.onPress} disabled={working}>
              {busy === "press" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Disc3 className="mr-2 h-4 w-4" aria-hidden="true" />}
              Press dub plate
            </Button>
          </div>
          {auditionUrl ? <audio key={auditionUrl} src={auditionUrl} controls autoPlay className="w-full" /> : null}
          {message ? (
            <div
              role="status"
              className={
                message.kind === "ok"
                  ? "flex items-start gap-2 rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-300"
                  : "rounded-lg bg-destructive/10 p-3 text-sm text-destructive"
              }
            >
              {message.kind === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> : null}
              <span>
                {message.text}
                {message.kind === "ok" ? (
                  <button type="button" onClick={props.onOpenLibrary} className="ml-2 underline underline-offset-2">Open library</button>
                ) : null}
              </span>
            </div>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}
