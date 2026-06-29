import { Clapperboard, ImageIcon } from "lucide-react";

import { assetUrl } from "@/lib/api";
import type { Generation } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  pending: "muted",
  failed: "destructive",
} as const;

export function GenerationCard({ generation }: { generation: Generation }) {
  const src = assetUrl(generation.file_url);

  return (
    <div className="group overflow-hidden rounded-lg border border-border bg-card transition-colors hover:border-primary/50">
      <div className="relative aspect-square w-full bg-background/60">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={generation.prompt}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            {generation.media_type === "video" ? (
              <Clapperboard className="h-8 w-8" />
            ) : (
              <ImageIcon className="h-8 w-8" />
            )}
          </div>
        )}
        <Badge
          variant={STATUS_VARIANT[generation.status]}
          className="absolute right-2 top-2 capitalize"
        >
          {generation.status}
        </Badge>
      </div>
      <div className="space-y-2 p-3">
        <p className="line-clamp-2 text-sm text-foreground/90">
          {generation.prompt}
        </p>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="capitalize">{generation.media_type}</span>
          <span className={cn(generation.credits_cost > 0 && "text-primary")}>
            {generation.credits_cost > 0 ? `-${generation.credits_cost} cr` : "-"}
          </span>
        </div>
        {generation.status === "failed" && generation.error ? (
          <p className="line-clamp-2 text-xs text-destructive">
            {generation.error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
