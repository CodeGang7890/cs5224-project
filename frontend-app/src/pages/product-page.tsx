import { TabPage } from "@/components/common/tab-page";
import { ProductManager } from "@/features/products";

export function ProductPage() {
  return (
    <TabPage
      title="Products"
      section="Catalog"
      description="Manage your business's products."
    >
      <ProductManager />
    </TabPage>
  );
}
