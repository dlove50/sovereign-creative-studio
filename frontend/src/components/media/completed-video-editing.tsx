"use client";

import type { MediaObject } from "@/lib/types/media";
import { useMediaHandoffRouter } from "./useMediaHandoffRouter";

export function CompletedVideoEditing({ id, url, title, origin }: { id: string; url: string; title: string; origin: string }) {
  const { onAction } = useMediaHandoffRouter(origin);
  const media: MediaObject = {
    mediaId: id, type: "video", storageUrl: url, filename: null, thumbnailUrl: null,
    sourceWorkflow: origin, projectId: null, ownerId: null, createdAt: null,
    provider: null, generationMode: null, prompt: title, creditsCharged: null,
    jobId: null, status: "completed", metadata: { width: null, height: null, duration: null, fps: null, resolution: null, language: null, transcriptText: null, audioDuration: null },
  };
  return <div className="space-y-2"><p className="text-sm text-muted-foreground">Continue with this completed video. Review settings before submitting; opening a tool does not start a job.</p><div className="flex flex-wrap gap-2">
    {([
      ["video_to_video", "Video-to-Video", "/videos", "video_to_video"],
      ["extend_video", "Extend Video", "/videos", "video_extension"],
      ["upscale_video", "Upscale Video", "/videos", "video_upscale"],
      ["transcribe_video", "Transcribe Video", "/video-to-text", null],
    ] as const).map(([actionId, label, targetRoute, targetMode]) => <button key={actionId} type="button" className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-raised" onClick={() => onAction({ actionId, label, targetRoute, targetMode, media })}>{label}</button>)}
  </div></div>;
}
