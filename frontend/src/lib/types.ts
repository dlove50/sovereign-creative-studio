export type MediaType = "image" | "video";

export type GenerationStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "pending";

export interface User {
  id: string;
  email: string;
  username?: string | null;
  name: string;
  role: "owner_admin" | "family_user" | "guest";
  credits: number;
}

export interface AuthStatus {
  public_signup_enabled: boolean;
  requires_admin_approval: boolean;
}

export interface AdminSetupStatus {
  owner_exists: boolean;
  needs_admin_password: boolean;
  owner_name: string | null;
}

export interface AvatarAsset {
  id: string;
  name: string;
  avatar_type: string;
  source_file_path: string | null;
  thumbnail_path: string | null;
  status: string;
  provider: string;
  notes: string | null;
  created_at: string;
  group_id?: string | null;
  look_label?: string | null;
  default_voice_id?: string | null;
}

export interface VoiceAsset {
  id: string;
  name: string;
  voice_type: string;
  provider: string;
  sample_file_path: string | null;
  status: string;
  created_at: string;
}

export interface AvatarJob {
  id: string;
  avatar_id: string | null;
  voice_id: string | null;
  job_type: string;
  script_text: string | null;
  status: string;
  provider: string;
  avatar_preset: string | null;
  avatar_width: number | null;
  avatar_height: number | null;
  avatar_frames: number | null;
  avatar_steps: number | null;
  avatar_cfg: number | null;
  avatar_runtime_seconds: number | null;
  output_video_path: string | null;
  error_message: string | null;
  credits_cost: number;
  created_at: string;
  completed_at: string | null;
}

export interface ProviderReadiness {
  backend: string;
  ready: boolean;
  detail: string;
  comfy_reachable?: boolean | null;
  node_present?: boolean | null;
  workflow_present?: boolean | null;
  models_present?: boolean | null;
  missing?: string[];
}

export interface AvatarWanPreset {
  id: "tiny_test" | "low_vram" | "balanced" | "quality" | "portrait_480p" | "landscape_480p";
  label: string;
  description: string;
  width: number;
  height: number;
  frames: number;
  steps: number;
  cfg: number;
  warning: string | null;
  verified: boolean;
  default: boolean;
}

export interface AvatarVoiceReadiness {
  avatar: ProviderReadiness;
  voice: ProviderReadiness;
  greeting_text: string;
  avatar_enabled: boolean;
  voice_enabled: boolean;
  credits_per_avatar_video: number;
  credits_per_voice_generation: number;
  default_avatar_preset: string;
  avatar_presets: AvatarWanPreset[];
}

export interface IntegrationProvider {
  id: string;
  name: string;
  kind: string;
  note: string;
  enabled: boolean;
  configured: boolean;
  masked_key: string | null;
  last_test_result: string | null;
  config: Record<string, string>;
}

export type ImageProvider = "local_comfyui" | "openai_image_api";
export type ImageGenerationMode = "text_to_image" | "image_edit";

export interface ImageModeOption {
  id: ImageGenerationMode;
  name: string;
  description: string;
  source_required: boolean;
  providers: Record<
    ImageProvider,
    {
      available: boolean;
      cost: number;
      note: string | null;
    }
  >;
}

export interface ImageQualityPreset {
  id: string;
  label: string;
  description: string;
  recommended: boolean;
  is_default: boolean;
  ready: boolean;
  missing: string[];
  detail: string;
}

export interface ImageStylePreset {
  id: string;
  label: string;
  description: string;
}

export interface ImageMode {
  id: string;
  label: string;
  description: string;
  recommended_model: string;
  recommended_ready: boolean;
  effective_preset: string;
  effective_model: string;
  setup_note: string | null;
  subject_size_guidance: string | null;
}

export interface FaceRefineStatus {
  available: boolean;
  enabled: boolean;
  workflow_present: boolean;
  detail: string;
}

