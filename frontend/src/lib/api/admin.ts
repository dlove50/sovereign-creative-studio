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
  Movie,
  MovieOrientation,
  MovieScene,
  AudioMergeOut,
  AudioPreviewOut,
  AudioTranscribeResult,
} from "../types";


import { API_BASE, downloadZip, formRequest, request, setActiveUserId } from "@/lib/api/core";

export type InteractiveNode = { id: string; title: string; video_url: string; question?: string; body?: string; choices: { label: string; next: string; feedback?: string; is_correct?: boolean | null }[] };
export type InteractiveItem = { id: string; title: string; nodes: InteractiveNode[]; start_node_id: string | null; created_at: string; updated_at: string };

export const adminApi = {
  getMe: () => request<User>("/api/me"),
  // --- auth ---
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  authMe: () => request<User>("/api/auth/me"),
  signup: (input: { username: string; password: string; name?: string }) =>
    request<User>("/api/auth/signup", { method: "POST", body: JSON.stringify(input) }),
  login: async (input: { username: string; password: string }) => {
    // Logging in starts as the real account — never carry a stale "act as" target.
    setActiveUserId(null);
    return request<User>("/api/auth/login", { method: "POST", body: JSON.stringify(input) });
  },
  logout: async () => {
    setActiveUserId(null);
    return request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
  },
  adminSetupStatus: () => request<AdminSetupStatus>("/api/auth/setup-status"),
  setupAdminPassword: async (input: { password: string; confirm_password: string }) => {
    setActiveUserId(null);
    return request<User>("/api/auth/setup-admin-password", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  // --- avatars & voices (Phase 16A) ---
  avatarReadiness: () => request<AvatarVoiceReadiness>("/api/avatars/readiness"),
  listAvatars: () => request<AvatarAsset[]>("/api/avatars"),
  createPhotoAvatar: (form: FormData) => formRequest<AvatarAsset>("/api/avatars/photo", form),
  cloneRealPerson: (form: FormData) =>
    formRequest<{ avatar: AvatarAsset; voice_id: string | null; voice_note: string | null }>("/api/avatars/clone", form),
  updateAvatar: (id: string, patch: { name?: string; default_voice_id?: string; is_favorite?: boolean }) =>
    request<AvatarAsset>(`/api/avatars/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) }),
  voicePreview: (voiceId: string) =>
    request<{ url: string; kind: "synthesised" | "reference" }>(`/api/voice-library/preview?voice_id=${encodeURIComponent(voiceId)}`),
  deleteClonedVoice: (name: string) =>
    request<void>(`/api/voice-library/${encodeURIComponent(name)}`, { method: "DELETE" }),
  cloneVoice: (form: FormData) => formRequest<{ voice_id: string; name: string }>("/api/voice-library/clone", form),
  createLookFromVideo: (form: FormData) => formRequest<AvatarAsset>("/api/avatars/looks/from-video", form),
  createVideoAvatar: (form: FormData) => formRequest<AvatarAsset>("/api/avatars/video", form),
  writeAgentScript: (input: { prompt: string; seconds: number }) =>
    request<{ title: string; script: string; model: string; target_words: number }>("/api/video-agent/script", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  trashAvatarJob: (id: string) =>
    request<void>(`/api/avatar-jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  trashVideo: (id: string) =>
    request<void>(`/api/videos/${encodeURIComponent(id)}`, { method: "DELETE" }),
  createBatch: (input: {
    avatar_id: string; tts_voice_id?: string | null; orientation: MovieOrientation;
    rows: { title: string; script: string; avatar_id?: string; tts_voice_id?: string }[]; render: boolean;
    avatar_ids?: string[]; tts_voice_ids?: string[];
  }) => request<Movie[]>("/api/movies/batch", { method: "POST", body: JSON.stringify(input) }),
  listMovies: () => request<Movie[]>("/api/movies"),
  deleteGeneration: (id: string) => request<void>(`/api/generations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  deleteProject: (id: string) => request<void>(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),
  createMovie: (input: { title?: string; orientation?: MovieOrientation; scenes?: Partial<MovieScene>[] } = {}) =>
    request<Movie>("/api/movies", { method: "POST", body: JSON.stringify(input) }),
  getMovie: (id: string) => request<Movie>(`/api/movies/${encodeURIComponent(id)}`),
  updateMovie: (id: string, input: { title?: string; orientation?: MovieOrientation; scenes?: Partial<MovieScene>[] }) =>
    request<Movie>(`/api/movies/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(input) }),
  deleteMovie: (id: string) => request<void>(`/api/movies/${encodeURIComponent(id)}`, { method: "DELETE" }),
  renderMovie: (id: string) => request<Movie>(`/api/movies/${encodeURIComponent(id)}/render`, { method: "POST" }),
  improveDelivery: (script: string) =>
    request<{ title: string; script: string }>("/api/movies/improve-delivery", { method: "POST", body: JSON.stringify({ script }) }),
  makeAutoClips: (form: FormData) =>
    formRequest<{
      duration: number; method: "ai" | "fallback"; has_video: boolean;
      clips: { title: string; start: number; end: number; seconds: number; url: string }[];
    }>("/api/auto-clips", form),
  cleanSpeech: (form: FormData) =>
    formRequest<{
      output_url: string; filename: string; has_video: boolean; original_seconds: number; new_seconds: number;
      seconds_removed: number; pauses_removed: number; fillers_removed: number;
    }>("/api/speech-cleanup", form),
  extractKnowledge: (form: FormData) =>
    formRequest<{ name: string; text: string; truncated: boolean }>("/api/slides/extract-text", form),
  developerEndpoints: () =>
    request<{ count: number; interactive_docs: string; openapi: string; endpoints: {
      method: string; path: string; group: string; summary: string; description: string;
      path_params: string[]; query_params: string[]; body: "json" | "multipart" | null;
    }[] }>("/api/developers/endpoints"),
  assistantChat: (messages: { role: "user" | "assistant"; content: string }[]) =>
    request<{ reply: string; action: string; navigate_to: string | null; page: string | null }>(
      "/api/assistant/chat", { method: "POST", body: JSON.stringify({ messages }) }),
  saveScreenRecording: (form: FormData) =>
    formRequest<{ id: string; title: string; result_url: string; poster_url: string; duration_seconds: number; has_audio: boolean }>("/api/recordings", form),
  documentBrief: (form: FormData) =>
    formRequest<{ name: string; brief: string; source_chars: number; condensed: boolean; ocr_pages: number; suggested_slides: number }>("/api/slides/document-brief", form),
  addCaptions: (videoUrl: string) =>
    request<{ video_url: string; srt_url: string; captions: number }>("/api/captions", { method: "POST", body: JSON.stringify({ video_url: videoUrl }) }),
  slidesToMovie: (form: FormData) =>
    formRequest<{ movie_id: string; scenes: number; warnings: string[]; credits_estimate: number }>("/api/slides/to-movie", form),
  generatePresentation: (input: { prompt: string; slide_count: number; avatar_id: string; tts_voice_id: string; orientation: "portrait" | "landscape"; brand_project_id?: string | null }) =>
    request<{ movie_id: string; scenes: number; warnings: string[]; credits_estimate: number }>("/api/slides/generate", { method: "POST", body: JSON.stringify(input) }),
  translateLanguages: () => request<string[]>("/api/translate/languages"),
  translateVideo: (form: FormData) =>
    formRequest<{
      language: string; video_url: string; srt_url: string; vtt_url: string; has_video: boolean;
      segments: { start: number; end: number; text: string; original: string }[];
    }>("/api/translate", form),
  translationToMovie: (input: { title: string; lines: string[]; avatar_id: string; tts_voice_id: string | null; orientation: "portrait" | "landscape" }) =>
    request<{ movie_id: string; scenes: number; credits_estimate: number }>("/api/translate/to-movie", { method: "POST", body: JSON.stringify(input) }),
  listInteractive: () => request<InteractiveItem[]>("/api/interactive"),
  exportInteractiveScorm: (id: string) => downloadZip(`/api/interactive/${encodeURIComponent(id)}/export/scorm`, {}, "sovereign-lesson-scorm12.zip"),
  exportInteractivePackage: (id: string, format: "scorm12" | "scorm2004" | "xapi") =>
    downloadZip(`/api/interactive/${encodeURIComponent(id)}/export/${format}`, {}, `sovereign-lesson-${format}.zip`),
  getInteractive: (id: string) => request<InteractiveItem>(`/api/interactive/${encodeURIComponent(id)}`),
  listInteractiveClips: () => request<{ title: string; url: string }[]>("/api/interactive/clips"),
  createInteractive: (input: { title?: string; nodes?: InteractiveNode[]; start_node_id?: string | null }) =>
    request<InteractiveItem>("/api/interactive", { method: "POST", body: JSON.stringify(input) }),
  updateInteractive: (id: string, input: { title?: string; nodes?: InteractiveNode[]; start_node_id?: string | null }) =>
    request<InteractiveItem>(`/api/interactive/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(input) }),
  deleteInteractive: (id: string) =>
    request<void>(`/api/interactive/${encodeURIComponent(id)}`, { method: "DELETE" }),
  deleteAvatar: (id: string) =>
    request<void>(`/api/avatars/${encodeURIComponent(id)}`, { method: "DELETE" }),
  listVoices: () => request<VoiceAsset[]>("/api/voices"),
  createVoice: (input: { name: string; voice_type: string }) =>
    request<VoiceAsset>("/api/voices", { method: "POST", body: JSON.stringify(input) }),
  createGreeting: (input: { script_text?: string; avatar_id?: string; voice_id?: string }) =>
    request<AvatarJob>("/api/avatar-jobs/greeting", { method: "POST", body: JSON.stringify(input) }),
  generateVoiceGreeting: (input: { script_text?: string; tts_voice_id?: string } = {}) =>
    request<VoiceAsset>("/api/voices/greeting", { method: "POST", body: JSON.stringify(input) }),
  deleteVoice: (id: string) =>
    request<void>(`/api/voices/${encodeURIComponent(id)}`, { method: "DELETE" }),
  createTalkingAvatar: (input: { avatar_id: string; voice_id: string; script_text?: string; avatar_preset?: string }) =>
    request<AvatarJob>("/api/avatar-jobs/talking", { method: "POST", body: JSON.stringify(input) }),
  getAvatarJob: (id: string) => request<AvatarJob>(`/api/avatar-jobs/${id}`),
  listAvatarJobs: () => request<AvatarJob[]>("/api/avatar-jobs"),
  // --- admin integrations ---
  listIntegrations: () => request<IntegrationProvider[]>("/api/admin/integrations"),
  setIntegrationKey: (provider: string, apiKey: string) =>
    request<IntegrationProvider[]>(`/api/admin/integrations/${provider}/key`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  deleteIntegrationKey: (provider: string) =>
    request<IntegrationProvider[]>(`/api/admin/integrations/${provider}/key`, { method: "DELETE" }),
  setIntegrationEnabled: (provider: string, enabled: boolean) =>
    request<IntegrationProvider[]>(`/api/admin/integrations/${provider}/enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  setIntegrationConfig: (provider: string, config: Record<string, string>) =>
    request<IntegrationProvider[]>(`/api/admin/integrations/${provider}/config`, {
      method: "POST",
      body: JSON.stringify(config),
    }),
  testIntegration: (provider: string) =>
    request<{ provider: string; result: string }>(`/api/admin/integrations/${provider}/test`, {
      method: "POST",
    }),
  getStatus: () => request<AppStatus>("/api/status"),
  getModelStatus: () => request<ModelManagerStatus>("/api/models/status"),
  getAdminDashboard: () => request<AdminDashboard>("/api/admin/dashboard"),
  getAdminJobs: (params?: { status?: string; feature?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.feature) search.set("feature", params.feature);
    if (params?.limit) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<AdminJobMonitor>(`/api/admin/jobs${query ? `?${query}` : ""}`);
  },
  getStaleJobs: (thresholdMinutes = 60) =>
    request<StaleJob[]>(`/api/admin/jobs/stale?threshold_minutes=${thresholdMinutes}`),
  markStaleJobs: (input: {
    action: "cancelled" | "failed";
    threshold_minutes?: number;
    ids?: { feature: string; id: string }[];
  }) =>
    request<MarkStaleResult>("/api/admin/jobs/mark-stale", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  dismissJob: (feature: string, id: string) =>
    request<{ dismissed: boolean }>("/api/admin/jobs/dismiss", {
      method: "POST",
      body: JSON.stringify({ feature, id }),
    }),
  trashAsset: (input: {
    entity_type: "video" | "scene" | "generation" | "upload";
    entity_id: string;
    force_original?: boolean;
    force_referenced?: boolean;
  }) =>
    request<TrashResult>("/api/admin/trash", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listTrash: () => request<TrashItem[]>("/api/admin/trash"),
  restoreTrash: (entity_type: string, entity_id: string) =>
    request<TrashResult>("/api/admin/trash/restore", {
      method: "POST",
      body: JSON.stringify({ entity_type, entity_id }),
    }),
  getAdminStorage: () => request<AdminStorageReport>("/api/admin/storage"),
  createStorageCleanupPlan: () =>
    request<StorageCleanupPlan>("/api/admin/storage/cleanup/plan", {
      method: "POST",
    }),
  executeStorageCleanup: (confirm: string) =>
    request<StorageCleanupResult>("/api/admin/storage/cleanup/execute", {
      method: "POST",
      body: JSON.stringify({ confirm }),
    }),
  listFamilyUsers: () => request<FamilyUser[]>("/api/admin/family-users"),
  createFamilyUser: (input: FamilyUserCreate) =>
    request<FamilyUser>("/api/admin/family-users", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateFamilyUser: (id: string, input: FamilyUserUpdate) =>
    request<FamilyUser>(`/api/admin/family-users/${id}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  disableFamilyUser: (id: string) =>
    request<FamilyUser>(`/api/admin/family-users/${id}/disable`, {
      method: "POST",
    }),
  reactivateFamilyUser: (id: string) =>
    request<FamilyUser>(`/api/admin/family-users/${id}/reactivate`, {
      method: "POST",
    }),
  listCreditTransactions: (params?: {
    user_id?: string;
    transaction_type?: string;
    status?: string;
    limit?: number;
  }) => {
    const search = new URLSearchParams();
    if (params?.user_id) search.set("user_id", params.user_id);
    if (params?.transaction_type) search.set("transaction_type", params.transaction_type);
    if (params?.status) search.set("status", params.status);
    if (params?.limit) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<AdminCreditTransaction[]>(
      `/api/admin/credits/transactions${query ? `?${query}` : ""}`,
    );
  },
  addCredits: (input: AdminCreditAdjustment) =>
    request<FamilyUser>("/api/admin/credits/add", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  removeCredits: (input: AdminCreditAdjustment) =>
    request<FamilyUser>("/api/admin/credits/remove", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listTopupPackages: () =>
    request<TopupPackage[]>("/api/admin/topups/packages"),
  listTopups: () => request<SandboxTopup[]>("/api/admin/topups"),
  createTopup: (input: { user_id: string; package_id: string; note?: string | null }) =>
    request<SandboxTopup>("/api/admin/topups/create", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  completeTopup: (id: string) =>
    request<SandboxTopup>(`/api/admin/topups/${id}/complete`, { method: "POST" }),
  cancelTopup: (id: string) =>
    request<SandboxTopup>(`/api/admin/topups/${id}/cancel`, { method: "POST" }),
  listBackups: () => request<Backup[]>("/api/admin/backups"),
  createBackup: () => request<Backup>("/api/admin/backups/create", { method: "POST" }),
  deleteBackup: (id: string) =>
    request<void>(`/api/admin/backups/${id}`, { method: "DELETE" }),
  backupDownloadUrl: (id: string) =>
    `${API_BASE}/api/admin/backups/${id}/download`,
  refundCreditTransaction: (id: string, note?: string) =>
    request<AdminCreditTransaction>(`/api/admin/credits/transactions/${id}/refund`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  resetAdminSafeWorkflowDefaults: () =>
    request<WorkflowConfigUpdateResult>("/api/admin/workflow/reset-safe-defaults", {
      method: "POST",
    }),

  getWorkflowManagerStatus: () =>
    request<WorkflowManagerStatus>("/api/workflow-manager/status"),
  getWorkflowManagerModels: () =>
    request<WorkflowManagerModels>("/api/workflow-manager/models"),
  getWorkflowManagerWorkflows: () =>
    request<WorkflowCheck[]>("/api/workflow-manager/workflows"),
  updateWorkflowConfig: (changes: WorkflowConfigUpdate) =>
    request<WorkflowConfigUpdateResult>("/api/workflow-manager/config", {
      method: "PUT",
      body: JSON.stringify(changes),
    }),
};
