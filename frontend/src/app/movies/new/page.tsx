"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function NewMoviePage() {
  const router = useRouter();
  const started = useRef(false);
  const active = useRef(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api.createMovie().then((movie) => { if (active.current) router.replace(`/movies/${movie.id}`); }).catch((e) => {
      if (!active.current) return;
      setError(e instanceof Error ? e.message : "Your video could not be created.");
      started.current = false;
    });
  }, [router, attempt]);
  return <div className="py-16 text-center" role="status">
    <h1 className="text-xl font-semibold">{error ? "Could not create video" : "Creating your video…"}</h1>
    {error ? <><p className="mt-3 text-sm text-destructive">{error}</p>
      <button className="mt-4 rounded-full bg-primary px-5 py-2 text-primary-foreground" onClick={() => { setError(null); setAttempt((n) => n + 1); }}>Try again</button></> : null}
    <Link href="/projects" className="mt-4 block text-sm text-primary hover:underline">Back to projects</Link>
  </div>;
}
