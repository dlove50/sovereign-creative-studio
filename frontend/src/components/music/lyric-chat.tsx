"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Send } from "lucide-react";

import { VoiceInputButton } from "@/components/chain/VoiceInputButton";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { musicApi } from "@/lib/api/music";

export type DraftSong = { title: string; style: string; lyrics: string };
type Turn = { role: "user" | "assistant"; content: string };

const STARTERS = [
  "A reggae song about sunrise at the bay",
  "A slow country ballad about my grandfather's farm",
  "An upbeat pop song about finishing a big project",
];

/**
 * A songwriting chat. Type or speak what the song should be; the local lyric writer drafts it and keeps rewriting
 * as you ask ("make the chorus sadder", "add a bridge about the sea"). Every reply updates the song in the form, so
 * the Create song button below always makes the latest version.
 */
export function LyricChat({ song, duration, onSong }: { song: DraftSong; duration: number; onSong: (song: DraftSong) => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [turns, busy]);

  async function send(message: string) {
    const content = message.trim();
    if (!content || busy) return;
    const next: Turn[] = [...turns, { role: "user", content }];
    setTurns(next);
    setText("");
    setError(null);
    setBusy(true);
    try {
      const out = await musicApi.lyricsChat({ messages: next, current: song.lyrics ? song : undefined, duration });
      setTurns([...next, { role: "assistant", content: out.reply }]);
      onSong({ title: out.title, style: out.style, lyrics: out.lyrics });
    } catch (e) {
      setError(e instanceof Error ? e.message : "The lyric writer could not answer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="flex min-h-[320px] flex-col rounded-xl border border-border bg-background/40">
        <div ref={log} role="log" aria-live="polite" data-lenis-prevent className="max-h-[360px] flex-1 space-y-3 overflow-y-auto p-4">
          {turns.length === 0 ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Tell me what the song should be, by typing or with the microphone. I write the lyrics, then change them whenever you ask.
              </p>
              <div className="flex flex-wrap gap-2">
                {STARTERS.map((starter) => (
                  <button
                    key={starter}
                    type="button"
                    onClick={() => void send(starter)}
                    className="rounded-full border border-border px-3 py-1 text-left text-xs text-muted-foreground transition duration-200 hover:border-primary/50 hover:text-foreground"
                  >
                    {starter}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            turns.map((turn, i) => (
              <div key={i} className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <p className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${turn.role === "user" ? "bg-primary text-primary-foreground" : "bg-raised"}`}>
                  {turn.content}
                </p>
              </div>
            ))
          )}
          {busy ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Writing…</p>
          ) : null}
        </div>
        {error ? <p role="alert" className="px-4 pb-2 text-sm text-destructive">{error}</p> : null}
        <form
          className="flex items-end gap-2 border-t border-border p-3"
          onSubmit={(e) => { e.preventDefault(); void send(text); }}
        >
          <VoiceInputButton disabled={busy} onTranscript={(spoken) => void send(spoken)} />
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(text); } }}
            maxLength={600}
            placeholder={turns.length ? "Ask for a change…" : "Describe the song…"}
            aria-label="Message to the songwriter"
            className="min-h-[44px] flex-1 resize-none"
            rows={2}
          />
          <Button type="submit" size="icon" disabled={busy || !text.trim()} aria-label="Send">
            <Send className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>
      </div>

      <div className="rounded-xl border border-border bg-background/40 p-4">
        {song.lyrics ? (
          <>
            <p className="text-base font-semibold">{song.title || "Untitled"}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">{song.style}</p>
            <pre data-lenis-prevent className="mt-3 max-h-[300px] overflow-y-auto whitespace-pre-wrap font-sans text-sm leading-relaxed">{song.lyrics}</pre>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Your lyrics appear here and update as we talk. When you like them, press Create song below.</p>
        )}
      </div>
    </div>
  );
}
