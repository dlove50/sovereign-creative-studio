import { InteractiveEditorView } from "@/components/interactive/interactive-editor-view";

export default function InteractiveEditorPage({ params }: { params: { id: string } }) {
  return <InteractiveEditorView key={params.id} itemId={params.id} />;
}
