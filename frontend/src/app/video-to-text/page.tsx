import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { VideoToTextView } from "@/components/video-to-text-view";

export default function VideoToTextPage() {
  return (
    <>
      <PageHeader
        title="Transcribe Video"
        description="Upload a video and turn speech into a transcript or summary."
      />
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <p className="text-sm text-muted-foreground">
          Looking to create a video from text? Go to Text to Video.
        </p>
        <Link
          href="/videos?mode=text_to_video"
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-muted"
        >
          Text to Video <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
      <VideoToTextView />
    </>
  );
}
