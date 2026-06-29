"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
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
  Images,
  ImageIcon,
  Layers3,
  Megaphone,
  PackagePlus,
  PenLine,
  PersonStanding,
  Plug,
  RadioTower,
  Rocket,
  Scissors,
  Sparkle,
  SlidersHorizontal,
  Sparkles,
  ShieldCheck,
  Type,
  UserCircle,
  Video,
  Wand2,
} from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { isAuthRoute } from "@/lib/routes";
import { ActiveUserSelector } from "@/components/active-user-selector";

// Simple, creator-friendly navigation shown to every logged-in user.
const CREATOR_NAV = [
  { href: "/", label: "Home", icon: Home },
  { href: "/chain", label: "Quick Chain", icon: Wand2 },
  { href: "/videos", label: "Video Generator", icon: Video },
  { href: "/video-to-text", label: "Transcribe Video", icon: Type },
  { href: "/create", label: "Image Studio", icon: ImageIcon },
  { href: "/inspiration", label: "Inspiration", icon: Sparkle },
  { href: "/avatars", label: "Avatars & Voices", icon: PersonStanding },
  { href: "/assets-library", label: "Assets", icon: Archive },
  { href: "/projects", label: "My Projects", icon: Folder },
  { href: "/credits", label: "Credits", icon: Coins },
  { href: "/profile", label: "Profile", icon: UserCircle },
];

// Advanced + admin tools — only shown to owner/admin so the creator view stays clean.
const ADMIN_NAV = [
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

function NavLink({
  href,
  label,
  icon: Icon,
  pathname,
}: {
  href: string;
  label: string;
  icon: typeof Home;
  pathname: string;
}) {
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-primary/15 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const onAuthRoute = isAuthRoute(pathname);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    // Admin tools are gated on the real session identity (authMe), independent of
    // any "act as" selection, so the owner/admin always keeps admin navigation.
    api
      .authMe()
      .then((u) => setIsAdmin(u.role === "owner_admin"))
      .catch(() => setIsAdmin(false));
  }, [pathname]);

  // Clean logged-out layout on auth/setup screens.
  if (onAuthRoute) return null;

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-card/40 px-4 py-6 md:flex">
      <Link href="/" className="mb-8 flex items-center gap-2 px-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Sparkles className="h-5 w-5" />
        </span>
        <span className="text-sm font-semibold leading-tight">
          Sovereign
          <span className="block text-xs font-normal text-muted-foreground">
            Creative Studio
          </span>
        </span>
      </Link>

      <nav className="flex flex-col gap-1">
        {CREATOR_NAV.map((item) => (
          <NavLink key={item.href} {...item} pathname={pathname} />
        ))}
      </nav>

      {isAdmin ? (
        <nav className="mt-6 flex flex-col gap-1 border-t border-border pt-4">
          <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Admin &amp; Advanced
          </p>
          {ADMIN_NAV.map((item) => (
            <NavLink key={item.href} {...item} pathname={pathname} />
          ))}
        </nav>
      ) : null}

      <div className="mt-auto space-y-3 pt-3">
        {/* Family-user (acting as) selector is an admin tool — hidden from normal users. */}
        {isAdmin ? <ActiveUserSelector /> : null}
      </div>
    </aside>
  );
}
