// Pure TypeScript: defines what each media type can do next. No React, no API,
// no navigation. Unavailable actions are returned with an honest status
// (setup-required / coming-soon / needs-repair) rather than hidden, so the UI can
// show them disabled with a label. Nothing is marked "available" unless it works.

import type { ActionDef, ActionId, MediaObject, MediaType, WorkflowStatus } from "@/lib/types/media";

export interface CompatibilityContext {
  /** Hide "Open in Assets" when the media is already shown inside Asset Library. */
  inAssets?: boolean;
  /** Avatar-from-image / voice are only "available" when the avatar stack is ready. */
  avatarReady?: boolean;
}

type Def = Omit<ActionDef, "primary">;

const A = (
  id: ActionId,
  label: string,
  status: WorkflowStatus,
  targetRoute: string | null,
  targetMode: string | null,
  icon: string,
): Def => ({ id, label, status, targetRoute, targetMode, icon });

// Primary action per media type (the big "what next" button).
const PRIMARY_BY_TYPE: Record<MediaType, ActionId | null> = {
  image: "animate_image",
  video: "transcribe_video",
  transcript: "summarize_transcript",
  audio: "use_for_avatar_voice",
  product_scene: "animate_scene",
  avatar_video: "download",
};

const UNIVERSAL: Def[] = [
  A("download", "Download", "available", null, null, "Download"),
  A("copy_url", "Copy URL", "available", null, null, "Link"),
  A("open_in_assets", "Open in Assets", "available", "/assets-library", null, "Archive"),
  A("view_details", "View Details", "available", null, null, "Info"),
];

function imageActions(ctx: CompatibilityContext): Def[] {
  return [
    A("animate_image", "Animate This Image", "available", "/videos", "image_to_video", "Clapperboard"),
    A("edit_image", "Edit This Image", "available", "/create", "image_edit", "Wand2"),
    A("product_scene", "Use in Product Scene", "available", "/product-scenes", null, "Megaphone"),
    A("use_reference", "Use as Reference", "available", "/product-scenes", "reference", "Images"),
    // Destination checks live readiness and imports only an owned image.
    A("avatar_from_image", "Make Talking Avatar", ctx.avatarReady === false ? "setup-required" : "available", "/avatars/from-image", null, "PersonStanding"),
  ];
}

function videoActions(): Def[] {
  return [
    A("transcribe_video", "Transcribe This Video", "available", "/video-to-text", null, "Type"),
    A("upscale_video", "Upscale This Video", "available", "/videos", "video_upscale", "Sparkles"),
    // The destination checks live backend prerequisites before accepting a job.
    A("video_to_video", "Video-to-Video", "available", "/videos", "video_to_video", "Film"),
    A("extend_video", "Extend Video", "available", "/videos", "video_extension", "Film"),
  ];
}

function transcriptActions(): Def[] {
  return [
    A("summarize_transcript", "Summarize Transcript", "available", "/video-to-text", null, "Sparkles"),
    A("send_to_copy_studio", "Send to Copy Studio", "available", "/copy-studio", null, "PenLine"),
    A("copy_text", "Copy Text", "available", null, null, "Copy"),
    A("download_transcript", "Download Transcript", "available", null, null, "Download"),
  ];
}

function audioActions(ctx: CompatibilityContext): Def[] {
  return [
    A("use_for_avatar_voice", "Use for Avatar Voice", ctx.avatarReady ? "available" : "setup-required", "/avatars", null, "Mic"),
  ];
}

function productSceneActions(): Def[] {
  return [
    A("animate_scene", "Animate This Scene", "available", "/videos", "image_to_video", "Clapperboard"),
  ];
}

function primarySpecific(media: MediaObject, ctx: CompatibilityContext): Def[] {
  switch (media.type) {
    case "image":
      return imageActions(ctx);
    case "video":
      return videoActions();
    case "transcript":
      return transcriptActions();
    case "audio":
      return audioActions(ctx);
    case "product_scene":
      return productSceneActions();
    case "avatar_video":
      return [];
    default:
      return [];
  }
}

export function getActionsForMedia(media: MediaObject, context: CompatibilityContext = {}): ActionDef[] {
  if (!media || media.status === "failed") return [];
  const primaryId = PRIMARY_BY_TYPE[media.type];
  const specific = primarySpecific(media, context);
  let universal = UNIVERSAL;
  if (context.inAssets) universal = universal.filter((a) => a.id !== "open_in_assets");
  // avatar_from_image / use_for_avatar_voice honor avatarReady
  const merged = [...specific, ...universal].map((d) => ({
    ...d,
    primary: d.id === primaryId,
  }));
  return merged;
}

export function getPrimaryAction(media: MediaObject): ActionDef | null {
  if (!media || media.status === "failed") return null;
  const primaryId = PRIMARY_BY_TYPE[media.type];
  if (!primaryId) return null;
  const all = getActionsForMedia(media);
  return all.find((a) => a.id === primaryId) ?? null;
}

const COMPAT: Record<MediaType, Set<ActionId>> = {
  image: new Set<ActionId>(["animate_image", "edit_image", "product_scene", "use_reference", "avatar_from_image"]),
  video: new Set<ActionId>(["transcribe_video", "upscale_video", "video_to_video", "extend_video"]),
  transcript: new Set<ActionId>(["summarize_transcript", "send_to_copy_studio", "copy_text", "download_transcript"]),
  audio: new Set<ActionId>(["use_for_avatar_voice"]),
  product_scene: new Set<ActionId>(["animate_scene"]),
  avatar_video: new Set<ActionId>([]),
};

const UNIVERSAL_IDS = new Set<ActionId>(["download", "copy_url", "open_in_assets", "view_details"]);

export function isCompatible(mediaType: MediaType, actionId: ActionId): boolean {
  if (UNIVERSAL_IDS.has(actionId)) return true;
  return COMPAT[mediaType]?.has(actionId) ?? false;
}
