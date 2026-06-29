import { PageHeader } from "@/components/page-header";
import { ProductScenesView } from "@/components/product-scenes-view";

export default function ProductScenesPage() {
  return (
    <>
      <PageHeader
        title="Product Scenes"
        description="Turn uploaded product assets into lightweight ad scene concepts."
      />
      <ProductScenesView />
    </>
  );
}
