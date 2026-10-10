import type {
  AppStatus,
  AssetCollection,
  AssetCollectionInput,
  BrandKit,
  BrandVisuals,
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


import { downloadZip, formRequest, request, requestVoid, setActiveUserId } from "@/lib/api/core";

export const projectsApi = {
  listLibrary: (projectId?: string) =>
    request<LibraryItem[]>(
      projectId ? `/api/library?project_id=${projectId}` : "/api/library",
    ),

  listCinematicOutputs: () => request<{id: string; plan_id: string; revision: number; title: string; result_url: string; status: string; created_at: string}[]>("/api/projects/cinematic-outputs"),
  listProjects: () => request<Project[]>("/api/projects"),
  getProjectWorkspace: (id: string) =>
    request<ProjectWorkspace>(`/api/projects/${id}/workspace`),
  getBrandKit: (id: string) =>
    request<BrandKit>(`/api/projects/${id}/brand-kit`),
  getBrandVisuals: (id: string) => request<BrandVisuals>(`/api/projects/${encodeURIComponent(id)}/brand-visuals`),
  importBrandWebsite: (id: string, source: string) =>
    request<BrandVisuals & {imported_colors: number; imported_fonts: number}>(`/api/projects/${encodeURIComponent(id)}/brand-visuals/import-site?${new URLSearchParams({source_url:source})}`, {method:"POST"}),
  updateBrandVisuals: (id: string, spec: Pick<BrandVisuals, "colors" | "fonts">) =>
    request<BrandVisuals>(`/api/projects/${encodeURIComponent(id)}/brand-visuals`, {method:"PUT", body:JSON.stringify(spec)}),
  uploadBrandImage: (id: string, kind: "logos" | "assets", file: File) => {
    const form = new FormData(); form.append("file", file);
    return formRequest<BrandVisuals>(`/api/projects/${encodeURIComponent(id)}/brand-assets?kind=${kind}`, form);
  },
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
    await requestVoid(`/api/projects/${projectId}/collections/${collectionId}`, { method: "DELETE" });
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
    await requestVoid(`/api/projects/${projectId}/briefs/${briefId}`, { method: "DELETE" });
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

  deleteBrandAsset: async (projectId: string, kind: "logos" | "assets", name: string) => {
    await requestVoid(`/api/projects/${encodeURIComponent(projectId)}/brand-assets/${encodeURIComponent(name)}?kind=${kind}`, { method: "DELETE" });
  },

  fetchRemoteImage: async (projectId: string, kind: "logos" | "assets", imageUrl: string) =>
    request<BrandVisuals>(
      `/api/projects/${encodeURIComponent(projectId)}/brand-assets/fetch-url?kind=${kind}&image_url=${encodeURIComponent(imageUrl)}`,
      { method: "POST" },
    ),

};
