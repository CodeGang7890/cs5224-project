import { type FormEvent, useState } from "react";
import {
  Eye,
  EyeOff,
  FlaskConical,
  LockKeyhole,
  LogIn,
  Sparkles,
  User,
  UserPlus,
} from "lucide-react";

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
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-md">
        <DialogHeader className="items-center text-center sm:text-center">
          <div className="mb-1 flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-sky-500 text-white shadow-md">
            <Sparkles className="size-5" />
          </div>
          <DialogTitle className="text-xl">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </DialogTitle>
          <DialogDescription>
            {mode === "login"
              ? "Log in to manage your AI sales assistant."
              : "Sign up with Google or Facebook, or choose a username and password. You'll set up your business next."}
          </DialogDescription>
        </DialogHeader>

        <SocialLoginButtons onLoggedIn={close} />
        <div className="text-muted-foreground flex items-center gap-3 text-xs">
          <span className="bg-border h-px flex-1" />
          {mode === "login"
            ? "or log in with your username"
            : "or sign up with a username"}
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

// The sample accounts from configuration-service's fixtures (auth_app/fixtures/sample_business_users.json),
// shown so testers can try the app. They all use the same password.
const DEMO_PASSWORD = "123";
const DEMO_ACCOUNTS = [
  { username: "kopi_owner", business: "Kopi & Co. Café" },
  { username: "bloom_owner", business: "Bloom & Twine Florist" },
  { username: "bloom_staff", business: "Bloom & Twine (staff)" },
  { username: "lumen_owner", business: "Lumen & Lens Photography" },
  { username: "rally_owner", business: "Rally Point Courts" },
];

function LoginForm({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { login, isLoggingIn, loginError } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

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
        <div className="relative">
          <User className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            id="login-username"
            name="username"
            autoComplete="username"
            required
            placeholder="e.g. kopi_owner"
            className="pl-9"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            aria-invalid={loginError ? true : undefined}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="login-password">Password</Label>
        <div className="relative">
          <LockKeyhole className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            id="login-password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            className="pr-10 pl-9"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={loginError ? true : undefined}
          />
          <button
            type="button"
            onClick={() => setShowPassword((shown) => !shown)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="text-muted-foreground hover:text-foreground absolute top-1/2 right-2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md transition-colors"
          >
            {showPassword ? (
              <EyeOff className="size-4" />
            ) : (
              <Eye className="size-4" />
            )}
          </button>
        </div>
      </div>

      {loginError && (
        <p role="alert" className="text-destructive text-sm">
          {loginErrorMessage(loginError)}
        </p>
      )}

      <Button type="submit" disabled={isLoggingIn} className="w-full">
        {isLoggingIn ? "Logging in…" : "Log in"}
      </Button>

      <div className="bg-muted/50 text-muted-foreground rounded-lg border border-dashed p-3 text-xs">
        <p className="flex items-center gap-1.5 font-medium">
          <FlaskConical className="size-3.5" /> Trying it out? Use a demo
          account
        </p>
        <p className="mt-1">
          Password for all:{" "}
          <code className="bg-background text-foreground rounded px-1 py-0.5 font-mono">
            {DEMO_PASSWORD}
          </code>{" "}
          · click one to fill in the form.
        </p>
        <ul className="mt-2 grid gap-1">
          {DEMO_ACCOUNTS.map((account) => (
            <li key={account.username}>
              <button
                type="button"
                onClick={() => {
                  setUsername(account.username);
                  setPassword(DEMO_PASSWORD);
                }}
                className="hover:bg-background hover:text-foreground flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left transition-colors"
              >
                <code className="font-mono">{account.username}</code>
                <span className="truncate">{account.business}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </form>
  );
}
