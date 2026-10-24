import { type FormEvent, useState } from "react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { FormField } from "@/components/common/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { type FormErrors, getFormErrors } from "@/lib/form-errors";

import { useSaveProvider } from "../hooks/use-services";
import type { ServiceProvider, ServiceProviderInput } from "../types";
import {
  SERVICE_LIMITS,
  changedProviderFields,
  validateProvider,
} from "../validation";

interface ProviderFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The provider to edit; omit to add one. */
  provider?: ServiceProvider;
  /** Called with a newly added provider (e.g. to show their schedule). */
  onCreated?: (provider: ServiceProvider) => void;
}

/** Adds or edits a service provider (name, note, active). Their hours are set in the schedule. */
export function ProviderFormDialog({
  open,
  onOpenChange,
  provider,
  onCreated,
}: ProviderFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {open && (
          <ProviderForm
            provider={provider}
            onCreated={onCreated}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ProviderForm({
  provider,
  onCreated,
  onDone,
}: {
  provider?: ServiceProvider;
  onCreated?: (provider: ServiceProvider) => void;
  onDone: () => void;
}) {
  const isEdit = provider !== undefined;
  const save = useSaveProvider();
  const [name, setName] = useState(provider?.name ?? "");
  const [description, setDescription] = useState(provider?.description ?? "");
  const [isActive, setIsActive] = useState(provider?.is_active ?? true);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [confirmOpen, setConfirmOpen] = useState(false);

  const input: ServiceProviderInput = {
    name: name.trim(),
    description: description.trim(),
    is_active: isActive,
  };
  const changes = isEdit ? changedProviderFields(provider, input) : input;
  const hasChanges = Object.keys(changes).length > 0;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fieldErrors = validateProvider(input);
    setErrors({ fields: fieldErrors as Record<string, string> });
    if (Object.keys(fieldErrors).length === 0 && hasChanges)
      setConfirmOpen(true);
  };

  const handleConfirm = () => {
    save.mutate(isEdit ? { id: provider.id, input: changes } : { input }, {
      onSuccess: (saved) => {
        setConfirmOpen(false);
        onDone();
        if (!isEdit) onCreated?.(saved);
      },
      onError: (error) => {
        setConfirmOpen(false);
        setErrors(getFormErrors(error));
      },
    });
  };

  return (
    <>
      <form onSubmit={handleSubmit} noValidate className="grid gap-4">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? `Edit “${provider.name}”` : "Add service provider"}
          </DialogTitle>
          <DialogDescription>
            Someone (or something) services are booked with: a photographer, a
            teacher, a room… Each has their own schedule, week by week.
          </DialogDescription>
        </DialogHeader>

        <FormField
          id="provider-name"
          label="Name"
          required
          error={errors.fields.name || undefined}
          length={{
            current: input.name.length,
            max: SERVICE_LIMITS.providerNameMaxLength,
          }}
        >
          <Input
            id="provider-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </FormField>

        <FormField
          id="provider-description"
          label="Note"
          hint="Optional, for your team (customers don't see it)."
          error={errors.fields.description || undefined}
          length={{
            current: input.description.length,
            max: SERVICE_LIMITS.providerDescriptionMaxLength,
          }}
        >
          <Textarea
            id="provider-description"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </FormField>

        <div className="flex items-center justify-between gap-4 rounded-md border p-3">
          <div className="grid gap-1">
            <label htmlFor="provider-is-active" className="text-sm font-medium">
              Active
            </label>
            <p className="text-muted-foreground text-xs">
              Inactive providers take no new bookings; existing ones stay.
            </p>
          </div>
          <Switch
            id="provider-is-active"
            checked={isActive}
            onCheckedChange={setIsActive}
          />
        </div>

        {errors.form && (
          <p role="alert" className="text-destructive text-sm">
            {errors.form}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onDone}>
            Cancel
          </Button>
          <Button type="submit" disabled={!hasChanges}>
            {isEdit ? "Save changes" : "Add provider"}
          </Button>
        </DialogFooter>
      </form>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isEdit ? "Save changes?" : "Add this service provider?"}
        description={
          isEdit ? (
            <>“{provider.name}” will be updated.</>
          ) : (
            <>
              “{input.name}” will be added, with nothing open yet: open some
              hours in their schedule, and link them to their services.
            </>
          )
        }
        confirmLabel={isEdit ? "Save changes" : "Add provider"}
        pendingLabel="Saving…"
        isPending={save.isPending}
        onConfirm={handleConfirm}
      />
    </>
  );
}
