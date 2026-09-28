import { type FormEvent, useState } from 'react'
import { LogIn } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { ApiError } from '@/types/api'

import { useAuth } from '../hooks/use-auth'

function loginErrorMessage(error: ApiError) {
  if (error.status === 401) return 'Incorrect username or password.'
  if (error.status === undefined) return "Couldn't reach the server. Is configuration-service running?"
  return error.message
}

/** "Log In" button that opens a username/password dialog. */
export function LoginDialog() {
  const { login, isLoggingIn, loginError, resetLoginError } = useAuth()
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (!nextOpen) {
      setPassword('')
      resetLoginError()
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    try {
      await login({ username: username.trim(), password })
      setUsername('')
      handleOpenChange(false)
    } catch {
      // Shown via `loginError`.
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm">
          <LogIn /> Log In
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Log in</DialogTitle>
            <DialogDescription>Enter your username and password.</DialogDescription>
          </DialogHeader>

          <div className="grid gap-2">
            <Label htmlFor="login-username">Username</Label>
            <Input
              id="login-username"
              name="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              aria-invalid={loginError ? true : undefined}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="login-password">Password</Label>
            <Input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={loginError ? true : undefined}
            />
          </div>

          {loginError && (
            <p role="alert" className="text-destructive text-sm">
              {loginErrorMessage(loginError)}
            </p>
          )}

          <DialogFooter>
            <Button type="submit" disabled={isLoggingIn} className="w-full">
              {isLoggingIn ? 'Logging in…' : 'Log in'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
