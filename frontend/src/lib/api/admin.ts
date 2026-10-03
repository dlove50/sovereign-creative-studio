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
  listMovies: () => request<Movie[]>("/api/movies"),
  createMovie: (input: { title?: string; orientation?: MovieOrientation; scenes?: Partial<MovieScene>[] } = {}) =>
    request<Movie>("/api/movies", { method: "POST", body: JSON.stringify(input) }),
  getMovie: (id: string) => request<Movie>(`/api/movies/${encodeURIComponent(id)}`),
  updateMovie: (id: string, input: { title?: string; orientation?: MovieOrientation; scenes?: Partial<MovieScene>[] }) =>
    request<Movie>(`/api/movies/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(input) }),
  deleteMovie: (id: string) => request<void>(`/api/movies/${encodeURIComponent(id)}`, { method: "DELETE" }),
  renderMovie: (id: string) => request<Movie>(`/api/movies/${encodeURIComponent(id)}/render`, { method: "POST" }),
  improveDelivery: (script: string) =>
    request<{ title: string; script: string }>("/api/movies/improve-delivery", { method: "POST", body: JSON.stringify({ script }) }),
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
