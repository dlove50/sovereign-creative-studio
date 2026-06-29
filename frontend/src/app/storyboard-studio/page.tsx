import { StoryboardStudioView } from "@/components/storyboard-studio-view";

export default function StoryboardStudioPage() {
  return (
    <main className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Storyboard Studio</h1>
        <p className="mt-2 text-muted-foreground">
          Plan multi-shot film sequences, continuity notes, and exportable shot lists.
        </p>
      </div>
      <StoryboardStudioView />
    </main>
  );
}
