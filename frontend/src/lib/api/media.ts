import type {
  AppStatus,
  AssetCollection,
  AssetCollectionInput,
  BrandKit,
  CampaignBuilderResult,
  CampaignPreset,
  CampaignResult,
  CampaignType,
  CopyGeneration,
  CopyTone,
  CopyType,
  CreativeBrief,
  CreativeBriefInput,
  CreativeDirectorResult,
  CollectionCampaignResult,
  Generation,
  ImageGenerationMode,
  ImageModeOption,
  ImagePresets,
  ImageProvider,
  LibraryItem,
  MaskPreviewResult,
  MediaType,
  ModelManagerStatus,
  ProductAsset,
  Production,
  ProductionInput,
  ProductionWorkspace,
  ProductSceneGeneration,
  ProductSceneMode,
  ProductScenePreset,
  Project,
  ProjectWorkspace,
  Shot,
  ShotInput,
  Storyboard,
  StoryboardInput,
  User,
  AuthStatus,
  AdminSetupStatus,
  AvatarAsset,
  VoiceAsset,
  AvatarJob,
  AvatarVoiceReadiness,
  IntegrationProvider,
  VideoGeneration,
  VideoMode,
  VideoModeOption,
  VideoMotionPreset,
  WorkflowCheck,
  WorkflowConfigUpdate,
  WorkflowConfigUpdateResult,
  WorkflowManagerModels,
  WorkflowManagerStatus,
  AdminCreditAdjustment,
  AdminCreditTransaction,
  AdminDashboard,
  AdminJobMonitor,
  AdminStorageReport,
  Backup,
  FamilyUser,
  FamilyUserCreate,
  FamilyUserUpdate,
  SandboxTopup,
  StaleJob,
  MarkStaleResult,
  TrashItem,
  TrashResult,
  StorageCleanupPlan,
  StorageCleanupResult,
  TopupPackage,
  TranscriptionJob,
  TranscriptionSummaryType,
  AudioMergeReadiness,
  AudioMergeOut,
  AudioPreviewOut,
  AudioTranscribeResult,
} from "../types";


import { API_BASE, downloadZip, formRequest, request, setActiveUserId } from "@/lib/api/core";

