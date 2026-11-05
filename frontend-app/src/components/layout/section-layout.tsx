import type { QueryKey } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router";

import { RefreshButton } from "@/components/common/refresh-button";
import type { SubTab } from "@/config/navigation";
import { cn } from "@/lib/utils";

interface SectionLayoutProps {
  title: string;
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
  description,
  tabs,
  badges,
  refreshKeys,
}: SectionLayoutProps) {
  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="text-muted-foreground text-sm">{description}</p>
        </div>
        {refreshKeys && <RefreshButton queryKeys={refreshKeys} />}
      </div>

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
                  ? "border-primary text-foreground"
                  : "text-muted-foreground hover:text-foreground border-transparent",
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