export interface ImagePresets {
  quality_presets: ImageQualityPreset[];
  style_presets: ImageStylePreset[];
  image_modes: ImageMode[];
  face_refine: FaceRefineStatus;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface BrandKit {
  brand_name: string | null;
  brand_voice: string | null;
  target_audience: string | null;
  primary_colors: string | null;
  style_keywords: string | null;
  negative_keywords: string | null;
  product_positioning: string | null;
  campaign_notes: string | null;
}

export interface CreativeBrief {
  id: string;
  project_id: string;
  title: string;
  campaign_goal: string | null;
  target_channels: string | null;
  deliverables: string | null;
  key_messages: string | null;
  creative_direction: string | null;
  reference_notes: string | null;
  selected_asset_ids: string[];
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CreativeBriefInput {
  title: string;
  campaign_goal?: string | null;
  target_channels?: string | null;
  deliverables?: string | null;
  key_messages?: string | null;
  creative_direction?: string | null;
  reference_notes?: string | null;
  selected_asset_ids?: string[];
  status?: string;
}

export interface Generation {
  id: string;
  prompt: string;
  media_type: MediaType;
  provider: ImageProvider;
  provider_task_id: string | null;
  provider_model: string | null;
  source_image_url: string | null;
  status: GenerationStatus;
  file_url: string | null;
  error: string | null;
  credits_cost: number;
  project_id: string | null;
  created_at: string;
  updated_at: string;
}

export type ProductAssetStatus =
  | "uploaded"
  | "processing"
  | "completed"
  | "failed";

export interface ProductAsset {
  id: string;
  project_id: string;
  filename: string;
  original_url: string;
  processed_url: string | null;
  mask_url: string | null;
  status: ProductAssetStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export type ProductScenePreset = "studio" | "luxury" | "outdoor" | "social ad";

export type ProductSceneMode =
  | "img2img"
  | "ipadapter"
  | "inpaint"
  | "segmented_composite"
  | "segmented_composite_polished"
  | "advertising_scene"
  | "fashion_editorial"
  | "creative_fashion_edit"
  | "creative_edit"
  | "character_reimagination"
  | "fashion_transformation"
  | "cinematic_scene_builder"
  | "clothing_style_edit"
  | "pose_edit"
  | "pose_stylized"
  | "film_scene"
  | "attribute_edit";

export interface MaskPreviewResult {
  mask_url: string | null;
  route: string;
}

export type ProductSceneStatus = "queued" | "running" | "completed" | "failed";

export interface ProductSceneGeneration {
  id: string;
  project_id: string;
  asset_id: string;
  prompt: string;
  preset: ProductScenePreset;
  mode: ProductSceneMode | null;
  target_attribute: string | null;
  status: ProductSceneStatus;
  result_url: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export type CopyType =
  | "product_description"
  | "instagram_caption"
  | "facebook_ad"
  | "tiktok_hook"
  | "seo_title";

export type CopyTone =
  | "luxury"
  | "friendly"
  | "bold"
  | "professional"
  | "playful";

export type CopyStatus = "queued" | "running" | "completed" | "failed";

export interface CopyGeneration {
  id: string;
  project_id: string;
  product_asset_id: string | null;
  product_scene_id: string | null;
  copy_type: CopyType;
  tone: CopyTone;
  audience: string | null;
  prompt: string;
  result_text: string | null;
  status: CopyStatus;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface CampaignPreset {
  id: string;
  name: string;
  description: string;
  scene_preset: string;
  scene_mode: string;
  scene_prompt_template: string;
  copy_type: CopyType;
  tone: CopyTone;
  audience_hint: string;
}

export interface CampaignResult {
  preset_id: string;
  scene_job: ProductSceneGeneration;
  copy_job: CopyGeneration;
}

export type VideoMotionPreset =
  | "slow_zoom"
  | "orbit"
  | "handheld"
  | "product_reveal"
  | "product_motion"
  | "cinematic_push"
  | "runway_walk"
  | "parallax"
  | "dolly_in"
  | "subtle_breathing";

export type VideoStatus = "queued" | "running" | "completed" | "failed";
export type VideoProvider = "local_ltx" | "local_wan" | "local_h3" | "seedance_api";

export type VideoMode =
  | "image_to_video"
  | "text_to_video"
  | "video_to_video"
  | "video_extension"
  | "video_upscale";

export type VideoQualityPreset =
  | "safe_preview"
  | "standard_local"
  | "best_local"
  | "image_to_video_best"
  | "h3_turbo"
  | "h3_full"
  | "h3_reference";

export interface VideoModeOption {
  id: VideoMode;
  name: string;
  description: string;
  source_required: boolean;
  available: boolean;
  backend: string;
  note: string | null;
  providers?: Record<
    VideoProvider,
    {
      available: boolean;
      cost: number;
      note: string | null;
    }
  >;
}

export interface VideoGeneration {
  id: string;
  project_id: string;
  product_scene_id: string | null;
  source_image_url: string;
  mode: VideoMode;
  provider: VideoProvider;
  provider_task_id: string | null;
  prompt: string;
  motion_preset: VideoMotionPreset;
  duration_seconds: number;
  quality_preset: VideoQualityPreset | null;
  status: VideoStatus;
  result_url: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  credits_cost: number;
}

export type TranscriptionStatus = "queued" | "running" | "completed" | "failed";
export type TranscriptionSummaryType =
  | "short_summary"
  | "bullet_summary"
  | "key_points"
  | "social_caption_ideas"
  | "scene_breakdown";

export interface TranscriptionJob {
  id: string;
  project_id: string | null;
  source_video_url: string;
  source_filename: string | null;
  status: TranscriptionStatus;
  transcript_text: string | null;
  summary_text: string | null;
  detected_language: string | null;
  duration_seconds: number | null;
  provider: string;
  model_name: string;
  error_message: string | null;
  credits_cost: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface VoiceOption {
  id: string;
  label: string;
  language: string;
  quality: string;
  is_default: boolean;
  ready: boolean;
}

export interface AudioMergeReadiness {
  ffmpeg: boolean;
  piper: boolean;
  ready: boolean;
  detail: string;
  piper_detail: string;
  default_voice: string | null;
  voices: VoiceOption[];
}

export interface AudioPreviewOut {
  audio_url: string;
  output_url: string;
  file_size_bytes: number;
  voice_id: string | null;
  status: string;
}

export interface AudioTranscribeResult {
  text: string;
  language: string | null;
  duration_seconds: number;
  error: string | null;
}

export interface AudioMergeOut {
  result_url: string;
  output_url: string;
  file_size_bytes: number;
  voice_id: string | null;
  status: string;
}

export interface Storyboard {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface StoryboardInput {
  title: string;
  description?: string | null;
  status?: string;
}

export interface Shot {
  id: string;
  storyboard_id: string;
  shot_number: number;
  duration_seconds: number;
  description: string | null;
  camera_notes: string | null;
  generation_prompt: string | null;
  product_scene_id: string | null;
  video_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ShotInput {
  shot_number?: number;
  duration_seconds?: number;
  description?: string | null;
  camera_notes?: string | null;
  generation_prompt?: string | null;
  product_scene_id?: string | null;
  video_id?: string | null;
}

export interface Production {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: string;
  storyboard_ids: string[];
  shot_ids: string[];
  video_ids: string[];
  export_urls: string[];
  created_at: string;
  updated_at: string;
}

export interface ProductionInput {
  title: string;
  description?: string | null;
  status?: string;
  storyboard_ids?: string[];
  shot_ids?: string[];
  video_ids?: string[];
}

export interface ProductionWorkspace {
  production: Production;
  storyboards: Storyboard[];
  shots: Shot[];
  videos: VideoGeneration[];
  counts: Record<string, number>;
}

export type LibraryItemType =
  | "upload"
  | "processed_asset"
  | "image"
  | "scene"
  | "copy"
  | "video"
  | "transcript"
  | "campaign"
  | "campaign_bundle";

export type CampaignType =
  | "product_launch"
  | "ecommerce"
  | "social_media"
  | "fashion_editorial"
  | "luxury_brand"
  | "custom";

export interface CampaignBundle {
  id: string;
  project_id: string;
  brief_id: string | null;
  selected_asset_id: string | null;
  title: string;
  campaign_type: string;
  status: string;
  scene_ids: string[];
  copy_ids: string[];
  video_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface CampaignBuilderResult {
  bundle_id: string;
  title: string;
  status: string;
  scene_count: number;
  copy_count: number;
  video_prompt_count: number;
  bundle: CampaignBundle;
}

export interface AssetCollection {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  asset_ids: string[];
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AssetCollectionInput {
  name: string;
  description?: string | null;
  asset_ids: string[];
  status?: string;
}

export interface CollectionCampaignResult {
  bundle_id: string;
  title: string;
  status: string;
  asset_count: number;
  scene_count: number;
  copy_count: number;
  video_prompt_count: number;
  bundle: CampaignBundle;
}

export interface LibraryItem {
  id: string;
  type: LibraryItemType;
  project_id: string | null;
  project_name: string | null;
  title: string;
  prompt: string | null;
  description: string | null;
  status: string;
  thumbnail_url: string | null;
  asset_url: string | null;
  download_url: string | null;
  created_at: string;
  source_entity_id: string;
  source_entity_type: string;
}

export interface ProjectWorkspace {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  brand_kit: BrandKit;
  creative_briefs: CreativeBrief[];
  campaign_bundles: CampaignBundle[];
  uploaded_assets: LibraryItem[];
  processed_assets: LibraryItem[];
  product_scenes: LibraryItem[];
  copy_generations: LibraryItem[];
  video_generations: LibraryItem[];
  campaign_items: LibraryItem[];
  counts_by_type: Record<LibraryItemType, number>;
  latest_activity_at: string;
}

export interface AppStatus {
  status: string;
  generator_backend: string;
  product_scene_backend: string;
  product_scene_model: string;
  product_scene_mode: string;
  copy_backend: string;
  video_backend: string;
  video_engine: string;
  transcription_backend: string;
  transcription_available: boolean;
  transcription_ffmpeg_available: boolean;
  transcription_faster_whisper_available: boolean;
  transcription_model_name: string;
  transcription_model_dir: string;
  transcription_device: string;
  transcription_compute_type: string;
  transcription_message: string | null;
  comfyui_base_url: string;
  comfyui_configured: boolean;
  comfyui_reachable: boolean;
  comfyui_error: string | null;
  openai_configured: boolean;
  storage_path: string;
  storage_writable: boolean;
}

export interface ComfyUIStatus {
  base_url: string;
  reachable: boolean;
  version: string | null;
  error: string | null;
}

export interface ModelCheck {
  name: string;
  category: string;
  installed: boolean;
  active: boolean;
  experimental: boolean;
  backend: string;
  source: string;
  details: string[];
  required_nodes: string[];
  required_models: string[];
  missing_nodes: string[];
  missing_models: string[];
}

export interface WorkflowCheck {
  name: string;
  kind: string;
  path: string;
  exists: boolean;
  active: boolean;
  experimental: boolean;
  details: string[];
  required_models: string[];
}

export interface ModelManagerStatus {
  status: string;
  current_config: Record<string, string>;
  video_generation_ready: string;
  comfyui: ComfyUIStatus;
  image_models: ModelCheck[];
  video_models: ModelCheck[];
  copy_models: ModelCheck[];
  support_models: ModelCheck[];
  workflows: WorkflowCheck[];
}

export interface WorkflowOption {
  id: string;
  name: string;
  available: boolean;
  active: boolean;
  experimental: boolean;
  backend: string | null;
  note: string | null;
}

export interface WorkflowManagerStatus {
  active_image_model: string;
  active_scene_workflow: string;
  active_scene_mode: string;
  active_video_backend: string;
  active_copy_backend: string;
  active_copy_model: string;
  generator_backend: string;
  product_scene_backend: string;
  comfyui_base_url: string;
  comfyui_reachable: boolean;
}

export interface WorkflowManagerModels {
  image_models: WorkflowOption[];
  scene_modes: WorkflowOption[];
  video_models: WorkflowOption[];
  copy_models: WorkflowOption[];
}

export interface WorkflowConfigUpdate {
  image_model?: string;
  scene_workflow?: string;
  scene_mode?: string;
  video_backend?: string;
  copy_backend?: string;
}

export interface WorkflowConfigUpdateResult {
  applied: Record<string, string>;
  warnings: string[];
  status: WorkflowManagerStatus;
}

export interface AdminUserSummary {
  id: string;
  display_name: string;
  email: string;
  role: "owner_admin" | "family_user" | "guest";
  status: "active" | "disabled";
  notes: string | null;
  credit_balance: number;
  created_at: string;
  updated_at: string;
  last_activity_at: string | null;
}

export type FamilyUser = AdminUserSummary;

export interface TopupPackage {
  id: string;
  name: string;
  credits: number;
  amount_cents: number;
  currency: string;
  price_display: string;
}

export type SandboxTopupStatus = "pending" | "completed" | "cancelled" | "failed";

export interface SandboxTopup {
  id: string;
  user_id: string;
  user_name: string;
  package_id: string;
  package_name: string;
  credits: number;
  amount_cents: number;
  amount_display: string;
  currency: string;
  status: SandboxTopupStatus;
  note: string | null;
  credit_transaction_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Backup {
  id: string;
  filename: string;
  created_at: string;
  size_bytes: number;
  download_url: string;
}

export type AdminJobStatus = "queued" | "running" | "completed" | "failed" | string;
export type AdminJobFeature = "base_generation" | "product_scene" | "copy" | "video" | string;

export interface AdminJobCounts {
  queued: number;
  running: number;
  completed: number;
  failed: number;
  total: number;
}

export interface AdminJobMonitorItem {
  id: string;
  feature: AdminJobFeature;
  status: AdminJobStatus;
  user_id: string;
  user_name: string | null;
  project_id: string | null;
  project_name: string | null;
  title: string | null;
  result_url: string | null;
  error: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface AdminJobMonitor {
  counts: AdminJobCounts;
  jobs: AdminJobMonitorItem[];
}

export interface StorageFolder {
  name: string;
  size_bytes: number;
  file_count: number;
}

export interface StorageLargestFile {
  path: string;
  size_bytes: number;
}

export interface AdminStorageReport {
  total_size_bytes: number;
  total_file_count: number;
  folders: StorageFolder[];
  largest_files: StorageLargestFile[];
}

export interface StorageCleanupCandidate {
  category: string;
  path: string;
  size_bytes: number;
}

export interface StorageCleanupPlan {
  candidates: StorageCleanupCandidate[];
  total_candidate_bytes: number;
  total_candidate_count: number;
  by_category: Record<string, number>;
  confirm_phrase: string;
  protected: string[];
}

export interface StorageCleanupResult {
  executed: boolean;
  deleted_count: number;
  freed_bytes: number;
  skipped: string[];
  message: string;
}

export interface StaleJob {
  id: string;
  feature: string;
  status: string;
  user_id: string;
  user_name: string | null;
  project_id: string | null;
  title: string | null;
  created_at: string;
  elapsed_minutes: number;
}

export interface MarkStaleResult {
  marked: number;
  action: string;
  note: string;
  refunds: number;
  details: string[];
}

export interface TrashItem {
  entity_type: string;
  entity_id: string;
  title: string | null;
  file_url: string | null;
  deleted_at: string;
}

export interface TrashResult {
  trashed: boolean;
  entity_type: string;
  entity_id: string;
  moved_files: string[];
  message: string;
}

export interface FamilyUserCreate {
  display_name: string;
  role: "owner_admin" | "family_user" | "guest";
  status?: "active" | "disabled";
  initial_credits?: number;
  notes?: string | null;
  email?: string | null;
}

export interface FamilyUserUpdate {
  display_name?: string;
  role?: "owner_admin" | "family_user" | "guest";
  status?: "active" | "disabled";
  notes?: string | null;
}

export interface AdminJobSummary {
  id: string;
  type: string;
  label: string;
  status: string;
  project_id: string | null;
  prompt: string | null;
  error: string | null;
  result_url: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AdminCreditTransaction {
  id: string;
  user_id: string;
  user_name: string;
  transaction_type:
    | "generation_charge"
    | "refund"
    | "manual_add"
    | "manual_remove"
    | "adjustment";
  amount: number;
  related_feature: string;
  related_id: string | null;
  status: "completed" | "failed" | "refunded" | "manual";
  reason: string;
  note: string | null;
  balance_after: number;
  generation_id: string | null;
  created_at: string;
}

export interface AdminCreditAdjustment {
  user_id: string;
  amount: number;
  note: string;
}

export interface AdminUsageSummary {
  id: string;
  user_id: string;
  user_name: string;
  feature: string;
  label: string;
  status: string;
  credits_charged: number;
  ledger_status: string;
  related_transaction_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AdminDashboard {
  title: string;
  mode: string;
  service_health: AppStatus;
  model_status: ModelManagerStatus;
  workflow_status: WorkflowManagerStatus;
  workflow_config: Record<string, string>;
  family_users: AdminUserSummary[];
  recent_jobs: AdminJobSummary[];
  failed_jobs: AdminJobSummary[];
  recent_credit_transactions: AdminCreditTransaction[];
  recent_usage: AdminUsageSummary[];
}

export interface CreativeDirectorRecommendation {
  category: string;
  recommendation: string;
  rationale: string;
  confidence: number;
}

export interface CreativeDirectorResult {
  project_id: string;
  brief_id: string | null;
  summary: string;
  recommendations: CreativeDirectorRecommendation[];
}

export type MovieOrientation = "portrait" | "landscape";
export type MovieStatus = "draft" | "rendering" | "completed" | "failed";
export interface MovieScene {
  id: string;
  avatar_id: string | null;
  tts_voice_id: string | null;
  script: string;
  status?: "draft" | "voice" | "video" | "completed" | "failed";
  error?: string | null;
}
export interface Movie {
  id: string;
  title: string;
  orientation: MovieOrientation;
  scenes: MovieScene[];
  status: MovieStatus;
  output_video_path: string | null;
  error_message: string | null;
  credits_estimate: number;
  created_at: string;
  updated_at: string;
}
