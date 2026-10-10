"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { assetUrl } from "@/lib/api/core";
import { musicApi, type NowPlaying, type Song } from "@/lib/api/music";

export type PlaySource = "browser" | "speakers";

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
  const server = useRef({ position: 0, fetchedAt: 0 });
  const sourceRef = useRef<PlaySource | null>(null);
  sourceRef.current = source;
  const lastOutput = useRef<PlaySource>("speakers");
  const pausedRef = useRef(false);
  const songRef = useRef<Song | null>(null);
  songRef.current = song;
  pausedRef.current = paused;

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

  const playInBrowser = useCallback(async (next: Song) => {
    const el = audio.current;
    if (!el) return;
    await musicApi.stop().catch(() => undefined);
    el.src = assetUrl(next.audio_url) ?? next.audio_url;
    lastOutput.current = "browser";
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
    if (lastOutput.current === "browser") await playInBrowser(current);
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

  return {
    song, source, paused, position, duration, getPosition,
    playInBrowser, playOnSpeakers, play, togglePause, stop, seek, setRate,
    playing: source !== null && !paused,
  };
}

export type MusicPlayer = ReturnType<typeof useMusicPlayer>;
