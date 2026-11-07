import { type ChangeEvent, type FormEvent, useState } from "react";

import { FormField } from "@/components/common/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type FormErrors, getFormErrors } from "@/lib/form-errors";

import { useAuth } from "../hooks/use-auth";
import type { SignUpInput } from "../types";

const EMPTY: SignUpInput = {
  username: "",
  email: "",
  password: "",
  first_name: "",
  last_name: "",
};
const PASSWORD_MIN_LENGTH = 8; // Django's MinimumLengthValidator (the backend also rejects common / numeric ones)

/** Username, email, password and optional names → POST /auth/signup/ (logged in straight away). */
export function SignUpForm({ onSignedUp }: { onSignedUp: () => void }) {
  const { signUp, isSigningUp, signUpError } = useAuth();
  const [values, setValues] = useState<SignUpInput>(EMPTY);
  const [confirm, setConfirm] = useState("");
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  const serverErrors: FormErrors = signUpError
    ? getFormErrors(signUpError)
    : { fields: {} };
  const errors = { ...serverErrors.fields, ...clientErrors };
  const set =
    (key: keyof SignUpInput) => (event: ChangeEvent<HTMLInputElement>) =>
      setValues((current) => ({ ...current, [key]: event.target.value }));

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const problems: Record<string, string> = {};
    if (values.password.length < PASSWORD_MIN_LENGTH) {
      problems.password = `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
    }
    if (confirm !== values.password)
      problems.confirm = "The passwords don't match.";
    setClientErrors(problems);
    if (Object.keys(problems).length) return;
    try {
      await signUp({
        ...values,
        username: values.username.trim(),
        email: values.email.trim(),
      });
      onSignedUp();
    } catch {
      // Shown via `signUpError`.
    }
  };

  const field = (key: keyof SignUpInput) => ({
    id: `signup-${key}`,
    value: values[key],
    onChange: set(key),
    "aria-invalid": errors[key] ? true : undefined,
  });

  return (
    <form onSubmit={handleSubmit} className="grid gap-3" noValidate>
      <div className="grid grid-cols-2 gap-3">
        <FormField
          id="signup-first_name"
          label="First name"
          error={errors.first_name}
        >
          <Input {...field("first_name")} autoComplete="given-name" />
        </FormField>
        <FormField
          id="signup-last_name"
          label="Last name"
          error={errors.last_name}
        >
          <Input {...field("last_name")} autoComplete="family-name" />
        </FormField>
      </div>
      <FormField
        id="signup-username"
        label="Username"
        required
        error={errors.username}
      >
        <Input {...field("username")} autoComplete="username" required />
      </FormField>
      <FormField id="signup-email" label="Email" required error={errors.email}>
        <Input {...field("email")} type="email" autoComplete="email" required />
      </FormField>
      <FormField
        id="signup-password"
        label="Password"
        required
        error={errors.password}
        hint={`At least ${PASSWORD_MIN_LENGTH} characters, not too common or similar to your username.`}
      >
        <Input
          {...field("password")}
          type="password"
          autoComplete="new-password"
          required
        />
      </FormField>
      <FormField
        id="signup-confirm"
        label="Confirm password"
        required
        error={errors.confirm}
      >
        <Input
          id="signup-confirm"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          aria-invalid={errors.confirm ? true : undefined}
        />
      </FormField>

      {serverErrors.form && (
        <p role="alert" className="text-destructive text-sm">
          {serverErrors.form}
        </p>
      )}

      <Button type="submit" disabled={isSigningUp} className="w-full">
        {isSigningUp ? "Creating your account…" : "Sign up"}
      </Button>
    </form>
  );
}
