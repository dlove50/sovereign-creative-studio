import { PageHeader } from "@/components/page-header";
import { AttributeEditorView } from "@/components/attribute-editor-view";

export default function AttributeEditorPage() {
  return (
    <>
      <PageHeader
        title="Attribute Editor"
        description="Edit a single attribute of a subject — pants, hair, face, shoes, garments — with automatic precise masks (human-parsing / GroundingDINO) or a manual mask."
      />
      <AttributeEditorView />
    </>
  );
}
