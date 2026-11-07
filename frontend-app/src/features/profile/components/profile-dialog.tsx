import type { LucideIcon } from "lucide-react";
import {
  CircleUser,
  Crown,
  Info,
  KeyRound,
  Mail,
  ShieldCheck,
  Sparkles,
  Store,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import { useSearchParams } from "react-router";

import { FacebookIcon, GoogleIcon } from "@/components/common/brand-icons";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type CurrentUser,
  SUBSCRIPTION_TIER_LABELS,
  useCurrentUser,
} from "@/features/auth";
import { cn } from "@/lib/utils";
import { type LoginMethod, useAuthStore } from "@/stores/auth-store";

const PROFILE_PARAM = "profile";

function getDisplayName(user: CurrentUser) {
  return (
    [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username
  );
}

function getInitials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

const LOGIN_METHODS: Record<LoginMethod, { label: string; icon: ReactNode }> = {
  google: { label: "Google", icon: <GoogleIcon /> },
  facebook: {
    label: "Facebook",
    icon: <FacebookIcon className="text-[#1877F2]" />,
  },
  password: {
    label: "Username and password",
    icon: <KeyRound className="text-muted-foreground" />,
  },
};

/**
 * Profile icon button + modal showing the logged-in user (GET /api/auth/me/): who they are, their
 * business, how this session signed in and their plan. Open state lives in the URL (`?profile`), so the
 * modal can be deep-linked and back closes it.
 */
export function ProfileDialog() {
  const [searchParams, setSearchParams] = useSearchParams();
  const open = searchParams.has(PROFILE_PARAM);
  const { data: user, isPending, isError, error } = useCurrentUser();

  const handleOpenChange = (nextOpen: boolean) => {
    setSearchParams((params) => {
      if (nextOpen) params.set(PROFILE_PARAM, "");
      else params.delete(PROFILE_PARAM);
      return params;
    });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Open profile">
          <CircleUser className="size-5" />
        </Button>
      </DialogTrigger>
      <DialogContent
        className={cn(
          "gap-0 overflow-hidden p-0 sm:max-w-md",
          // The close button sits on the banner (shown once the profile loaded): white there.
          user && "[&>button]:text-white [&>button]:opacity-90",
        )}
      >
        {isPending ? (
          <div className="grid gap-4 p-6">
            <DialogTitle className="sr-only">Your profile</DialogTitle>
            <DialogDescription className="sr-only">Loading…</DialogDescription>
            <Skeleton className="size-20 rounded-full" />
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : isError ? (
          <div className="grid gap-2 p-6">
            <DialogTitle>Your profile</DialogTitle>
            <DialogDescription className="text-destructive">
              Couldn't load your profile: {error.message}
            </DialogDescription>
          </div>
        ) : (
          <ProfileContent user={user} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ProfileContent({ user }: { user: CurrentUser }) {
  const loginMethod = useAuthStore((state) => state.loginMethod);
  const name = getDisplayName(user);
  const login = loginMethod ? LOGIN_METHODS[loginMethod] : null;

  return (
    <>
      {/* Banner */}
      <div className="relative h-24 overflow-hidden bg-gradient-to-br from-emerald-500 via-emerald-600 to-sky-600">
        <div className="absolute -top-10 -left-6 size-32 rounded-full bg-white/15 blur-2xl" />
        <div className="absolute -right-8 -bottom-12 size-36 rounded-full bg-sky-300/30 blur-2xl" />
      </div>

      <div className="flex flex-col gap-5 px-6 pb-6">
        <div className="-mt-10 flex items-end justify-between gap-3">
          <Avatar className="ring-background size-20 shadow-md ring-4">
            <AvatarFallback className="bg-gradient-to-br from-emerald-500 to-sky-500 text-xl font-semibold text-white">
              {getInitials(name)}
            </AvatarFallback>
          </Avatar>
          <div className="flex flex-wrap justify-end gap-1.5 pb-1">
            <PlanBadge tier={user.subscription_tier} />
            {user.is_staff && (
              <Badge variant="outline" className="gap-1">
                <ShieldCheck /> Admin
              </Badge>
            )}
          </div>
        </div>

        <div>
          <DialogTitle className="text-xl">{name}</DialogTitle>
          <DialogDescription>@{user.username}</DialogDescription>
        </div>

        <dl className="divide-y rounded-xl border">
          <DetailRow icon={Store} label="Business">
            {user.business_name ?? (
              <span className="text-muted-foreground">No business yet</span>
            )}
          </DetailRow>
          <DetailRow icon={Mail} label="Email">
            {user.email || (
              <span className="text-muted-foreground">No email</span>
            )}
          </DetailRow>
          <DetailRow icon={KeyRound} label="Signed in with">
            {login ? (
              <span className="flex items-center gap-2 [&>svg]:size-4 [&>svg]:shrink-0">
                {login.icon}
                {login.label}
              </span>
            ) : (
              <span className="text-muted-foreground">
                Log in again to see this
              </span>
            )}
          </DetailRow>
        </dl>

        <SubscriptionCard tier={user.subscription_tier} />
      </div>
    </>
  );
}

function DetailRow({
  icon: Icon,
  label,
  children,
}: {
  icon: LucideIcon;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-lg">
        <Icon className="text-muted-foreground size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <dt className="text-muted-foreground text-xs">{label}</dt>
        <dd className="truncate text-sm font-medium">{children}</dd>
      </div>
    </div>
  );
}

function PlanBadge({ tier }: { tier: CurrentUser["subscription_tier"] }) {
  const isBusiness = tier === "business";
  return (
    <Badge
      className={cn(
        "gap-1",
        isBusiness
          ? "bg-amber-500 text-white"
          : "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
      )}
    >
      {isBusiness ? <Crown /> : <Sparkles />}
      {SUBSCRIPTION_TIER_LABELS[tier] ?? tier} plan
    </Badge>
  );
}

/** The plan, with a "Manage subscription" button that only explains there's no billing in this demo. */
function SubscriptionCard({
  tier,
}: {
  tier: CurrentUser["subscription_tier"];
}) {
  const [showNote, setShowNote] = useState(false);
  const isBusiness = tier === "business";

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border p-4",
        isBusiness
          ? "border-amber-300 bg-gradient-to-br from-amber-50 to-orange-50 dark:border-amber-700 dark:from-amber-950/40 dark:to-orange-950/30"
          : "bg-gradient-to-br from-emerald-50 to-sky-50 dark:from-emerald-950/40 dark:to-sky-950/30",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex size-9 items-center justify-center rounded-full",
              isBusiness
                ? "bg-amber-500 text-white"
                : "bg-emerald-600 text-white",
            )}
          >
            {isBusiness ? (
              <Crown className="size-4" />
            ) : (
              <Sparkles className="size-4" />
            )}
          </div>
          <div className="leading-tight">
            <p className="text-muted-foreground text-xs">Subscription</p>
            <p className="font-semibold">
              {SUBSCRIPTION_TIER_LABELS[tier] ?? tier} plan
            </p>
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="bg-background/70"
          onClick={() => setShowNote(true)}
        >
          Manage subscription
        </Button>
      </div>
      {showNote && (
        <p
          role="status"
          className="animate-in fade-in slide-in-from-top-1 text-muted-foreground flex items-start gap-2 text-xs"
        >
          <Info className="mt-0.5 size-3.5 shrink-0" />
          This is a demo app, so there's no billing yet: subscriptions can't be
          changed here.
        </p>
      )}
    </div>
  );
}
