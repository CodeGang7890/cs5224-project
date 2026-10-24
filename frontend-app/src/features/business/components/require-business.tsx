import { Outlet } from "react-router";

import { Skeleton } from "@/components/ui/skeleton";
import { APP_NAME } from "@/config/app";

import { useNeedsBusiness } from "../hooks/use-my-business";
import { CreateBusinessCard } from "./create-business-card";

/**
 * Business guard, a layout route inside `RequireAuth` (`src/app/routes.tsx`): the business pages need the
 * account to have a business, so a new account (sign up, first Google / Facebook login) is asked to create
 * it first; then the page renders in place.
 */
export function RequireBusiness() {
  const needsBusiness = useNeedsBusiness();

  if (needsBusiness === undefined) {
    return (
      <div className="grid gap-3">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full max-w-2xl" />
      </div>
    );
  }
  if (needsBusiness) {
    return (
      <section className="flex flex-col gap-6">
        <title>{`Set up your business | ${APP_NAME}`}</title>
        <CreateBusinessCard />
      </section>
    );
  }
  return <Outlet />;
}
