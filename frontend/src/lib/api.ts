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
} from "./types";

// Default to a relative base so the browser calls the frontend origin and the
// Next rewrite proxies to the backend — this keeps the session cookie first-party.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

/** Turn a backend-relative file URL (e.g. "/storage/x.svg") into an absolute one. */
export function assetUrl(fileUrl: string | null): string | null {
  if (!fileUrl) return null;
  return fileUrl.startsWith("http") ? fileUrl : `${API_BASE}${fileUrl}`;
}

// Local "acting as" family user (attribution only — not authentication).
const ACTIVE_USER_KEY = "scs_active_user_id";
const ACTIVE_USER_HEADER = "X-SCS-Family-User-Id";

export function getActiveUserId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_USER_KEY);
}

export function setActiveUserId(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id) window.localStorage.setItem(ACTIVE_USER_KEY, id);
  else window.localStorage.removeItem(ACTIVE_USER_KEY);
}

function activeUserHeaders(): Record<string, string> {
  const id = getActiveUserId();
  return id ? { [ACTIVE_USER_HEADER]: id } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    credentials: "include",
    ...init,
    // Headers last so the active-user header is never clobbered by `init`.
    headers: {
      "Content-Type": "application/json",
      ...activeUserHeaders(),
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function formRequest<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body,
    cache: "no-store",
    credentials: "include",
    headers: activeUserHeaders(),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const payload = await res.json();
      if (payload?.detail) detail = payload.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
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
  listVoices: () => request<VoiceAsset[]>("/api/voices"),
  createVoice: (input: { name: string; voice_type: string }) =>
    request<VoiceAsset>("/api/voices", { method: "POST", body: JSON.stringify(input) }),
  createGreeting: (input: { script_text?: string; avatar_id?: string; voice_id?: string }) =>
    request<AvatarJob>("/api/avatar-jobs/greeting", { method: "POST", body: JSON.stringify(input) }),
  generateVoiceGreeting: (input: { script_text?: string } = {}) =>
    request<VoiceAsset>("/api/voices/greeting", { method: "POST", body: JSON.stringify(input) }),
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
  listLibrary: (projectId?: string) =>
    request<LibraryItem[]>(
      projectId ? `/api/library?project_id=${projectId}` : "/api/library",
    ),

  listProjects: () => request<Project[]>("/api/projects"),
  getProjectWorkspace: (id: string) =>
    request<ProjectWorkspace>(`/api/projects/${id}/workspace`),
  getBrandKit: (id: string) =>
    request<BrandKit>(`/api/projects/${id}/brand-kit`),
  updateBrandKit: (id: string, input: BrandKit) =>
    request<BrandKit>(`/api/projects/${id}/brand-kit`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),

  createCampaign: (
    projectId: string,
    input: { brief_id: string; asset_id: string; campaign_type: CampaignType },
  ) =>
    request<CampaignBuilderResult>(
      `/api/projects/${projectId}/campaign-builder`,
      { method: "POST", body: JSON.stringify(input) },
    ),

  listCollections: (projectId: string) =>
    request<AssetCollection[]>(`/api/projects/${projectId}/collections`),
  createCollection: (projectId: string, input: AssetCollectionInput) =>
    request<AssetCollection>(`/api/projects/${projectId}/collections`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateCollection: (
    projectId: string,
    collectionId: string,
    input: Partial<AssetCollectionInput>,
  ) =>
    request<AssetCollection>(
      `/api/projects/${projectId}/collections/${collectionId}`,
      { method: "PUT", body: JSON.stringify(input) },
    ),
  deleteCollection: async (projectId: string, collectionId: string) => {
    const res = await fetch(
      `${API_BASE}/api/projects/${projectId}/collections/${collectionId}`,
      { method: "DELETE", cache: "no-store" },
    );
    if (!res.ok) throw new Error("Could not delete collection");
  },
  createCollectionCampaign: (
    projectId: string,
    collectionId: string,
    input: {
      collection_id: string;
      brief_id: string;
      campaign_type: CampaignType;
    },
  ) =>
    request<CollectionCampaignResult>(
      `/api/projects/${projectId}/collections/${collectionId}/campaign`,
      { method: "POST", body: JSON.stringify(input) },
    ),

  listBriefs: (projectId: string) =>
    request<CreativeBrief[]>(`/api/projects/${projectId}/briefs`),
  createBrief: (projectId: string, input: CreativeBriefInput) =>
    request<CreativeBrief>(`/api/projects/${projectId}/briefs`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateBrief: (
    projectId: string,
    briefId: string,
    input: Partial<CreativeBriefInput>,
  ) =>
    request<CreativeBrief>(`/api/projects/${projectId}/briefs/${briefId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  deleteBrief: async (projectId: string, briefId: string) => {
    const res = await fetch(
      `${API_BASE}/api/projects/${projectId}/briefs/${briefId}`,
      { method: "DELETE", cache: "no-store" },
    );
    if (!res.ok) throw new Error("Could not delete brief");
  },
  getCreativeDirectorRecommendations: (input: {
    project_id: string;
    brief_id?: string | null;
  }) =>
    request<CreativeDirectorResult>("/api/creative-director/recommendations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  createProject: (name: string, description?: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, description: description || null }),
    }),

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
    quality_preset?: string | null;
    style_preset?: string | null;
    image_mode?: string | null;
  }) =>
    request<Generation>("/api/generations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
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
  createVideo: (input: {
    project_id: string;
    product_scene_id?: string | null;
    source_image_url?: string | null;
    prompt: string;
    motion_preset: VideoMotionPreset;
    duration_seconds: number;
    mode?: VideoMode;
    provider?: "local_ltx" | "seedance_api";
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

  listStoryboards: (projectId: string) =>
    request<Storyboard[]>(`/api/projects/${projectId}/storyboards`),
  createStoryboard: (projectId: string, input: StoryboardInput) =>
    request<Storyboard>(`/api/projects/${projectId}/storyboards`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateStoryboard: (
    projectId: string,
    storyboardId: string,
    input: Partial<StoryboardInput>,
  ) =>
    request<Storyboard>(`/api/projects/${projectId}/storyboards/${storyboardId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  deleteStoryboard: async (projectId: string, storyboardId: string) => {
    const res = await fetch(
      `${API_BASE}/api/projects/${projectId}/storyboards/${storyboardId}`,
      { method: "DELETE", cache: "no-store" },
    );
    if (!res.ok) throw new Error("Could not delete storyboard");
  },
  exportStoryboardUrl: (projectId: string, storyboardId: string) =>
    `${API_BASE}/api/projects/${projectId}/storyboards/${storyboardId}/export`,
  listShots: (storyboardId: string) =>
    request<Shot[]>(`/api/storyboards/${storyboardId}/shots`),
  createShot: (storyboardId: string, input: ShotInput) =>
    request<Shot>(`/api/storyboards/${storyboardId}/shots`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateShot: (storyboardId: string, shotId: string, input: Partial<ShotInput>) =>
    request<Shot>(`/api/storyboards/${storyboardId}/shots/${shotId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  deleteShot: async (storyboardId: string, shotId: string) => {
    const res = await fetch(
      `${API_BASE}/api/storyboards/${storyboardId}/shots/${shotId}`,
      { method: "DELETE", cache: "no-store" },
    );
    if (!res.ok) throw new Error("Could not delete shot");
  },

  listProductions: (projectId: string) =>
    request<Production[]>(`/api/projects/${projectId}/productions`),
  createProduction: (projectId: string, input: ProductionInput) =>
    request<Production>(`/api/projects/${projectId}/productions`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getProduction: (projectId: string, productionId: string) =>
    request<ProductionWorkspace>(
      `/api/projects/${projectId}/productions/${productionId}`,
    ),
  updateProduction: (
    projectId: string,
    productionId: string,
    input: Partial<ProductionInput>,
  ) =>
    request<Production>(`/api/projects/${projectId}/productions/${productionId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  deleteProduction: async (projectId: string, productionId: string) => {
    const res = await fetch(
      `${API_BASE}/api/projects/${projectId}/productions/${productionId}`,
      { method: "DELETE", cache: "no-store" },
    );
    if (!res.ok) throw new Error("Could not delete production");
  },
  downloadProductionPackage: async (projectId: string, productionId: string) => {
    await downloadZip(
      `/api/projects/${projectId}/productions/${productionId}/export`,
      {},
      "production-package.zip",
    );
  },

  listPresets: () => request<CampaignPreset[]>("/api/presets"),
  createCampaignFromPreset: (input: {
    project_id: string;
    asset_id: string;
    preset_id: string;
    product_name?: string | null;
    brief_id?: string | null;
  }) =>
    request<CampaignResult>("/api/campaigns/from-preset", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  // Export downloads. Scene/copy are GETs, so a plain link works; the bundle is
  // a POST, so it's fetched and saved as a blob.
  exportSceneUrl: (id: string) => `${API_BASE}/api/exports/scene/${id}`,
  exportCopyUrl: (id: string) => `${API_BASE}/api/exports/copy/${id}`,
  downloadCampaignBundle: async (input: {
    scene_id?: string | null;
    copy_id?: string | null;
  }) => {
    const res = await fetch(`${API_BASE}/api/exports/campaign-bundle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json())?.detail ?? detail;
      } catch {
        /* non-JSON */
      }
      throw new Error(detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "campaign-bundle.zip";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  downloadSocialBundle: async (input: {
    project_id: string;
    brief_id?: string | null;
    campaign_bundle_id?: string | null;
    platforms: string[];
  }) => {
    await downloadZip("/api/exports/social-bundle", input, "social-bundle.zip");
  },
  downloadMarketingBundle: async (input: {
    project_id: string;
    brief_id?: string | null;
    campaign_bundle_id?: string | null;
    platforms?: string[];
  }) => {
    await downloadZip(
      "/api/exports/marketing-bundle",
      { ...input, platforms: input.platforms ?? [] },
      "marketing-bundle.zip",
    );
  },
};

async function downloadZip(path: string, input: unknown, filename: string) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* non-JSON */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
