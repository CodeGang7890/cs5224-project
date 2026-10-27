import { SectionLayout } from "@/components/layout/section-layout";
import { catalogTabs } from "@/config/navigation";

/** The Catalog section: products, services and FAQs (what the chat assistant sells and answers from). */
export function CatalogPage() {
  return (
    <SectionLayout
      title="Catalog"
      description="What your business sells and answers questions about: the chat assistant works from these."
      tabs={catalogTabs}
    />
  );
}
