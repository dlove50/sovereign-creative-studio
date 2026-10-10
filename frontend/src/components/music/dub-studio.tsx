"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Pause, Play, Repeat, Square, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { assetUrl } from "@/lib/api/core";
import { formatDuration, musicApi, type DubInfo, type DubLoop, type DubParams, type DubState, type DubVoices, type Song } from "@/lib/api/music";
import { cn } from "@/lib/utils";

import { DubFxPanel } from "./dub-fx-panel";
import { DubPressPanel, type PressBusy } from "./dub-press-panel";
import { Panel, Segmented } from "./dub-ui";
import { CUE_COLORS, DubWaveform } from "./dub-waveform";
import type { MusicPlayer } from "./use-music-player";

const AUTO_LOOP_BEATS = [0.5, 1, 2, 4, 8, 16];
const SAVE_DELAY_MS = 600;
const LOOP_CHECK_MS = 30;

type Zoom = "all" | "30" | "10";

const DEFAULT_PARAMS: DubParams = {
  start: 0, end: null, tempo_pct: 0, pitch: 0, eq_low: 0, eq_mid: 0, eq_high: 0,
  filter_mode: "off", filter_hz: 1000, echo: false, echo_division: "1/4", echo_feedback: 0.45, echo_mix: 0.4,
  reverb: 0, drops: [], fade_in: 0, fade_out: 2, master: true,
  special_text: "", special_placement: "none", special_voice: null, special_mode: "spoken", special_song_id: null, sides: "vocal",
  special_volume: 1, sound_name: "", title: "",
};

type Props = {
  songs: Song[];
  player: MusicPlayer;
  onSongsChanged: () => void;
  onOpenLibrary: () => void;
};

