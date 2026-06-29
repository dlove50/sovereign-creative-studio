// Phase 1 — UI/UX handoff system. The MediaObject is the single shape every
// "what do you want to do next" surface depends on. Mappers (mediaMapping.ts)
// translate each backend entity into this shape; UI never reads raw backend rows.

export type MediaType =
  | "image"
  | "video"
  | "transcript"
  | "audio"
  | "product_scene"
  | "avatar_video";

// Status of a *next action* (not of the media itself).
export type WorkflowStatus =
  | "available"
  | "setup-required"
  | "coming-soon"
  | "needs-repair";

export type ActionId =
  // image
  | "animate_image"
  | "edit_image"
  | "product_scene"
  | "use_reference"
  | "avatar_from_image"
  // video
  | "upscale_video"
  | "transcribe_video"
  | "video_to_video"
  | "extend_video"
  // transcript
  | "summarize_transcript"
  | "send_to_copy_studio"
  | "copy_text"
  | "download_transcript"
  // audio / product scene
  | "use_for_avatar_voice"
  | "animate_scene"
  // universal
  | "download"
  | "copy_url"
  | "open_in_assets"
  | "view_details";

export interface MediaMetadata {
  width: number | null;
  height: number | null;
  duration: number | null;
  fps: number | null;
  resolution: string | null;
  language: string | null;
  transcriptText: string | null;
  audioDuration: number | null;
}

export interface MediaObject {
  mediaId: string;
  type: MediaType;
  filename: string | null;
  /** Raw /storage/... URL. Never shown in the main UI — only Copy URL + Details. */
  storageUrl: string | null;
  thumbnailUrl: string | null;
  sourceWorkflow: string | null;
  projectId: string | null;
  ownerId: string | null;
  createdAt: string | null;
  provider: string | null;
  generationMode: string | null;
  prompt: string | null;
  creditsCharged: number | null;
  jobId: string | null;
  /** Job lifecycle status (queued/running/completed/failed) where known. */
  status: string | null;
  metadata: MediaMetadata;
}

export interface ActionDef {
  id: ActionId;
  label: string;
  status: WorkflowStatus;
  /** Target page route, e.g. "/videos". Null for in-place actions (copy/download). */
  targetRoute: string | null;
  /** Target workflow mode, e.g. "image_to_video". */
  targetMode: string | null;
  primary?: boolean;
  /** lucide-react icon name, resolved in the UI layer. */
  icon?: string;
  description?: string | null;
}

export interface HandoffAction {
  actionId: ActionId;
  media: MediaObject;
  targetRoute: string | null;
  targetMode: string | null;
  label: string;
}

export function emptyMediaMetadata(): MediaMetadata {
  return {
    width: null,
    height: null,
    duration: null,
    fps: null,
    resolution: null,
    language: null,
    transcriptText: null,
    audioDuration: null,
  };
}
