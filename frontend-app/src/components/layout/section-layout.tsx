import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router";

import type { SubTab } from "@/config/navigation";
import { cn } from "@/lib/utils";

interface SectionLayoutProps {
  title: string;
  description: ReactNode;
  tabs: SubTab[];
  /** Optional extra content per tab (by its `to`), e.g. a count badge. */
  badges?: Partial<Record<string, ReactNode>>;
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
}: SectionLayoutProps) {
  return (
    <section className="flex flex-col gap-6">
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <p className="text-muted-foreground text-sm">{description}</p>
      </div>

      <nav
        aria-label={title}
        className="-mx-1 flex gap-1 overflow-x-auto border-b px-1"
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                "-mb-px inline-flex shrink-0 items-center border-b-2 px-3 py-2 text-sm font-medium transition-colors",
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
