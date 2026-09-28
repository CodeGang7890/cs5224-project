import { Moon, Sun } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router'

import { Button } from '@/components/ui/button'
import { APP_NAME } from '@/config/app'
import { navItems, paths } from '@/config/navigation'
import { ProfileDialog } from '@/features/profile'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/stores/theme-store'

export function RootLayout() {
  const theme = useThemeStore((state) => state.theme)
  const toggleTheme = useThemeStore((state) => state.toggleTheme)

  return (
    <div className="flex min-h-svh flex-col">
      <header className="bg-background sticky top-0 z-40 border-b">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link to={paths.home} className="shrink-0 font-semibold">
            {APP_NAME}
          </Link>

          <nav className="-mx-1 flex flex-1 items-center gap-1 overflow-x-auto">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === paths.home}
                className={({ isActive }) =>
                  cn(
                    'shrink-0 rounded-md px-3 py-1.5 text-sm transition-colors hover:text-foreground',
                    isActive
                      ? 'bg-accent text-foreground font-medium'
                      : 'text-muted-foreground',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex shrink-0 items-center gap-1">
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
            <ProfileDialog />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
