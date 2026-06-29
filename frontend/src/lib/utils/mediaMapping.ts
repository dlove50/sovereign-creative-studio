// Translate backend entities into the single MediaObject shape. Every function is
// tolerant of missing/optional fields: unknown values become null and never throw,
// so one absent metadata field can't crash the UI. Failed jobs map to null.

import type {
  Generation,
  VideoGeneration,
  ProductSceneGeneration,
  TranscriptionJob,
  LibraryItem,
  AvatarJob,
  VoiceAsset,
  AdminJobMonitorItem,
} from "@/lib/types";
import type { MediaObject, MediaType } from "@/lib/types/media";
import { emptyMediaMetadata } from "@/lib/types/media";

function filenameFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const clean = url.split("?")[0].split("#")[0];
    const parts = clean.split("/").filter(Boolean);
    return parts.length ? parts[parts.length - 1] : null;
  } catch {
    return null;
  }
}

function libraryTypeToMediaType(t: string | null | undefined): MediaType {
  switch (t) {
    case "video":
      return "video";
    case "transcript":
      return "transcript";
    case "scene":
      return "product_scene";
    default:
      return "image"; // upload, processed_asset, image, copy thumbnails, etc.
  }
}

export function generationToMedia(gen: Generation): MediaObject {
  return {
    mediaId: gen.id,
    type: "image",
    filename: filenameFromUrl(gen.file_url),
    storageUrl: gen.file_url ?? null,
    thumbnailUrl: gen.file_url ?? null,
    sourceWorkflow: gen.source_image_url ? "image_edit" : "text_to_image",
    projectId: gen.project_id ?? null,
    ownerId: null,
    createdAt: gen.created_at ?? null,
    provider: gen.provider ?? null,
    generationMode: gen.source_image_url ? "image_edit" : "text_to_image",
    prompt: gen.prompt ?? null,
    creditsCharged: gen.credits_cost ?? null,
    jobId: gen.id,
    status: gen.status ?? null,
    metadata: emptyMediaMetadata(),
  };
}

export function videoToMedia(video: VideoGeneration): MediaObject {
  const meta = emptyMediaMetadata();
  meta.duration = video.duration_seconds ?? null;
  return {
    mediaId: video.id,
    type: "video",
    filename: filenameFromUrl(video.result_url),
    storageUrl: video.result_url ?? null,
    thumbnailUrl: null, // backend does not produce video thumbnails yet
    sourceWorkflow: video.mode ?? null,
    projectId: video.project_id ?? null,
    ownerId: null,
    createdAt: video.created_at ?? null,
    provider: video.provider ?? null,
    generationMode: video.mode ?? null,
    prompt: video.prompt ?? null,
    creditsCharged: video.credits_cost ?? null,
    jobId: video.id,
    status: video.status ?? null,
    metadata: meta,
  };
}

export function transcriptToMedia(t: TranscriptionJob): MediaObject {
  const meta = emptyMediaMetadata();
  meta.language = t.detected_language ?? null;
  meta.transcriptText = t.transcript_text ?? null;
  meta.audioDuration = t.duration_seconds ?? null;
  meta.duration = t.duration_seconds ?? null;
  return {
    mediaId: t.id,
    type: "transcript",
    filename: t.source_filename ?? filenameFromUrl(t.source_video_url),
    storageUrl: t.source_video_url ?? null,
    thumbnailUrl: null,
    sourceWorkflow: "transcribe_video",
    projectId: t.project_id ?? null,
    ownerId: null,
    createdAt: t.created_at ?? null,
    provider: t.provider ?? null,
    generationMode: "transcribe_video",
    prompt: null,
    creditsCharged: t.credits_cost ?? null,
    jobId: t.id,
    status: t.status ?? null,
    metadata: meta,
  };
}

