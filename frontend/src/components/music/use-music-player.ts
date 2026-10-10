"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { assetUrl } from "@/lib/api/core";
import { musicApi, type NowPlaying, type Song, type SongVersion } from "@/lib/api/music";

export type PlaySource = "browser" | "speakers";

/** The full mix, or one side of the split (the vocal alone, or the music without it). */
function versionUrl(song: Song, version: SongVersion): string {
  return version === "full" ? song.audio_url : musicApi.stemUrl(song.id, version);
}

const POLL_MS = 1500;

/**
 * One player, two outputs: this browser tab, or the computer's speakers (which is
 * also how Jarvis plays songs). The speaker state is polled from the backend so the
 * screen follows whatever Jarvis starts, and the display stays in sync with either.
 */
export function useMusicPlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [song, setSong] = useState<Song | null>(null);
  const [source, setSource] = useState<PlaySource | null>(null);
  const [paused, setPaused] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [version, setVersionState] = useState<SongVersion>("full");
  const server = useRef({ position: 0, fetchedAt: 0 });
  const sourceRef = useRef<PlaySource | null>(null);
  sourceRef.current = source;
  const lastOutput = useRef<PlaySource>("speakers");
  const pausedRef = useRef(false);
  const versionRef = useRef<SongVersion>("full");
  const songRef = useRef<Song | null>(null);
  songRef.current = song;
  pausedRef.current = paused;
  versionRef.current = version;

  // Browser audio element
  useEffect(() => {
    const el = new Audio();
    el.preload = "auto";
    audio.current = el;
    const onTime = () => setPosition(el.currentTime);
    const onMeta = () => setDuration(Number.isFinite(el.duration) ? el.duration : 0);
    const onEnded = () => {
      setSource(null);
      setPaused(false);
      setPosition(0);
    };
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("ended", onEnded);
    return () => {
      el.pause();
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("ended", onEnded);
    };
  }, []);

  // Follow the speakers (started here, by Jarvis, or by anything else).
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      if (document.hidden) return;
      try {
        const state = await musicApi.nowPlaying();
        if (!alive) return;
        if ((state.playing || state.paused) && state.song) {
          audio.current?.pause();
          server.current = { position: state.position, fetchedAt: performance.now() };
          lastOutput.current = "speakers";
          setSong(state.song);
          setSource("speakers");
          setPaused(state.paused);
          setDuration(state.duration);
          setPosition(state.position);
        } else if (sourceRef.current === "speakers") {
          setSource(null);
          setPosition(0);
        }
      } catch {
        /* backend briefly unavailable: keep the last state */
      }
    };
    poll();
    const id = window.setInterval(poll, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  // Smooth progress for the speakers between polls.
  useEffect(() => {
    if (source !== "speakers" || paused) return;
    const id = window.setInterval(() => {
      const elapsed = (performance.now() - server.current.fetchedAt) / 1000;
      setPosition(Math.min(server.current.position + elapsed, duration || Infinity));
    }, 250);
    return () => window.clearInterval(id);
  }, [source, paused, duration]);

  const getPosition = useCallback((): number => {
    if (sourceRef.current === "speakers") {
      return server.current.position + (performance.now() - server.current.fetchedAt) / 1000;
    }
    return audio.current?.currentTime ?? 0;
  }, []);

  const playInBrowser = useCallback(async (next: Song, nextVersion: SongVersion = "full") => {
    const el = audio.current;
    if (!el) return;
    await musicApi.stop().catch(() => undefined);
    const url = versionUrl(next, nextVersion);
    el.src = assetUrl(url) ?? url;
    lastOutput.current = "browser";
    setVersionState(nextVersion);
    setSong(next);
    setSource("browser");
    setPaused(false);
    setPosition(0);
    setDuration(0);
    try {
      await el.play();
    } catch {
      setPaused(true);
    }
  }, []);

  const playOnSpeakers = useCallback(async (next: Song) => {
    audio.current?.pause();
    setVersionState("full"); // the speakers always play the full mix
    const state = await musicApi.play(next.id);
    lastOutput.current = "speakers";
    server.current = { position: state.position, fetchedAt: performance.now() };
    setSong(state.song ?? next);
    setSource("speakers");
    setPaused(false);
    setDuration(state.duration);
    setPosition(state.position);
  }, []);

  const applySpeakerState = useCallback((state: NowPlaying) => {
    server.current = { position: state.position, fetchedAt: performance.now() };
    setPaused(state.paused);
    setPosition(state.position);
  }, []);

  const togglePause = useCallback(async () => {
    if (sourceRef.current === "speakers") {
      const state = await (pausedRef.current ? musicApi.resume() : musicApi.pause()).catch(() => null);
      if (state) applySpeakerState(state);
      return;
    }
    const el = audio.current;
    if (!el || sourceRef.current !== "browser") return;
    if (el.paused) {
      el.play().then(() => setPaused(false)).catch(() => undefined);
    } else {
      el.pause();
      setPaused(true);
    }
  }, [applySpeakerState]);

  /** Play button: resume if paused, otherwise (re)start the current song on the last-used output. */
  const play = useCallback(async () => {
    if (sourceRef.current !== null) {
      if (pausedRef.current) await togglePause();
      return;
    }
    const current = songRef.current;
    if (!current) return;
    if (lastOutput.current === "browser") await playInBrowser(current, versionRef.current);
    else await playOnSpeakers(current);
  }, [togglePause, playInBrowser, playOnSpeakers]);

  const stop = useCallback(async () => {
    if (sourceRef.current === "speakers") await musicApi.stop().catch(() => undefined);
    const el = audio.current;
    if (el) {
      el.pause();
      el.currentTime = 0;
    }
    setSource(null);
    setPaused(false);
    setPosition(0);
  }, []);

  /** Browser playback speed with the pitch locked (the deck's tempo fader). */
  const setRate = useCallback((rate: number) => {
    const el = audio.current;
    if (!el) return;
    el.preservesPitch = true;
    el.defaultPlaybackRate = rate;
    el.playbackRate = rate;
  }, []);

  const seek = useCallback(async (seconds: number) => {
    if (sourceRef.current === "speakers") {
      const state = await musicApi.seek(seconds).catch(() => null);
      if (state) applySpeakerState(state);
      return;
    }
    const el = audio.current;
    if (el && sourceRef.current === "browser") {
      el.currentTime = seconds;
      setPosition(seconds);
    }
  }, [applySpeakerState]);

  /**
   * Switch between the full song, the vocal alone and the music alone without losing the place.
   * The split sides play in this browser tab (the speakers only play full songs).
   */
  const setVersion = useCallback(async (next: SongVersion) => {
    const el = audio.current;
    const current = songRef.current;
    if (!el || !current || next === versionRef.current) return;
    const onSpeakers = sourceRef.current === "speakers";
    const at = onSpeakers ? getPosition() : el.currentTime;
    const wasPlaying = sourceRef.current !== null && !pausedRef.current;
    if (onSpeakers) await musicApi.stop().catch(() => undefined);
    const url = versionUrl(current, next);
    el.addEventListener("loadedmetadata", () => {
      el.currentTime = Math.min(at, Number.isFinite(el.duration) ? el.duration : at);
      setPosition(el.currentTime);
    }, { once: true });
    el.src = assetUrl(url) ?? url;
    lastOutput.current = "browser";
    setVersionState(next);
    if (!wasPlaying) {
      if (sourceRef.current !== null) {
        setSource("browser");
        setPaused(true);
      }
      return;
    }
    setSource("browser");
    setPaused(false);
    try {
      await el.play();
    } catch {
      setPaused(true);
    }
  }, [getPosition]);

  /** Show an updated copy of the current song (new lyrics) without interrupting playback. */
  const replaceSong = useCallback((next: Song) => {
    setSong((current) => (current?.id === next.id ? next : current));
  }, []);

  return {
    song, source, paused, position, duration, getPosition, version, setVersion, replaceSong,
    playInBrowser, playOnSpeakers, play, togglePause, stop, seek, setRate,
    playing: source !== null && !paused,
  };
}

export type MusicPlayer = ReturnType<typeof useMusicPlayer>;
