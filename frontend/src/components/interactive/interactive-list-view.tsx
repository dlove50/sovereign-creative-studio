"use client";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GitBranch, Plus, Trash2 } from "lucide-react";

import trainingExample from "@/lib/training-example.json";
import { api } from "@/lib/api";

type Item = Awaited<ReturnType<typeof api.listInteractive>>[number];

export function InteractiveListView() {
  const router = useRouter();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listInteractive().then(setItems).catch((e) => { setItems([]); setError(e instanceof Error ? e.message : "Could not load your interactive videos."); });
  }, []);

  async function create() {
    try {
      const made = await api.createInteractive({ title: "Untitled interactive video", nodes: [] });
      router.push(`/interactive/${made.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create it.");
    }
  }

  async function startTraining(){try{const made=await api.createInteractive(trainingExample);router.push(`/interactive/${made.id}`);}catch(e){setError(e instanceof Error?e.message:"Could not create training example.");}}

  async function remove(id: string) {
    if (!await confirmDialog("Delete this interactive video?")) return;
    await api.deleteInteractive(id);
    setItems((all) => (all ?? []).filter((i) => i.id !== id));
  }

  return (
    <div className="mx-auto max-w-[760px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Interactive video</h1>
      <p className="mx-auto mt-2 max-w-md text-center text-sm text-muted-foreground">
        Connect your finished videos into a story where the viewer picks what happens next.
      </p>
      <div className="mt-6 flex justify-center">
        <button type="button" onClick={create} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90">
          <Plus className="h-4 w-4" /> New interactive video
        </button>
      </div>
      <div className="mt-4 text-center"><button type="button" onClick={startTraining} className="rounded-lg border border-border px-4 py-2 font-medium">Start training example</button><p className="mt-2 text-sm text-muted-foreground">Creates an editable text-only practice scenario. No video render or charge.</p></div>
      {error ? <p className="mt-4 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {items && items.length === 0 ? <p className="py-14 text-center text-sm text-muted-foreground">Nothing here yet. Make a video with choices to get started.</p> : null}
      <ul className="mt-6 space-y-2">
        {(items ?? []).map((item) => (
          <li key={item.id} className="flex items-center gap-3 rounded-2xl border border-border bg-card/50 p-3">
            <GitBranch className="h-5 w-5 text-primary" aria-hidden />
            <Link href={`/interactive/${item.id}`} className="flex-1 text-sm font-semibold hover:underline">
              {item.title}
              <span className="block text-xs font-normal text-muted-foreground">{item.nodes.length} clips</span>
            </Link>
            <button type="button" onClick={() => remove(item.id)} aria-label={`Delete ${item.title}`} className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-raised hover:text-destructive">
              <Trash2 className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
