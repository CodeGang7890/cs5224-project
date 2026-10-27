import { TabPage } from "@/components/common/tab-page";
import { FaqManager } from "@/features/faqs";

export function FaqPage() {
  return (
    <TabPage
      title="FAQs"
      section="Catalog"
      description="Manage the frequently asked questions for your business."
    >
      <FaqManager />
    </TabPage>
  );
}
