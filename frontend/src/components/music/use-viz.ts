"use client";

import { useEffect, useState } from "react";

import { decodeViz, musicApi } from "@/lib/api/music";

export type Viz = { frames: Uint8Array; bands: number; fps: number; duration: number };

const cache = new Map<string, Promise<Viz | null>>();

function load(songId: string): Promise<Viz | null> {
  let hit = cache.get(songId);
  if (!hit) {
    hit = musicApi
      .viz(songId)
      .then((v) => ({ frames: decodeViz(v), bands: v.bands, fps: v.fps, duration: v.duration }))
      .catch(() => {
        cache.delete(songId);
        return null;
      });
    cache.set(songId, hit);
  }
  return hit;
}

/** Real band-energy data for a song (null while loading or if unavailable). */
export function useViz(songId: string | null): Viz | null {
  const [viz, setViz] = useState<{ id: string; data: Viz } | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!songId) return;
    load(songId).then((data) => {
      if (!cancelled && data) setViz({ id: songId, data });
    });
    return () => {
      cancelled = true;
    };
  }, [songId]);
  return songId && viz?.id === songId ? viz.data : null;
}
