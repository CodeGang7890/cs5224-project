import type { QueryKey } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router";

import { RefreshButton } from "@/components/common/refresh-button";
import type { SubTab } from "@/config/navigation";
import { cn } from "@/lib/utils";

import { type Accent, ACCENTS } from "./accents";
import { PageHeader } from "./page-header";

interface SectionLayoutProps {
  title: string;
  icon: LucideIcon;
  accent: Accent;
  description: ReactNode;
  tabs: SubTab[];
  /** Optional extra content per tab (by its `to`), e.g. a count badge. */
  badges?: Partial<Record<string, ReactNode>>;
  /** The section's data: shows a Refresh button (and when it was updated) for these queries. */
  refreshKeys?: QueryKey[];
}

/**
 * Layout route of a top-nav section with sub-tabs (Catalog, Orders, Chats): its heading, the
 * sub-tab links (each sub-tab is its own route, so its URL state stays separate), and the
 * current sub-tab's page.
 */
export function SectionLayout({
  title,
  icon,
  accent,
  description,
  tabs,
  badges,
  refreshKeys,
}: SectionLayoutProps) {
  return (
    <section className="flex flex-col gap-6">
      <PageHeader
        icon={icon}
        accent={accent}
        title={title}
        description={description}
        actions={refreshKeys && <RefreshButton queryKeys={refreshKeys} />}
      />

      <nav
        aria-label={title}
        // The bottom line is an inset shadow, not a border the tabs overlap with -mb-px: overflow-x-auto
        // also makes the bar scroll vertically, so that 1px overlap showed a vertical scrollbar.
        className="-mx-1 flex gap-1 overflow-x-auto overflow-y-hidden px-1 shadow-[inset_0_-1px_0_var(--border)]"
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                "inline-flex shrink-0 items-center border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? ACCENTS[accent].tab
                  : cn(
                      "text-muted-foreground border-transparent",
                      ACCENTS[accent].tabHover,
                    ),
              )
            }
          >
            {tab.label}
            {badges?.[tab.to]}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </section>
  );
}
