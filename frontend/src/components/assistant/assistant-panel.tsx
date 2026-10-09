"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, MessageCircle, Send, X } from "lucide-react";

import { api } from "@/lib/api";

type Turn = { role: "user" | "assistant"; content: string; opened?: string };

const GREETING: Turn = {
  role: "assistant",
  content: "Hello. Ask me how anything in the studio works, or tell me where you want to go. I can open pages and look up your credits, avatars and recent videos. I never start a render or spend credits.",
};

// A small helper that answers how-to questions and opens pages; it takes no costly or destructive action.
export function AssistantPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([GREETING]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [turns, busy, open]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);

  async function send() {
    const question = text.trim();
    if (!question || busy) return;
    const next: Turn[] = [...turns, { role: "user", content: question }];
    setTurns(next);
    setText("");
    setBusy(true);
    setError(null);
    try {
      const history = next.filter((t) => t !== GREETING).map(({ role, content }) => ({ role, content })).slice(-12);
      const answer = await api.assistantChat(history);
      setTurns((all) => [...all, { role: "assistant", content: answer.reply, opened: answer.navigate_to ? answer.page ?? undefined : undefined }]);
      if (answer.navigate_to) router.push(answer.navigate_to);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The assistant could not answer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {open ? (
        <section aria-label="Studio assistant" className="fixed bottom-20 right-4 z-50 flex h-[min(520px,70vh)] w-[min(380px,calc(100vw-2rem))] flex-col rounded-3xl border border-border bg-card shadow-2xl shadow-black/40">
          <header className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">Studio assistant</h2>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close the assistant" className="rounded-full p-1 text-muted-foreground hover:bg-raised"><X className="h-4 w-4" /></button>
          </header>
          <div ref={log} role="log" aria-live="polite" className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
            {turns.map((t, i) => (
              <p key={i} className={t.role === "user" ? "ml-8 rounded-2xl bg-primary/20 px-3 py-2" : "mr-8 rounded-2xl bg-background px-3 py-2"}>
                {t.content}
                {t.opened ? <span className="mt-1 block text-xs text-muted-foreground">Opened {t.opened}.</span> : null}
              </p>
            ))}
            {busy ? <p className="mr-8 flex items-center gap-2 rounded-2xl bg-background px-3 py-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Thinking…</p> : null}
            {error ? <p role="alert" className="rounded-xl bg-destructive/15 px-3 py-2 text-destructive">{error}</p> : null}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2 border-t border-border p-3">
            <label className="sr-only" htmlFor="assistant-input">Ask the assistant</label>
            <input id="assistant-input" ref={input} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Ask how to do something…" className="h-10 min-w-0 flex-1 rounded-xl border border-input bg-background px-3 text-sm" />
            <button type="submit" disabled={busy || !text.trim()} aria-label="Send" className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground disabled:opacity-50"><Send className="h-4 w-4" /></button>
          </form>
        </section>
      ) : null}
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label={open ? "Close the assistant" : "Open the studio assistant"} className="fixed bottom-4 right-4 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-black/40 hover:bg-primary/90">
        <MessageCircle className="h-5 w-5" />
      </button>
    </>
  );
}
