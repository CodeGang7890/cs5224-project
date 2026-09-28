import { LogOut } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { LoginDialog, useAuth } from '@/features/auth'
import { ProfileDialog } from '@/features/profile'

/** Header controls: "Log In" when logged out; username, profile and "Log Out" when logged in. */
export function AuthControls() {
  const { isAuthenticated, user, isLoadingUser, logout } = useAuth()

  if (!isAuthenticated) return <LoginDialog />

  return (
    <div className="flex items-center gap-1">
      {isLoadingUser ? (
        <Skeleton className="h-4 w-20" />
      ) : (
        user && (
          <span className="text-muted-foreground hidden max-w-40 truncate px-1 text-sm sm:inline">
            {user.username}
          </span>
        )
      )}
      <ProfileDialog />
      <Button variant="outline" size="sm" onClick={logout}>
        <LogOut /> Log Out
      </Button>
    </div>
  )
}