export function productSceneToMedia(scene: ProductSceneGeneration): MediaObject {
  return {
    mediaId: scene.id,
    type: "product_scene",
    filename: filenameFromUrl(scene.result_url),
    storageUrl: scene.result_url ?? null,
    thumbnailUrl: scene.result_url ?? null,
    sourceWorkflow: "product_scene",
    projectId: scene.project_id ?? null,
    ownerId: null,
    createdAt: scene.created_at ?? null,
    provider: null,
    generationMode: scene.mode ?? null,
    prompt: scene.prompt ?? null,
    creditsCharged: null,
    jobId: scene.id,
    status: scene.status ?? null,
    metadata: emptyMediaMetadata(),
  };
}

export function voiceToMedia(voice: VoiceAsset): MediaObject {
  return {
    mediaId: voice.id,
    type: "audio",
    filename: filenameFromUrl(voice.sample_file_path),
    storageUrl: voice.sample_file_path ?? null,
    thumbnailUrl: null,
    sourceWorkflow: "voice",
    projectId: null,
    ownerId: null,
    createdAt: voice.created_at ?? null,
    provider: voice.provider ?? null,
    generationMode: voice.voice_type ?? null,
    prompt: null,
    creditsCharged: null,
    jobId: voice.id,
    status: voice.status ?? null,
    metadata: emptyMediaMetadata(),
  };
}

export function avatarJobToMedia(job: AvatarJob): MediaObject | null {
  if (job.status === "failed" || !job.output_video_path) return null;
  const meta = emptyMediaMetadata();
  meta.width = job.avatar_width ?? null;
  meta.height = job.avatar_height ?? null;
  return {
    mediaId: job.id,
    type: "avatar_video",
    filename: filenameFromUrl(job.output_video_path),
    storageUrl: job.output_video_path ?? null,
    thumbnailUrl: null,
    sourceWorkflow: "avatar",
    projectId: null,
    ownerId: null,
    createdAt: job.created_at ?? null,
    provider: job.provider ?? null,
    generationMode: job.job_type ?? null,
    prompt: job.script_text ?? null,
    creditsCharged: job.credits_cost ?? null,
    jobId: job.id,
    status: job.status ?? null,
    metadata: meta,
  };
}

/** Map an Asset Library row (already a unified shape) into a MediaObject. */
export function assetToMedia(asset: LibraryItem): MediaObject {
  const type = libraryTypeToMediaType(asset.type);
  const meta = emptyMediaMetadata();
  if (type === "transcript") meta.transcriptText = asset.description ?? null;
  return {
    mediaId: asset.source_entity_id || asset.id,
    type,
    filename: filenameFromUrl(asset.asset_url ?? asset.thumbnail_url),
    storageUrl: asset.asset_url ?? null,
    thumbnailUrl: asset.thumbnail_url ?? asset.asset_url ?? null,
    sourceWorkflow: asset.source_entity_type ?? asset.type ?? null,
    projectId: asset.project_id ?? null,
    ownerId: null,
    createdAt: asset.created_at ?? null,
    provider: null,
    generationMode: null,
    prompt: asset.prompt ?? null,
    creditsCharged: null,
    jobId: asset.source_entity_id || null,
    status: asset.status ?? null,
    metadata: meta,
  };
}

/** Job Monitor row -> MediaObject. Returns null for failed jobs or jobs with no
 *  usable result, so failed jobs never render handoff actions. */
export function jobToMedia(job: AdminJobMonitorItem): MediaObject | null {
  if (job.status === "failed" || !job.result_url) return null;
  const type: MediaType =
    job.feature === "video"
      ? "video"
      : job.feature === "product_scene"
        ? "product_scene"
        : "image";
  return {
    mediaId: job.id,
    type,
    filename: filenameFromUrl(job.result_url),
    storageUrl: job.result_url ?? null,
    thumbnailUrl: type === "video" ? null : job.result_url ?? null,
    sourceWorkflow: job.feature ?? null,
    projectId: job.project_id ?? null,
    ownerId: job.user_id ?? null,
    createdAt: job.created_at ?? null,
    provider: null,
    generationMode: null,
    prompt: null,
    creditsCharged: null,
    jobId: job.id,
    status: job.status ?? null,
    metadata: emptyMediaMetadata(),
  };
}