export const mediaApi = {
  listGenerations: () => request<Generation[]>("/api/generations"),
  getGeneration: (id: string) => request<Generation>(`/api/generations/${id}`),
  listGenerationModes: () => request<ImageModeOption[]>("/api/generations/modes"),
  listImagePresets: () => request<ImagePresets>("/api/generations/presets"),
  createGeneration: (input: {
    prompt: string;
    media_type: MediaType;
    project_id?: string | null;
    provider?: ImageProvider;
    mode?: ImageGenerationMode;
    source_image_url?: string | null;
    reference_image_urls?: string[];
    quality_preset?: string | null;
    style_preset?: string | null;
    image_mode?: string | null;
  }) =>
    request<Generation>("/api/generations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  uploadReferenceImage: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return formRequest<{ source_image_url: string; filename: string; checked: boolean }>("/api/generations/reference-upload", body);
  },
  uploadGenerationSource: (file: File, projectId?: string | null) => {
    const body = new FormData();
    if (projectId) body.append("project_id", projectId);
    body.append("file", file);
    return formRequest<{
      source_image_url: string;
      filename: string;
      project_id: string | null;
    }>("/api/generations/source-upload", body);
  },

  listAssets: (projectId?: string, readyFor?: "product_scenes") => {
    const params = new URLSearchParams();
    if (projectId) params.set("project_id", projectId);
    if (readyFor) params.set("ready_for", readyFor);
    const query = params.toString();
    return request<ProductAsset[]>(query ? `/api/assets?${query}` : "/api/assets");
  },
  getAsset: (id: string) => request<ProductAsset>(`/api/assets/${id}`),
  uploadAsset: (projectId: string, file: File) => {
    const body = new FormData();
    body.append("project_id", projectId);
    body.append("file", file);
    return formRequest<ProductAsset>("/api/assets/upload", body);
  },
  removeBackground: (id: string) =>
    request<ProductAsset>(`/api/assets/${id}/remove-background`, {
      method: "POST",
    }),
  uploadAssetMask: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return formRequest<ProductAsset>(`/api/assets/${id}/mask`, body);
  },

  listProductScenes: (projectId?: string) =>
    request<ProductSceneGeneration[]>(
      projectId
        ? `/api/product-scenes?project_id=${projectId}`
        : "/api/product-scenes",
    ),
  getProductScene: (id: string) =>
    request<ProductSceneGeneration>(`/api/product-scenes/${id}`),
  createProductScene: (input: {
    project_id: string;
    asset_id: string;
    prompt: string;
    preset: ProductScenePreset;
    mode?: ProductSceneMode;
    target_attribute?: string | null;
    brief_id?: string | null;
  }) =>
    request<ProductSceneGeneration>("/api/product-scenes", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  previewMask: (input: { asset_id: string; target_attribute: string }) =>
    request<MaskPreviewResult>("/api/product-scenes/mask-preview", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  saveSceneAsAsset: (sceneId: string) =>
    request<ProductAsset>(`/api/assets/from-scene/${sceneId}`, { method: "POST" }),

  listCopy: (projectId?: string) =>
    request<CopyGeneration[]>(
      projectId ? `/api/copy?project_id=${projectId}` : "/api/copy",
    ),
  getCopy: (id: string) => request<CopyGeneration>(`/api/copy/${id}`),
  createCopy: (input: {
    project_id: string;
    product_asset_id?: string | null;
    product_scene_id?: string | null;
    copy_type: CopyType;
    tone: CopyTone;
    audience?: string | null;
    prompt: string;
    brief_id?: string | null;
  }) =>
    request<CopyGeneration>("/api/copy", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  listVideos: (projectId?: string) =>
    request<VideoGeneration[]>(
      projectId ? `/api/videos?project_id=${projectId}` : "/api/videos",
    ),
  getVideo: (id: string) => request<VideoGeneration>(`/api/videos/${id}`),
  importVideos: (files: File[], projectId: string) => {
    const form = new FormData();
    form.append("project_id", projectId);
    files.forEach((file) => form.append("files", file));
    return formRequest<{ videos: VideoGeneration[]; errors: { filename: string; error: string }[] }>("/api/videos/import", form);
  },
  createVideo: (input: {
    project_id: string;
    product_scene_id?: string | null;
    source_image_url?: string | null;
    prompt: string;
    motion_preset: VideoMotionPreset;
    duration_seconds: number;
    mode?: VideoMode;
    provider?: "local_ltx" | "local_wan" | "local_h3" | "seedance_api";
    quality_preset?: string | null;
    brief_id?: string | null;
  }) =>
    request<VideoGeneration>("/api/videos", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listVideoModes: () => request<VideoModeOption[]>("/api/videos/modes"),
  exportVideoUrl: (id: string) => `${API_BASE}/api/exports/video/${id}`,

  listTranscriptions: (projectId?: string) =>
    request<TranscriptionJob[]>(
      projectId
        ? `/api/transcriptions?project_id=${projectId}`
        : "/api/transcriptions",
    ),
  getTranscription: (id: string) =>
    request<TranscriptionJob>(`/api/transcriptions/${id}`),
  createTranscription: (input: {
    project_id?: string | null;
    source_video_url?: string | null;
    file?: File | null;
  }) => {
    const body = new FormData();
    if (input.project_id) body.append("project_id", input.project_id);
    if (input.source_video_url) body.append("source_video_url", input.source_video_url);
    if (input.file) body.append("file", input.file);
    return formRequest<TranscriptionJob>("/api/transcriptions", body);
  },
  summarizeTranscription: (id: string, summaryType: TranscriptionSummaryType) =>
    request<TranscriptionJob>(`/api/transcriptions/${id}/summarize`, {
      method: "POST",
      body: JSON.stringify({ summary_type: summaryType }),
    }),
  transcriptionDownloadUrl: (id: string) =>
    `${API_BASE}/api/transcriptions/${id}/download`,

  transcribeAudio: (file: File | Blob) => {
    const fd = new FormData();
    fd.append("file", file, file instanceof File ? file.name : "voice-input.webm");
    return formRequest<AudioTranscribeResult>("/api/audio/transcribe", fd);
  },

  getAudioMergeReadiness: () =>
    request<AudioMergeReadiness>("/api/audio-merge/readiness"),
  previewVoice: (input: { tts_text: string; voice_id?: string | null }) =>
    request<AudioPreviewOut>("/api/audio-merge/preview", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  createAudioMerge: (input: { source_video_url: string; tts_text: string; voice_id?: string | null }) =>
    request<AudioMergeOut>("/api/audio-merge", {
      method: "POST",
      body: JSON.stringify(input),
    }),

};
