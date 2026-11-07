import { Moon, Sparkles, Sun } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router";

import { Button } from "@/components/ui/button";
import { APP_NAME } from "@/config/app";
import { navItems, paths } from "@/config/navigation";
import { WhatsAppReconnectAlert } from "@/features/whatsapp";
import { cn } from "@/lib/utils";
import { selectIsAuthenticated, useAuthStore } from "@/stores/auth-store";
import { useThemeStore } from "@/stores/theme-store";

import { AuthControls } from "./auth-controls";

export function RootLayout() {
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  // Login-only tabs are hidden while logged out (their URLs still show the login guard).
  const visibleItems = navItems.filter(
    (item) => isAuthenticated || !item.requiresAuth,
  );

  return (
    <div className="flex min-h-svh flex-col">
      <header className="bg-background sticky top-0 z-40 border-b">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link
            to={paths.home}
            className="flex shrink-0 items-center gap-2 font-semibold"
          >
            <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-sky-500 text-white shadow-sm">
              <Sparkles className="size-4" />
            </span>
            {APP_NAME}
          </Link>

          <nav className="-mx-1 flex flex-1 items-center gap-1 overflow-x-auto">
            {visibleItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === paths.home}
                className={({ isActive }) =>
                  cn(
                    "shrink-0 rounded-md px-3 py-1.5 text-sm transition-colors hover:text-foreground",
                    isActive
                      ? "bg-emerald-50 font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                      : "text-muted-foreground hover:bg-muted/60",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun /> : <Moon />}
            </Button>
            <AuthControls />
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-8">
        <WhatsAppReconnectAlert />
        <Outlet />
      </main>
    </div>
  );
}
