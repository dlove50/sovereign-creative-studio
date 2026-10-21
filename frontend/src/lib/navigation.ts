import {
  Activity,
  Archive,
  Brain,
  Boxes,
  Clapperboard,
  Coins,
  Cpu,
  Download,
  Film,
  Folder,
  Home,
  Mic,
  LayoutGrid,
  Palette,
  Images,
  ImageIcon,
  Layers3,
  Megaphone,
  Music2,
  PackagePlus,
  PenLine,
  PersonStanding,
  Plug,
  RadioTower,
  Rocket,
  ScanText,
  Scissors,
  SlidersHorizontal,
  ShieldCheck,
  Sparkle,
  Type,
  UserCircle,
  Users,
  Video,
  Wand2,
  type LucideIcon,
} from "lucide-react";

export type NavigationItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

export function isNavigationActive(href: string, pathname: string) {
  return href === "/" || href === "/admin" ? pathname === href : pathname.startsWith(href);
}

// The everyday creator path stays short and task-oriented.
export const CREATOR_NAV: NavigationItem[] = [
  { href: "/motion-studio", label: "Motion Studio", icon: Film },
  { href: "/apps", label: "App library", icon: LayoutGrid },
  { href: "/", label: "Home", icon: Home },
  { href: "/chain", label: "Quick Chain", icon: Wand2 },
  { href: "/movies", label: "Scene by scene", icon: Clapperboard },
  { href: "/videos", label: "Video Generator", icon: Video },
  { href: "/video-to-text", label: "Transcribe Video", icon: Type },
  { href: "/ocr-studio", label: "OCR Studio", icon: ScanText },
  { href: "/create", label: "Image Studio", icon: ImageIcon },
  { href: "/music-lab", label: "Music Lab", icon: Music2 },
  { href: "/performance", label: "Dual Performance", icon: Users },
  { href: "/enhance", label: "AI Enhance", icon: Sparkle },
  { href: "/voice-studio", label: "Voice Studio", icon: Mic },
  { href: "/inspiration", label: "Inspiration", icon: Sparkle },
  { href: "/avatars", label: "Avatars & Voices", icon: PersonStanding },
  { href: "/assets-library", label: "Assets", icon: Archive },
  { href: "/projects", label: "My Projects", icon: Folder },
  { href: "/credits", label: "Credits", icon: Coins },
  { href: "/profile", label: "Profile", icon: UserCircle },
];

export const ADMIN_NAV: NavigationItem[] = [
  { href: "/cloud-studio", label: "Cloud Studio", icon: Sparkle },
  { href: "/admin", label: "Admin Dashboard", icon: ShieldCheck },
  { href: "/admin/integrations", label: "Provider Integrations", icon: Plug },
  { href: "/product-scenes", label: "Product Scenes", icon: Megaphone },
  { href: "/copy-studio", label: "Copy Studio", icon: PenLine },
  { href: "/campaigns", label: "Campaigns", icon: Rocket },
  { href: "/campaign-builder", label: "Campaign Builder", icon: Boxes },
  { href: "/collections", label: "Asset Collections", icon: Layers3 },
  { href: "/creative-director", label: "Creative Director", icon: Brain },
  { href: "/film-studio", label: "Film Studio", icon: Film },
  { href: "/storyboard-studio", label: "Storyboard Studio", icon: Clapperboard },
  { href: "/production-studio", label: "Production Studio", icon: RadioTower },
  { href: "/export-studio", label: "Export Studio", icon: Download },
  { href: "/upload", label: "Upload", icon: PackagePlus },
  { href: "/attribute-editor", label: "Attribute Editor", icon: Scissors },
  { href: "/pose-studio", label: "Pose Studio", icon: PersonStanding },
  { href: "/gallery", label: "Gallery", icon: Images },
  { href: "/model-manager", label: "Model Manager", icon: Cpu },
  { href: "/workflow-manager", label: "Workflow Manager", icon: SlidersHorizontal },
  { href: "/status", label: "Status", icon: Activity },
];

// HeyGen-style shell: a slim icon rail for the main areas, and a "Create" fly-out
// for the ways to start a video. Every other studio lives in the Apps library.
export const RAIL_NAV: NavigationItem[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/avatars", label: "Avatar", icon: PersonStanding },
  { href: "/apps", label: "Apps", icon: Sparkle },
  { href: "/director", label: "Director", icon: Clapperboard },
  { href: "/music-lab", label: "Music", icon: Music2 },
  { href: "/performance", label: "Duet", icon: Users },
  { href: "/enhance", label: "Enhance", icon: Sparkle },
  { href: "/brand", label: "Brand", icon: Palette },
  { href: "/projects", label: "Projects", icon: Folder },
];

// The Avatar section's own pages, shown in a panel when the Avatar rail item is hovered.
export const AVATAR_NAV: NavigationItem[] = [
  { href: "/avatars", label: "Avatars", icon: PersonStanding },
  { href: "/avatars/looks", label: "Design a look", icon: Wand2 },
  { href: "/voices", label: "Voices", icon: Mic },
];

export const CREATE_NAV: NavigationItem[] = [
  { href: "/apps", label: "App library", icon: LayoutGrid },
  { href: "/motion-studio", label: "Motion Studio", icon: Film },
  { href: "/", label: "Home", icon: Home },
  { href: "/video-agent", label: "Video agent", icon: Sparkle },
  { href: "/movies", label: "Scene by scene", icon: Clapperboard },
  { href: "/chain", label: "Single scene", icon: Wand2 },
];
