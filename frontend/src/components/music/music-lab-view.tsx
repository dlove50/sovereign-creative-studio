"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AudioLines, Cpu, Disc3, Library, Wand2 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { musicApi, type MusicStatus, type Song } from "@/lib/api/music";
import { cn } from "@/lib/utils";

import { CreatePanel, type PlayTarget } from "./create-panel";
import { DubStudio } from "./dub-studio";
import { EnginePanel } from "./engine-panel";
import { LibraryPanel } from "./library-panel";
import { PlayerDock } from "./player-dock";
import { StagePanel } from "./stage-panel";
import { useMusicPlayer } from "./use-music-player";

type TabId = "create" | "library" | "stage" | "dub" | "engine";

const TABS: { id: TabId; label: string; icon: typeof Wand2 }[] = [
  { id: "create", label: "Create", icon: Wand2 },
  { id: "library", label: "Library", icon: Library },
  { id: "stage", label: "Stage", icon: AudioLines },
  { id: "dub", label: "Dub Plate", icon: Disc3 },
  { id: "engine", label: "Engine", icon: Cpu },
];

function isTab(value: string | null): value is TabId {
  return TABS.some((t) => t.id === value);
}

export function MusicLabView() {
  const params = useSearchParams();
  const player = useMusicPlayer();
  const [tab, setTab] = useState<TabId>(() => {
    const requested = params.get("tab");
    if (isTab(requested)) return requested;
    return params.get("display") ? "stage" : "create";
  });
  const [status, setStatus] = useState<MusicStatus | null>(null);
  const [songs, setSongs] = useState<Song[]>([]);
  const [loadingSongs, setLoadingSongs] = useState(true);

  const refreshStatus = useCallback(() => {
    musicApi.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  const refreshSongs = useCallback(() => {
    musicApi
      .songs()
      .then(setSongs)
      .catch(() => setSongs([]))
      .finally(() => setLoadingSongs(false));
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshSongs();
    const id = window.setInterval(refreshStatus, 15000);
    return () => window.clearInterval(id);
  }, [refreshStatus, refreshSongs]);

  // When Jarvis (or another tab) starts a song on the speakers, show the display.
  const speakersActive = player.source === "speakers";
  useEffect(() => {
    if (speakersActive && params.get("display")) setTab("stage");
  }, [speakersActive, params]);

  const onSongReady = useCallback(
    (song: Song, target: PlayTarget) => {
      refreshSongs();
      refreshStatus();
      if (target === "browser") {
        void player.playInBrowser(song);
        setTab("stage");
      } else if (target === "speakers") {
        setTab("stage");
      } else {
        setTab("library");
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refreshSongs, refreshStatus, player.playInBrowser],
  );

  const engine = status?.engine;
  const dockOpen = player.source !== null;

  return (
    <div className={cn("space-y-6", dockOpen && "pb-24")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title="Music Lab"
          description="Turn an idea or your own lyrics into a complete song with the local YuE2 engine."
        />
        <Badge variant={engine?.ready ? "success" : engine?.online ? "default" : "muted"} className="mt-1">
          {engine?.ready ? "YuE2 ready" : engine?.online ? "YuE2 needs attention" : "YuE2 offline"}
        </Badge>
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-border" role="tablist" aria-label="Music Lab sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "relative flex h-11 shrink-0 items-center gap-2 px-4 text-sm font-medium transition-colors",
              tab === t.id ? "text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <t.icon className="h-4 w-4" aria-hidden="true" />
            {t.label}
            {t.id === "library" && songs.length > 0 ? (
              <span className="rounded-full bg-muted px-1.5 text-xs tabular-nums text-muted-foreground">{songs.length}</span>
            ) : null}
            {t.id === "stage" && dockOpen ? <span className="h-2 w-2 animate-pulse rounded-full bg-primary" aria-label="Playing" /> : null}
            {tab === t.id ? <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-primary" /> : null}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === "create" ? (
          <div className="rounded-2xl border border-border bg-card p-5 md:p-6">
            <CreatePanel status={status} onSongReady={onSongReady} />
          </div>
        ) : null}
        {tab === "library" ? (
          <LibraryPanel songs={songs} loading={loadingSongs} player={player} onChanged={refreshSongs} />
        ) : null}
        {tab === "stage" ? <StagePanel player={player} /> : null}
        {tab === "dub" ? (
          <DubStudio songs={songs} player={player} onSongsChanged={refreshSongs} onOpenLibrary={() => setTab("library")} />
        ) : null}
        {tab === "engine" ? <EnginePanel status={status} onRefresh={refreshStatus} /> : null}
      </div>

      <PlayerDock player={player} onOpenStage={() => setTab("stage")} />
    </div>
  );
}
