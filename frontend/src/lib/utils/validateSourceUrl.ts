// First line of defense: validate a source URL before any API call. The backend
// re-validates independently (second line of defense). Only same-origin
// /storage/... paths are accepted.

import type { MediaType } from "@/lib/types/media";

export interface ValidateResult {
  ok: boolean;
  error: string | null;
}

const IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];
const VIDEO_EXTS = [".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"];
const AUDIO_EXTS = [".wav", ".mp3", ".m4a", ".ogg", ".flac"];

function extOf(url: string): string {
  const clean = url.split("?")[0].split("#")[0];
  const idx = clean.lastIndexOf(".");
  return idx >= 0 ? clean.slice(idx).toLowerCase() : "";
}

function extMatchesTypes(ext: string, acceptTypes: MediaType[]): boolean {
  for (const t of acceptTypes) {
    if (t === "image" && IMAGE_EXTS.includes(ext)) return true;
    if ((t === "video" || t === "avatar_video") && VIDEO_EXTS.includes(ext)) return true;
    if (t === "audio" && AUDIO_EXTS.includes(ext)) return true;
    if (t === "product_scene" && IMAGE_EXTS.includes(ext)) return true;
    // transcript has no file extension to validate here
    if (t === "transcript") return true;
  }
  return false;
}

export function validateSourceUrl(url: string, acceptTypes: MediaType[] = []): ValidateResult {
  const value = (url ?? "").trim();
  if (!value) {
    return { ok: false, error: "Enter or choose a source." };
  }
  // Windows path e.g. C:\Users\David\Pictures\3d dog.png
  if (/^[A-Za-z]:\\/.test(value)) {
    return { ok: false, error: "Windows paths are not accepted here. Upload the file or choose it from Assets." };
  }
  // Path traversal
  if (value.includes("..")) {
    return { ok: false, error: "Path traversal is not allowed." };
  }
  // External URLs
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value) || value.startsWith("//")) {
    return { ok: false, error: "External URLs are not accepted. Upload the file or choose from Assets." };
  }
  // Must be a same-origin storage path
  if (!value.startsWith("/storage/")) {
    return { ok: false, error: "External URLs are not accepted. Upload the file or choose from Assets." };
  }
  // File-type compatibility for this workflow
  if (acceptTypes.length > 0) {
    const ext = extOf(value);
    if (ext && !extMatchesTypes(ext, acceptTypes)) {
      return { ok: false, error: "This file type is not compatible with this tool." };
    }
  }
  return { ok: true, error: null };
}
