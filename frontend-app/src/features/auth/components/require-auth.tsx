import type { ReactNode } from "react";
import { LockKeyhole } from "lucide-react";
import { Outlet } from "react-router";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { APP_NAME } from "@/config/app";
import { selectIsAuthenticated, useAuthStore } from "@/stores/auth-store";

import { AuthDialog } from "./auth-dialog";

/**
 * Login guard. Renders its content only when the user is logged in; otherwise shows a
 * "you need to be logged in" message with a Log In button. After logging in, the content
 * appears in place, with no redirect.
 *
 * Two ways to use it:
 *
 * 1. As a layout route in `src/app/routes.tsx` to protect a group of pages (preferred):
 *      { element: <RequireAuth />, children: [{ path: paths.workflow, element: <WorkflowPage /> }] }
 *
 * 2. Wrapping any element directly:
 *      <RequireAuth><WorkflowPage /></RequireAuth>
 */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);

  if (!isAuthenticated) return <LoginRequired />;
  return children ?? <Outlet />;
}

function LoginRequired() {
  return (
    <section className="flex justify-center py-12">
      <title>{`Log in required | ${APP_NAME}`}</title>
      <Card className="w-full max-w-md text-center">
        <CardHeader className="justify-items-center">
          <div className="bg-muted mb-2 flex size-12 items-center justify-center rounded-full">
            <LockKeyhole className="text-muted-foreground size-6" />
          </div>
          <CardTitle>Log in required</CardTitle>
          <CardDescription>
            You need to be logged in to access this page. New here? Sign up.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center gap-2">
          <AuthDialog mode="signup" />
          <AuthDialog />
        </CardContent>
      </Card>
    </section>
  );
}
