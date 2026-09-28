import { useEffect } from 'react'

import { useThemeStore } from '@/stores/theme-store'

/** Syncs the Zustand theme with the `dark` class on <html>, which shadcn/ui's CSS variables key off. */
export function useApplyTheme() {
  const theme = useThemeStore((state) => state.theme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])
}
