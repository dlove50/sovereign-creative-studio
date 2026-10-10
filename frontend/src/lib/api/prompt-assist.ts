import { request } from "./core";

export type PromptKind =
  | "general" | "story" | "lyrics" | "song_idea" | "podcast" | "narration" | "visual" | "video" | "style" | "movie";

export type MoviePlan = {
  title: string;
  logline: string;
  look: string;
  cast: { name: string; identity: string; wardrobe: string }[];
  rules: string;
  sound: string;
  chapters: { title: string; seconds: number; beats: string; guards: string }[];
};

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const promptAssistApi = {
  clean: (text: string, kind: PromptKind, context = "") => post<{ text: string }>("/api/prompt-assist/clean", { text, kind, context }),
  write: (idea: string, kind: PromptKind, context = "") => post<{ text: string }>("/api/prompt-assist/write", { idea, kind, context }),
  movie: (idea: string, seconds: number, context = "") =>
    post<{ plan: MoviePlan; text: string }>("/api/prompt-assist/movie", { idea, seconds, context }),
};
