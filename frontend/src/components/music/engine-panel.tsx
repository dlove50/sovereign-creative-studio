"use client";

import { useState } from "react";
import Link from "next/link";
import { Cloud, Cpu, ExternalLink, Loader2, Power } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { musicApi, type MusicStatus } from "@/lib/api/music";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border/60 py-2 text-sm last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate text-right font-medium">{value}</dd>
    </div>
  );
}

export function EnginePanel({ status, onRefresh }: { status: MusicStatus | null; onRefresh: () => void }) {
  const [starting, setStarting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const start = async () => {
    setStarting(true);
    setMessage(null);
    try {
      const res = await musicApi.startEngine();
      setMessage(res.started ? "Starting the engine. This takes about a minute." : "The engine is already running.");
      window.setTimeout(onRefresh, 4000);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not start the engine.");
    } finally {
      setStarting(false);
    }
  };

  const engine = status?.engine;
  const tone = engine?.ready ? "success" : engine?.online ? "default" : "muted";

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="space-y-4 rounded-2xl border border-primary/30 bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500/20 to-cyan-500/10">
              <Cpu className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h2 className="font-semibold">YuE2 · local</h2>
              <p className="text-sm text-muted-foreground">Default engine. Free, private, runs on this PC.</p>
            </div>
          </div>
          <Badge variant={tone}>{engine?.ready ? "Ready" : engine?.online ? "Needs attention" : "Offline"}</Badge>
        </div>
        <dl>
          <Row label="Status" value={engine?.detail ?? "Checking…"} />
          <Row label="Model" value={engine?.checkpoint ?? "—"} />
          <Row label="Model file found" value={engine ? (engine.checkpoint_present ? "Yes" : "No") : "—"} />
          <Row label="YuE2 support" value={engine ? (engine.nodes_present ? "Yes" : "No") : "—"} />
          <Row label="Free video memory" value={engine?.vram_free_gb != null ? `${engine.vram_free_gb} GB` : "—"} />
        </dl>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={start} disabled={starting || engine?.online}>
            {starting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Power className="h-4 w-4" aria-hidden="true" />}
            Start engine
          </Button>
          <Button variant="ghost" onClick={onRefresh}>Refresh</Button>
          {message ? <span role="status" className="text-sm text-muted-foreground">{message}</span> : null}
        </div>
        <p className="text-xs text-muted-foreground">
          YuE2 model weights are licensed for non-commercial use. Songs are made on your own GPU; nothing is uploaded.
        </p>
      </section>

      <section className="space-y-4 rounded-2xl border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/10">
              <Cloud className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h2 className="font-semibold">ElevenLabs · cloud</h2>
              <p className="text-sm text-muted-foreground">Optional. Paid service that uses your ElevenLabs credits.</p>
            </div>
          </div>
          <Badge variant="muted">Optional</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Sovereign makes songs with YuE2 first, so nothing is billed. If you ever want ElevenLabs music instead, it
          stays available in Cloud Studio under the Music mode.
        </p>
        <Link href="/cloud-studio" className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
          Open Cloud Studio <ExternalLink className="h-4 w-4" aria-hidden="true" />
        </Link>
      </section>

      <section className="rounded-2xl border border-border bg-card p-5 lg:col-span-2">
        <h2 className="mb-2 font-semibold">Ask Jarvis</h2>
        <p className="text-sm text-muted-foreground">
          Say or type “make me a reggae song about a sunrise at the bay.” Jarvis writes the lyrics, Sovereign composes the
          whole song with YuE2, plays it through your speakers and shows it on the Stage tab here.
        </p>
      </section>
    </div>
  );
}
