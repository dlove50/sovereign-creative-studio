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

export const projectsApi = {
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

};
