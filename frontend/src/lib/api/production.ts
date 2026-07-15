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

export const productionApi = {
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
