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

import { placeholderProfile } from '../data/placeholder-profile'

const PROFILE_PARAM = 'profile'

function getInitials(name: string) {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

/**
 * Profile icon button + modal. Open state lives in the URL (`?profile`), so the
 * modal can be deep-linked and the browser back button closes it.
 */
export function ProfileDialog() {
  const [searchParams, setSearchParams] = useSearchParams()
  const open = searchParams.has(PROFILE_PARAM)
  const profile = placeholderProfile

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
        <div className="flex items-center gap-4">
          <Avatar className="size-12">
            <AvatarFallback>{getInitials(profile.name)}</AvatarFallback>
          </Avatar>
          <div className="flex flex-col">
            <span className="font-medium">{profile.name}</span>
            <span className="text-muted-foreground text-sm">{profile.email}</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
