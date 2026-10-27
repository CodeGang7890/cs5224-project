import { type FormEvent, useState } from "react";
import { LogIn, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiErrorMessage } from "@/lib/form-errors";
import type { ApiError } from "@/types/api";

import { useAuth } from "../hooks/use-auth";
import { SignUpForm } from "./sign-up-form";
import { SocialLoginButtons } from "./social-login-buttons";

export type AuthMode = "login" | "signup";

function loginErrorMessage(error: ApiError) {
  return error.status === 401
    ? "Incorrect username or password."
    : apiErrorMessage(error);
}

/**
 * "Log In" (or, with `mode="signup"`, "Sign Up") button opening the login / sign-up dialog: Continue with
 * Google / Facebook, or a username and password. The dialog can switch between the two modes.
 */
export function AuthDialog({
  mode: initialMode = "login",
}: {
  mode?: AuthMode;
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<AuthMode>(initialMode);

  // The forms unmount when the dialog closes or switches mode, which clears their errors.
  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen) setMode(initialMode);
  };
  const close = () => setOpen(false);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        {initialMode === "signup" ? (
          <Button size="sm" variant="outline">
            <UserPlus /> Sign Up
          </Button>
        ) : (
          <Button size="sm">
            <LogIn /> Log In
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>
            {mode === "login" ? "Log in" : "Create your account"}
          </DialogTitle>
          <DialogDescription>
            {mode === "login"
              ? "Continue with Google or Facebook, or use your username and password."
              : "Sign up with Google or Facebook, or choose a username and password. You'll set up your business next."}
          </DialogDescription>
        </DialogHeader>

        <SocialLoginButtons onLoggedIn={close} />
        <div className="text-muted-foreground flex items-center gap-3 text-xs uppercase">
          <span className="bg-border h-px flex-1" />
          or
          <span className="bg-border h-px flex-1" />
        </div>
        {mode === "login" ? (
          <LoginForm onLoggedIn={close} />
        ) : (
          <SignUpForm onSignedUp={close} />
        )}

        <p className="text-muted-foreground text-center text-sm">
          {mode === "login"
            ? "Don't have an account? "
            : "Already have an account? "}
          <button
            type="button"
            className="text-primary font-medium underline-offset-4 hover:underline"
            onClick={() => setMode(mode === "login" ? "signup" : "login")}
          >
            {mode === "login" ? "Sign up" : "Log in"}
          </button>
        </p>
      </DialogContent>
    </Dialog>
  );
}

function LoginForm({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { login, isLoggingIn, loginError } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await login({ username: username.trim(), password });
      onLoggedIn();
    } catch {
      // Shown via `loginError`.
    }
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="login-username">Username</Label>
        <Input
          id="login-username"
          name="username"
          autoComplete="username"
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

      <Button type="submit" disabled={isLoggingIn} className="w-full">
        {isLoggingIn ? "Logging in…" : "Log in"}
      </Button>
    </form>
  );
}
