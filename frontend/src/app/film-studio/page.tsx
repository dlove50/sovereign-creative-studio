import { FilmStudioView } from "@/components/film-studio-view";
import { PageHeader } from "@/components/page-header";

export default function FilmStudioPage() {
  return (
    <>
      <PageHeader
        title="Film Studio"
        description="Create cinematic keyframes from product assets, then animate them into short clips."
      />
      <FilmStudioView />
    </>
  );
}