/** Dub plate studio: a one-deck workspace with waveform, hot cues, loops and tempo, then FX, a voice special and the press. */
export function DubStudio({ songs, player, onSongsChanged, onOpenLibrary }: Props) {
  const [songId, setSongId] = useState<string | null>(null);
  const [info, setInfo] = useState<DubInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [deck, setDeck] = useState<DubState>({ cues: [], loops: [], bpm: 0, beat_offset: 0 });
  const [params, setParams] = useState<DubParams>(DEFAULT_PARAMS);
  const [cursor, setCursor] = useState(0);
  const [loop, setLoop] = useState<DubLoop | null>(null);
  const [loopOn, setLoopOn] = useState(false);
  const [zoom, setZoom] = useState<Zoom>("all");
  const [voices, setVoices] = useState<DubVoices | null>(null);
  const [busy, setBusy] = useState<PressBusy>(null);
  const [specialSong, setSpecialSong] = useState<Song | null>(null);
  const [specialMaking, setSpecialMaking] = useState(false);
  const [specialStatus, setSpecialStatus] = useState("");
  const [specialError, setSpecialError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [auditionUrl, setAuditionUrl] = useState<string | null>(null);
  const taps = useRef<number[]>([]);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSave = useRef<DubState | null>(null);

  const song = useMemo(() => songs.find((s) => s.id === songId) ?? null, [songs, songId]);
  const loaded = player.song?.id === songId && player.source !== null;
  const position = loaded ? player.position : cursor;
  const duration = info?.duration ?? 0;
  const bpm = deck.bpm;
  const beat = bpm > 0 ? 60 / bpm : 0;
  const rate = 1 + params.tempo_pct / 100;

  const patch = useCallback((p: Partial<DubParams>) => setParams((prev) => ({ ...prev, ...p })), []);

  // Choose a song: what is playing, otherwise the newest.
  useEffect(() => {
    if (songId && songs.some((s) => s.id === songId)) return;
    const next = (player.song && songs.find((s) => s.id === player.song?.id)) ?? songs[0] ?? null;
    setSongId(next?.id ?? null);
  }, [songs, songId, player.song]);

  useEffect(() => {
    musicApi.dubVoices().then(setVoices).catch(() => setVoices({ ready: false, voices: [] }));
  }, []);

  // Load analysis, cues and loops whenever the song changes.
  useEffect(() => {
    if (!songId) return;
    let cancelled = false;
    setInfo(null);
    setLoadError(null);
    setLoop(null);
    setLoopOn(false);
    setCursor(0);
    setAuditionUrl(null);
    setMessage(null);
    setParams((prev) => ({
      ...DEFAULT_PARAMS,
      special_voice: prev.special_voice, sound_name: prev.sound_name, special_text: prev.special_text,
      special_placement: prev.special_placement, special_mode: prev.special_mode, special_song_id: prev.special_song_id, sides: prev.sides,
    }));
    musicApi
      .dub(songId)
      .then((data) => {
        if (cancelled) return;
        setInfo(data);
        setDeck(data.state);
      })
      .catch((e) => !cancelled && setLoadError(e instanceof Error ? e.message : "Could not analyse this song."));
    return () => {
      cancelled = true;
    };
  }, [songId]);

  // Keep the cursor where the music was when it stops or pauses.
  useEffect(() => {
    if (loaded) setCursor(player.position);
  }, [loaded, player.position]);

  // Browser tempo fader (pitch locked); reset when leaving the studio.
  useEffect(() => {
    player.setRate(rate);
  }, [rate, player.setRate]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => player.setRate(1), [player.setRate]); // eslint-disable-line react-hooks/exhaustive-deps

  // Loop engine: jump back to the loop start when the playhead reaches the end (browser output).
  useEffect(() => {
    if (!loopOn || !loop) return;
    const id = window.setInterval(() => {
      if (player.source !== "browser" || player.song?.id !== songId || player.paused) return;
      if (player.getPosition() >= loop.end) void player.seek(loop.start);
    }, LOOP_CHECK_MS);
    return () => window.clearInterval(id);
  }, [loopOn, loop, player, songId]);

  const flushSave = useCallback(async () => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = null;
    const state = pendingSave.current;
    pendingSave.current = null;
    if (state && songId) await musicApi.saveDubState(songId, state).catch(() => undefined);
  }, [songId]);

  const updateDeck = useCallback(
    (next: DubState) => {
      setDeck(next);
      pendingSave.current = next;
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => void flushSave(), SAVE_DELAY_MS);
    },
    [flushSave],
  );
  useEffect(() => () => void flushSave(), [flushSave]);

  const playFrom = useCallback(
    async (start: number) => {
      if (!song) return;
      setCursor(start);
      await player.playInBrowser(song);
      player.setRate(rate);
      if (start > 0.2) await player.seek(start);
    },
    [song, player, rate],
  );

  const playPause = async () => {
    if (loaded) {
      await (player.paused ? player.play() : player.togglePause());
      return;
    }
    await playFrom(cursor);
  };

  const seekTo = (t: number) => {
    setCursor(t);
    if (loaded) void player.seek(t);
  };

  const jumpTo = (t: number) => {
    if (loaded) seekTo(t);
    else void playFrom(t);
  };

  const snap = (t: number) => (beat > 0 ? deck.beat_offset + Math.round((t - deck.beat_offset) / beat) * beat : t);

  const startAutoLoop = (beats: number) => {
    if (beat <= 0 || !duration) return;
    const start = Math.max(0, snap(position));
    const end = Math.min(duration, start + beats * beat);
    setLoop({ start, end, label: `${beats} beat${beats === 1 ? "" : "s"}` });
    setLoopOn(true);
  };

  const setCue = (slot: number) => updateDeck({ ...deck, cues: [...deck.cues.filter((c) => c.slot !== slot), { slot, time: round(position), label: "" }] });
  const clearCue = (slot: number) => updateDeck({ ...deck, cues: deck.cues.filter((c) => c.slot !== slot) });

  const tap = () => {
    const now = performance.now();
    taps.current = [...taps.current.filter((t) => now - t < 2500), now].slice(-8);
    if (taps.current.length >= 3) {
      const gaps = taps.current.slice(1).map((t, i) => t - taps.current[i]);
      const avg = gaps.reduce((a, b) => a + b, 0) / gaps.length;
      updateDeck({ ...deck, bpm: round(60000 / avg, 1) });
    }
  };

  const makeSpecial = async () => {
    if (!songId) return;
    setSpecialMaking(true);
    setSpecialError(null);
    setSpecialStatus("Starting...");
    try {
      let job = await musicApi.dubSpecial(songId, { text: params.special_text, sound_name: params.sound_name });
      while (job.status !== "done" && job.status !== "error") {
        setSpecialStatus(job.message);
        await new Promise((r) => setTimeout(r, 2000));
        job = await musicApi.job(job.id);
      }
      if (job.status === "error" || !job.song) throw new Error(job.error ?? job.message ?? "The special could not be made.");
      setSpecialSong(job.song);
      patch({ special_song_id: job.song.id });
      onSongsChanged();
    } catch (e) {
      setSpecialError(e instanceof Error ? e.message : "The special could not be made.");
    } finally {
      setSpecialMaking(false);
      setSpecialStatus("");
    }
  };

  const audition = async (side: "vocal" | "version") => {
    if (!songId) return;
    setBusy(side === "vocal" ? "audition-vocal" : "audition-version");
    setMessage(null);
    try {
      await flushSave();
      if (player.source) await player.stop();
      const res = await musicApi.dubPreview(songId, params, side);
      setAuditionUrl(assetUrl(res.audio_url) ?? res.audio_url);
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : "That did not work." });
    } finally {
      setBusy(null);
    }
  };

  const press = async () => {
    if (!songId) return;
    setBusy("press");
    setMessage(null);
    try {
      await flushSave();
      const { songs: made } = await musicApi.dubRender(songId, params);
      onSongsChanged();
      const names = made.map((m) => `"${m.title}"`).join(" and ");
      setMessage({ kind: "ok", text: `Pressed ${names} and saved ${made.length > 1 ? "them" : "it"} to your library.` });
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : "That did not work." });
    } finally {
      setBusy(null);
    }
  };

  if (songs.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
        Make a song first (Create tab), then bring it here to cut a dub plate.
      </div>
    );
  }

  const dropRegions = params.drops.map((d) => ({ at: d.at, end: d.at + d.beats * (beat || 0.5) }));
  const zoomSeconds = zoom === "all" ? duration : Number(zoom);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-[14rem] flex-1 space-y-1.5 text-xs font-medium">
          Track on the deck
          <select
            value={songId ?? ""}
            onChange={(e) => setSongId(e.target.value)}
            className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm"
          >
            {songs.map((s) => (
              <option key={s.id} value={s.id}>{s.title}{s.provider === "dubplate" ? " (dub plate)" : ""}</option>
            ))}
          </select>
        </label>
        <Segmented
          label="Waveform zoom"
          value={zoom}
          onChange={setZoom}
          options={[{ id: "all", label: "Whole song" }, { id: "30", label: "30 s" }, { id: "10", label: "10 s" }]}
        />
      </div>

      <Panel title="Deck" hint={loaded && player.source === "browser" ? "Playing in the browser" : "Plays in the browser so loops and tempo work"}>
        {loadError ? (
          <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{loadError}</p>
        ) : !info ? (
          <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> Reading the waveform and tempo...
          </div>
        ) : (
          <div className="space-y-3">
            <DubWaveform
              peaks={info.peaks}
              duration={info.duration}
              position={position}
              bpm={bpm}
              beatOffset={deck.beat_offset}
              cues={deck.cues}
              loop={loop ? { ...loop, active: loopOn } : null}
              trim={{ start: params.start, end: params.end ?? info.duration }}
              drops={dropRegions}
              zoomSeconds={zoomSeconds}
              onSeek={seekTo}
            />
            <div className="flex flex-wrap items-center gap-3">
              <Button size="icon" className="h-12 w-12 rounded-full" onClick={() => void playPause()} aria-label={loaded && !player.paused ? "Pause" : "Play"}>
                {loaded && !player.paused ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
              </Button>
              <Button size="icon" variant="outline" onClick={() => void player.stop()} disabled={!loaded} aria-label="Stop">
                <Square className="h-4 w-4" />
              </Button>
              <span className="text-sm font-semibold tabular-nums">{formatDuration(position)} <span className="font-normal text-muted-foreground">/ {formatDuration(duration)}</span></span>
              <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                {bpm > 0 ? `${(bpm * rate).toFixed(1)} BPM` : "No tempo found"}
                {params.tempo_pct !== 0 ? ` (${params.tempo_pct > 0 ? "+" : ""}${params.tempo_pct}%)` : ""}
              </span>
            </div>
          </div>
        )}
      </Panel>

      {info ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Panel title="Hot cues" hint="Tap an empty pad to set, a lit pad to jump">
            <div className="grid grid-cols-4 gap-2">
              {Array.from({ length: 8 }, (_, slot) => {
                const cue = deck.cues.find((c) => c.slot === slot);
                const color = CUE_COLORS[slot];
                return (
                  <div key={slot} className="relative">
                    <button
                      type="button"
                      onClick={() => (cue ? jumpTo(cue.time) : setCue(slot))}
                      aria-label={cue ? `Jump to cue ${slot + 1} at ${formatDuration(cue.time)}` : `Set cue ${slot + 1} here`}
                      className={cn("flex h-14 w-full flex-col items-center justify-center rounded-lg border text-xs font-semibold transition-colors", cue ? "text-[#0b0f14]" : "border-border text-muted-foreground hover:border-foreground/40")}
                      style={cue ? { background: color, borderColor: color } : undefined}
                    >
                      <span className="text-sm">{slot + 1}</span>
                      <span className="tabular-nums opacity-80">{cue ? formatDuration(cue.time) : "set"}</span>
                    </button>
                    {cue ? (
                      <button type="button" onClick={() => clearCue(slot)} aria-label={`Clear cue ${slot + 1}`} className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-card text-muted-foreground shadow ring-1 ring-border hover:text-destructive">
                        <X className="h-3 w-3" />
                      </button>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </Panel>

          <Panel title="Loops" hint={bpm > 0 ? "Snaps to the beat grid" : "Set a tempo first"}>
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {AUTO_LOOP_BEATS.map((b) => (
                  <Button key={b} size="sm" variant="outline" disabled={bpm <= 0} onClick={() => startAutoLoop(b)}>
                    {b < 1 ? "1/2" : b}
                  </Button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Button size="sm" variant="ghost" onClick={() => setLoop({ start: round(position), end: Math.min(duration, round(position) + (beat || 2)), label: "" })}>In</Button>
                <Button size="sm" variant="ghost" disabled={!loop} onClick={() => loop && position > loop.start + 0.1 && (setLoop({ ...loop, end: round(position) }), setLoopOn(true))}>Out</Button>
                <Button size="sm" variant={loopOn ? "default" : "outline"} disabled={!loop} onClick={() => setLoopOn((v) => !v)}>
                  <Repeat className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" /> {loopOn ? "Loop on" : "Loop off"}
                </Button>
                <Button size="sm" variant="ghost" disabled={!loop || deck.loops.length >= 8} onClick={() => loop && updateDeck({ ...deck, loops: [...deck.loops, { ...loop, label: loop.label || formatDuration(loop.start) }] })}>Save</Button>
              </div>
              {loop ? <p className="text-xs tabular-nums text-muted-foreground">{formatDuration(loop.start)} to {formatDuration(loop.end)}</p> : null}
              {deck.loops.length > 0 ? (
                <ul className="flex flex-wrap gap-1.5">
                  {deck.loops.map((l, i) => (
                    <li key={`${l.start}-${i}`} className="flex items-center overflow-hidden rounded-md bg-muted/50 text-xs">
                      <button type="button" className="px-2 py-1 hover:bg-muted" onClick={() => (setLoop(l), setLoopOn(true), jumpTo(l.start))}>{l.label || formatDuration(l.start)}</button>
                      <button type="button" aria-label="Remove saved loop" className="px-1.5 py-1 text-muted-foreground hover:text-destructive" onClick={() => updateDeck({ ...deck, loops: deck.loops.filter((_, j) => j !== i) })}><X className="h-3 w-3" /></button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {player.source === "speakers" && loaded ? <p className="text-xs text-amber-300">Loops need browser playback. Press play on the deck.</p> : null}
            </div>
          </Panel>

          <Panel title="Tempo and beat grid" hint={info.bpm > 0 ? `Detected ${info.bpm} BPM` : "Tempo not detected"}>
            <div className="space-y-3">
              <div className="flex items-center gap-1.5">
                <Input
                  type="number" min={0} max={300} step={0.1} value={bpm || ""} placeholder="BPM"
                  onChange={(e) => updateDeck({ ...deck, bpm: Math.max(0, Math.min(300, Number(e.target.value) || 0)) })}
                  className="w-24" aria-label="Song BPM"
                />
                <Button size="sm" variant="outline" disabled={bpm <= 0} onClick={() => updateDeck({ ...deck, bpm: round(bpm / 2, 1) })}>÷2</Button>
                <Button size="sm" variant="outline" disabled={bpm <= 0} onClick={() => updateDeck({ ...deck, bpm: round(Math.min(300, bpm * 2), 1) })}>×2</Button>
                <Button size="sm" variant="outline" onClick={tap}>Tap</Button>
              </div>
              <Button size="sm" variant="outline" disabled={beat <= 0} onClick={() => updateDeck({ ...deck, beat_offset: round(((position % beat) + beat) % beat) })}>
                Beat 1 is here
              </Button>
              <label className="block space-y-1.5">
                <span className="flex items-baseline justify-between text-xs">
                  <span className="font-medium" onDoubleClick={() => patch({ tempo_pct: 0 })} title="Double-click to reset">Tempo</span>
                  <span className="tabular-nums text-muted-foreground">{params.tempo_pct > 0 ? "+" : ""}{params.tempo_pct}%</span>
                </span>
                <input
                  type="range" min={-16} max={16} step={0.5} value={params.tempo_pct}
                  onChange={(e) => patch({ tempo_pct: Number(e.target.value) })}
                  className="seek-bar h-1.5 w-full cursor-pointer appearance-none rounded-full"
                  style={{ background: `linear-gradient(to right, hsl(var(--primary)) ${((params.tempo_pct + 16) / 32) * 100}%, hsl(var(--muted)) ${((params.tempo_pct + 16) / 32) * 100}%)` }}
                />
              </label>
              <p className="text-xs text-muted-foreground">Tempo changes speed without changing the key, live on the deck and in the pressed plate.</p>
            </div>
          </Panel>
        </div>
      ) : null}

      {info ? <DubFxPanel params={params} patch={patch} cursor={position} duration={duration} bpm={bpm} /> : null}

      {info ? (
        <DubPressPanel
          params={params}
          patch={patch}
          voices={voices}
          songTitle={song?.title ?? "Song"}
          busy={busy}
          message={message}
          auditionUrl={auditionUrl}
          stemsAvailable={info.stems_available}
          special={{ song: specialSong, making: specialMaking, status: specialStatus, error: specialError }}
          onMakeSpecial={() => void makeSpecial()}
          onAudition={(side) => void audition(side)}
          onPress={() => void press()}
          onOpenLibrary={onOpenLibrary}
        />
      ) : null}
    </div>
  );
}

function round(value: number, digits = 2): number {
  const f = 10 ** digits;
  return Math.round(value * f) / f;
}
