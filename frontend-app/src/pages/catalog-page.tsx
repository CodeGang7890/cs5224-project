import { Package } from "lucide-react";

import { SectionLayout } from "@/components/layout/section-layout";
import { catalogTabs } from "@/config/navigation";
import { faqKeys } from "@/features/faqs";
import { productKeys } from "@/features/products";
import { providerKeys, serviceKeys } from "@/features/services";

const REFRESH_KEYS = [
  productKeys.all,
  serviceKeys.all,
  providerKeys.all,
  faqKeys.all,
];

/** The Catalog section: products, services and FAQs (what the chat assistant sells and answers from). */
export function CatalogPage() {
  return (
    <SectionLayout
      icon={Package}
      accent="emerald"
      title="Catalog"
      description="What your business sells and answers questions about: the chat assistant works from these."
      tabs={catalogTabs}
      refreshKeys={REFRESH_KEYS}
    />
  );
}
