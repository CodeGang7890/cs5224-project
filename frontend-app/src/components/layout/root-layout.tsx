import { Moon, Sun } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/stores/theme-store'

const navItems = [
  { to: '/', label: 'Home' },
  { to: '/posts', label: 'Posts' },
]

export function RootLayout() {
  const theme = useThemeStore((state) => state.theme)
  const toggleTheme = useThemeStore((state) => state.toggleTheme)

  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <nav className="flex items-center gap-6">
            <span className="font-semibold">frontend-app</span>
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  cn(
                    'text-sm transition-colors hover:text-foreground',
                    isActive ? 'text-foreground font-medium' : 'text-muted-foreground',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
            {theme === 'dark' ? <Sun /> : <Moon />}
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
