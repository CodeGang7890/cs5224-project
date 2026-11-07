import { type FormEvent, useState } from "react";
import { Store } from "lucide-react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { FormField } from "@/components/common/form-field";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getFormErrors } from "@/lib/form-errors";

import { useSaveMyBusiness } from "../hooks/use-my-business";
import { BUSINESS_LIMITS, type BusinessInput } from "../types";

const EMPTY: BusinessInput = {
  business_name: "",
  location: "",
  description: "",
};

function validate(values: BusinessInput): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!values.business_name.trim())
    errors.business_name = "Enter your business name.";
  if (!values.location.trim())
    errors.location = "Enter where your business is.";
  for (const key of ["business_name", "location", "description"] as const) {
    if (values[key].length > BUSINESS_LIMITS[key])
      errors[key] = `At most ${BUSINESS_LIMITS[key]} characters.`;
  }
  return errors;
}

/**
 * "Set up your business": a new account (sign up, or a first Google / Facebook login) has none, so the
 * business pages wait for it (`RequireBusiness`) and Home shows it instead of the WhatsApp card.
 */
export function CreateBusinessCard() {
  const save = useSaveMyBusiness();
  const [values, setValues] = useState<BusinessInput>(EMPTY);
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const [confirmOpen, setConfirmOpen] = useState(false);

  const server = save.error ? getFormErrors(save.error) : undefined;
  const errors = { ...server?.fields, ...clientErrors };
  const trimmed = (): BusinessInput => ({
    business_name: values.business_name.trim(),
    location: values.location.trim(),
    description: values.description.trim(),
  });

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const problems = validate(trimmed());
    setClientErrors(problems);
    if (Object.keys(problems).length === 0) setConfirmOpen(true);
  };

  const handleConfirm = () => {
    save.mutate(trimmed(), { onSettled: () => setConfirmOpen(false) });
  };

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Store className="size-5" /> Set up your business
        </CardTitle>
        <CardDescription>
          Tell us about your business to start: your assistant uses this when it
          talks to customers. You can connect WhatsApp next.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
          <FormField
            id="business-name"
            label="Business name"
            required
            error={errors.business_name}
            length={{
              current: values.business_name.length,
              max: BUSINESS_LIMITS.business_name,
            }}
          >
            <Input
              id="business-name"
              value={values.business_name}
              onChange={(event) =>
                setValues({ ...values, business_name: event.target.value })
              }
              aria-invalid={errors.business_name ? true : undefined}
              autoComplete="organization"
            />
          </FormField>
          <FormField
            id="business-location"
            label="Location"
            required
            error={errors.location}
            hint="E.g. Tiong Bahru, Singapore"
          >
            <Input
              id="business-location"
              value={values.location}
              onChange={(event) =>
                setValues({ ...values, location: event.target.value })
              }
              aria-invalid={errors.location ? true : undefined}
            />
          </FormField>
          <FormField
            id="business-description"
            label="Description"
            error={errors.description}
            hint="What you sell or offer (optional)."
            length={{
              current: values.description.length,
              max: BUSINESS_LIMITS.description,
            }}
          >
            <Textarea
              id="business-description"
              rows={3}
              value={values.description}
              onChange={(event) =>
                setValues({ ...values, description: event.target.value })
              }
              aria-invalid={errors.description ? true : undefined}
            />
          </FormField>
          {server?.form && (
            <p role="alert" className="text-destructive text-sm">
              {server.form}
            </p>
          )}
          <div>
            <Button type="submit" disabled={save.isPending}>
              Create business
            </Button>
          </div>
        </form>
      </CardContent>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Create your business?"
        description={`Your account will be set up for ${values.business_name.trim()}. You can change these details later.`}
        confirmLabel="Create business"
        pendingLabel="Creating…"
        isPending={save.isPending}
        onConfirm={handleConfirm}
      />
    </Card>
  );
}
