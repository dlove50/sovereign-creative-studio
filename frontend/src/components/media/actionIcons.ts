import {
  Archive,
  Clapperboard,
  Copy,
  Download,
  Film,
  Images,
  Info,
  Link as LinkIcon,
  Megaphone,
  Mic,
  PenLine,
  PersonStanding,
  Sparkles,
  Type,
  Wand2,
  type LucideIcon,
} from "lucide-react";

import type { ActionId } from "@/lib/types/media";

export const ACTION_ICONS: Record<ActionId, LucideIcon> = {
  animate_image: Clapperboard,
  edit_image: Wand2,
  product_scene: Megaphone,
  use_reference: Images,
  avatar_from_image: PersonStanding,
  upscale_video: Sparkles,
  transcribe_video: Type,
  video_to_video: Film,
  extend_video: Film,
  summarize_transcript: Sparkles,
  send_to_copy_studio: PenLine,
  copy_text: Copy,
  download_transcript: Download,
  use_for_avatar_voice: Mic,
  animate_scene: Clapperboard,
  download: Download,
  copy_url: LinkIcon,
  open_in_assets: Archive,
  view_details: Info,
};

export const STATUS_LABEL: Record<string, string> = {
  "setup-required": "Setup required",
  "coming-soon": "Coming soon",
  "needs-repair": "Workflow needs repair",
};
