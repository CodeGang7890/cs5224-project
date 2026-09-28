import { CircleUser } from 'lucide-react'
import { useSearchParams } from 'react-router'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { type CurrentUser, useCurrentUser } from '@/features/auth'

const PROFILE_PARAM = 'profile'

function getDisplayName(user: CurrentUser) {
  return [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username
}

function getInitials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

/**
 * Profile icon button + modal showing the logged-in user (GET /api/auth/me/). Open state
 * lives in the URL (`?profile`), so the modal can be deep-linked and back closes it.
 */
export function ProfileDialog() {
  const [searchParams, setSearchParams] = useSearchParams()
  const open = searchParams.has(PROFILE_PARAM)
  const { data: user, isPending, isError, error } = useCurrentUser()

  const handleOpenChange = (nextOpen: boolean) => {
    setSearchParams((params) => {
      if (nextOpen) params.set(PROFILE_PARAM, '')
      else params.delete(PROFILE_PARAM)
      return params
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Open profile">
          <CircleUser className="size-5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Your profile</DialogTitle>
          <DialogDescription>Account details for the signed-in user.</DialogDescription>
        </DialogHeader>
        {isPending ? (
          <Skeleton className="h-12 w-full" />
        ) : isError ? (
          <p className="text-destructive text-sm">Couldn't load your profile: {error.message}</p>
        ) : (
          <div className="grid gap-4">
            <div className="flex items-center gap-4">
              <Avatar className="size-12">
                <AvatarFallback>{getInitials(getDisplayName(user))}</AvatarFallback>
              </Avatar>
              <div className="flex min-w-0 flex-col">
                <span className="truncate font-medium">{getDisplayName(user)}</span>
                <span className="text-muted-foreground truncate text-sm">
                  {user.email || 'No email'}
                </span>
              </div>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Username</dt>
              <dd className="truncate">{user.username}</dd>
              <dt className="text-muted-foreground">Business</dt>
              <dd className="truncate">
                {user.business === null ? 'None' : `${user.business_name} (ID ${user.business})`}
              </dd>
            </dl>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
