import { type ComponentProps, useRef } from "react";

import { Button } from "@/components/ui/button";
import { AuthDialog } from "@/features/auth";

/**
 * A landing-page button (any label and style) that opens the usual log-in / sign-up dialog. It renders
 * `AuthDialog` with its own small button hidden and clicks that, so the dialog itself is unchanged.
 */
export function AuthButton({
  mode = "login",
  onClick,
  ...props
}: ComponentProps<typeof Button> & { mode?: "login" | "signup" }) {
  const dialogRef = useRef<HTMLSpanElement>(null);
  return (
    <>
      <Button
        {...props}
        onClick={(event) => {
          onClick?.(event);
          dialogRef.current?.querySelector("button")?.click();
        }}
      />
      <span ref={dialogRef} hidden>
        <AuthDialog mode={mode} />
      </span>
    </>
  );
}
