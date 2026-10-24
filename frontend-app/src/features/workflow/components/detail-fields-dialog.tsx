import { useState, type FormEvent } from "react";
import { CircleAlert, Plus, Trash2 } from "lucide-react";

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
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";

import {
  DETAIL_LIMITS,
  DETAIL_TYPE_LABELS,
  PRESET_DETAIL_FIELDS,
  detailFieldsOrDefault,
  describeDetailField,
  isPresetKey,
  isRequiredDetail,
  isValidDetailKey,
  keyFromLabel,
} from "../details";
import {
  DETAIL_FIELD_TYPES,
  type DetailField,
  type DetailFieldType,
} from "../types";

interface DetailFieldsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The step's current fields (undefined: the defaults). */
  fields: DetailField[] | undefined;
  /** Which step: Details collection (product orders) or Booking details (service bookings). */
  kind: "order" | "booking";
  onApply: (fields: DetailField[]) => void;
}

/**
 * Edits which customer details a details step asks for: Details collection (product orders) or
 * Booking details (service bookings), each its own list. Applying only changes the editor; the
 * workflow's Save button saves it to the backend.
 */
export function DetailFieldsDialog({
  open,
  onOpenChange,
  fields,
  kind,
  onApply,
}: DetailFieldsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85svh] flex-col gap-4 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {kind === "booking"
              ? "Details to collect for bookings"
              : "Details to collect for orders"}
          </DialogTitle>
          <DialogDescription>
            {kind === "booking"
              ? "Asked at the Booking details step, when a customer books a service."
              : "Asked at the Details collection step, when a customer orders products."}{" "}
            The chat only moves on once every required detail is given and
            valid. There's no need to ask for a phone number: customers chat on
            WhatsApp, so you already have it.
          </DialogDescription>
        </DialogHeader>
        {/* Remounted on each open, so it always starts from the step's current fields. */}
        {open && (
          <DetailFieldsForm
            fields={detailFieldsOrDefault(fields)}
            onCancel={() => onOpenChange(false)}
            onApply={(next) => {
              onApply(next);
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Form state ---------------------------------------------------------------------------

/** A preset (basic) detail: on or off, with an editable label. Its other settings are kept. */
interface PresetDraft {
  enabled: boolean;
  field: DetailField;
  label: string;
  required: boolean;
}

/** A custom detail being edited. Number inputs are kept as strings. */
interface CustomDraft {
  uid: string;
  /** The saved key, kept when editing; null for a new detail (made from the label on apply). */
  key: string | null;
  label: string;
  type: DetailFieldType;
  description: string;
  maxLength: string;
  minValue: string;
  maxValue: string;
  required: boolean;
}

type DraftErrors = Partial<
  Record<
    "label" | "description" | "maxLength" | "minValue" | "maxValue",
    string
  >
>;

function toCustomDraft(field: DetailField): CustomDraft {
  return {
    uid: crypto.randomUUID(),
    key: field.key,
    label: field.label,
    type: field.type,
    description: field.description ?? "",
    maxLength: field.max_length?.toString() ?? "",
    minValue: field.min_value?.toString() ?? "",
    maxValue: field.max_value?.toString() ?? "",
    required: isRequiredDetail(field),
  };
}

function newCustomDraft(): CustomDraft {
  return {
    uid: crypto.randomUUID(),
    key: null,
    label: "",
    type: "text",
    description: "",
    maxLength: "200",
    minValue: "",
    maxValue: "",
    required: true,
  };
}

function labelError(label: string): string | undefined {
  if (!label.trim()) return "Enter a label.";
  if (label.trim().length > DETAIL_LIMITS.labelMaxLength)
    return `At most ${DETAIL_LIMITS.labelMaxLength} characters.`;
  return undefined;
}

function validateCustom(draft: CustomDraft): DraftErrors {
  const errors: DraftErrors = {};
  errors.label = labelError(draft.label);
  if (draft.description.length > DETAIL_LIMITS.descriptionMaxLength) {
    errors.description = `At most ${DETAIL_LIMITS.descriptionMaxLength} characters.`;
  }
  if (draft.type === "text" && draft.maxLength.trim()) {
    const value = Number(draft.maxLength);
    if (
      !Number.isInteger(value) ||
      value < 1 ||
      value > DETAIL_LIMITS.textMaxLength
    ) {
      errors.maxLength = `A whole number from 1 to ${DETAIL_LIMITS.textMaxLength}.`;
    }
  }
  if (draft.type === "number") {
    const low = draft.minValue.trim() ? Number(draft.minValue) : undefined;
    const high = draft.maxValue.trim() ? Number(draft.maxValue) : undefined;
    if (low !== undefined && !Number.isFinite(low))
      errors.minValue = "Enter a number.";
    if (high !== undefined && !Number.isFinite(high))
      errors.maxValue = "Enter a number.";
    if (
      low !== undefined &&
      high !== undefined &&
      Number.isFinite(low) &&
      Number.isFinite(high) &&
      low > high
    ) {
      errors.maxValue = "Must be at least the minimum.";
    }
  }
  return Object.fromEntries(
    Object.entries(errors).filter(([, message]) => message),
  ) as DraftErrors;
}

/** Required is the default, so only `required: false` is stored. */
function withRequired(field: DetailField, required: boolean): DetailField {
  const { required: _previous, ...rest } = field;
  return required ? rest : { ...rest, required: false };
}

function toField(draft: CustomDraft, key: string): DetailField {
  const field: DetailField = withRequired(
    { key, label: draft.label.trim(), type: draft.type },
    draft.required,
  );
  if (draft.description.trim()) field.description = draft.description.trim();
  if (draft.type === "text" && draft.maxLength.trim())
    field.max_length = Number(draft.maxLength);
  if (draft.type === "number") {
    if (draft.minValue.trim()) field.min_value = Number(draft.minValue);
    if (draft.maxValue.trim()) field.max_value = Number(draft.maxValue);
  }
  return field;
}

// --- Form ---------------------------------------------------------------------------------

interface DetailFieldsFormProps {
  fields: DetailField[];
  onCancel: () => void;
  onApply: (fields: DetailField[]) => void;
}

function DetailFieldsForm({
  fields,
  onCancel,
  onApply,
}: DetailFieldsFormProps) {
  const [presets, setPresets] = useState<PresetDraft[]>(() =>
    PRESET_DETAIL_FIELDS.map((preset) => {
      const existing = fields.find((field) => field.key === preset.key);
      const field = existing ?? preset;
      return {
        enabled: existing !== undefined,
        field,
        label: field.label,
        required: isRequiredDetail(field),
      };
    }),
  );
  const [customs, setCustoms] = useState<CustomDraft[]>(() =>
    fields.filter((field) => !isPresetKey(field.key)).map(toCustomDraft),
  );
  const [submitted, setSubmitted] = useState(false);

  const presetErrors = presets.map((preset) =>
    preset.enabled ? labelError(preset.label) : undefined,
  );
  const customErrors = customs.map(validateCustom);
  const enabledPresets = presets.filter((preset) => preset.enabled);
  const count = enabledPresets.length + customs.length;
  const hasRequired =
    enabledPresets.some((preset) => preset.required) ||
    customs.some((draft) => draft.required);
  const formError =
    count === 0
      ? "Choose at least one detail to collect."
      : count > DETAIL_LIMITS.fieldsMax
        ? `At most ${DETAIL_LIMITS.fieldsMax} details.`
        : !hasRequired
          ? "At least one detail must be required, or the chat would move on without asking anything."
          : undefined;
  const hasErrors =
    formError !== undefined ||
    presetErrors.some(Boolean) ||
    customErrors.some((e) => Object.keys(e).length > 0);

  const updatePreset = (index: number, changes: Partial<PresetDraft>) =>
    setPresets((current) =>
      current.map((preset, i) =>
        i === index ? { ...preset, ...changes } : preset,
      ),
    );
  const updateCustom = (uid: string, changes: Partial<CustomDraft>) =>
    setCustoms((current) =>
      current.map((draft) =>
        draft.uid === uid ? { ...draft, ...changes } : draft,
      ),
    );

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (hasErrors) return;
    const result: DetailField[] = presets
      .filter((preset) => preset.enabled)
      .map((preset) =>
        withRequired(
          { ...preset.field, label: preset.label.trim() },
          preset.required,
        ),
      );
    // Saved keys stay (collected data is stored under them); new details get one from their label.
    // Preset keys are reserved, so a custom "Email" doesn't turn into the Email preset.
    const taken = new Set([
      ...PRESET_DETAIL_FIELDS.map((field) => field.key),
      ...customs.flatMap((draft) => (draft.key ? [draft.key] : [])),
    ]);
    for (const draft of customs) {
      let key = draft.key;
      if (key === null || !isValidDetailKey(key)) {
        key = keyFromLabel(draft.label, taken);
        taken.add(key);
      }
      result.push(toField(draft, key));
    }
    onApply(result);
  };

  return (
    <form
      onSubmit={onSubmit}
      className="flex min-h-0 flex-1 flex-col gap-4"
      noValidate
    >
      <div className="-mx-1 grid min-h-0 flex-1 gap-5 overflow-y-auto px-1">
        <section className="grid gap-2">
          <h3 className="text-sm font-semibold">Basic details</h3>
          <ul className="grid gap-2">
            {presets.map((preset, index) => (
              <li
                key={preset.field.key}
                className="flex items-start gap-3 rounded-lg border p-3"
              >
                <Switch
                  className="mt-2"
                  checked={preset.enabled}
                  onCheckedChange={(enabled) =>
                    updatePreset(index, { enabled })
                  }
                  aria-label={`Ask for ${preset.label || preset.field.label}`}
                />
                <div className="grid flex-1 gap-1">
                  <Input
                    value={preset.label}
                    disabled={!preset.enabled}
                    onChange={(event) =>
                      updatePreset(index, { label: event.target.value })
                    }
                    aria-label={`Label for ${preset.field.label}`}
                    aria-invalid={
                      (submitted && presetErrors[index] !== undefined) ||
                      undefined
                    }
                  />
                  <p
                    className={
                      submitted && presetErrors[index]
                        ? "text-destructive text-xs"
                        : "text-muted-foreground text-xs"
                    }
                  >
                    {(submitted && presetErrors[index]) ||
                      describeDetailField(
                        withRequired(preset.field, preset.required),
                      )}
                  </p>
                </div>
                <RequiredSwitch
                  id={`preset-${preset.field.key}-required`}
                  checked={preset.required}
                  disabled={!preset.enabled}
                  onChange={(required) => updatePreset(index, { required })}
                />
              </li>
            ))}
          </ul>
        </section>

        <section className="grid gap-2">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Custom details</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setCustoms((c) => [...c, newCustomDraft()])}
            >
              <Plus /> Add a detail
            </Button>
          </div>
          {customs.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              None yet. Add things like customisation notes (text), a postal
              code (number) or a delivery date.
            </p>
          ) : (
            <ul className="grid gap-2">
              {customs.map((draft, index) => (
                <CustomDetailRow
                  key={draft.uid}
                  draft={draft}
                  errors={submitted ? customErrors[index] : {}}
                  onChange={(changes) => updateCustom(draft.uid, changes)}
                  onRemove={() =>
                    setCustoms((current) =>
                      current.filter((d) => d.uid !== draft.uid),
                    )
                  }
                />
              ))}
            </ul>
          )}
        </section>
      </div>

      {submitted && formError && (
        <p
          role="alert"
          className="text-destructive flex items-center gap-2 text-sm"
        >
          <CircleAlert className="size-4 shrink-0" /> {formError}
        </p>
      )}

      <DialogFooter className="items-center sm:justify-between">
        <p className="text-muted-foreground text-xs">
          {count} detail{count === 1 ? "" : "s"}. Save the workflow afterwards
          to keep the change.
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit">Apply</Button>
        </div>
      </DialogFooter>
    </form>
  );
}

interface CustomDetailRowProps {
  draft: CustomDraft;
  errors: DraftErrors;
  onChange: (changes: Partial<CustomDraft>) => void;
  onRemove: () => void;
}

function CustomDetailRow({
  draft,
  errors,
  onChange,
  onRemove,
}: CustomDetailRowProps) {
  const id = (name: string) => `${draft.uid}-${name}`;
  return (
    <li className="grid gap-3 rounded-lg border p-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_11rem_auto_auto] sm:items-start">
        <FormField
          id={id("label")}
          label="Label"
          error={errors.label}
          hint={draft.key ? `Key: ${draft.key}` : undefined}
        >
          <Input
            id={id("label")}
            value={draft.label}
            placeholder="e.g. Customisation notes"
            onChange={(event) => onChange({ label: event.target.value })}
            aria-invalid={errors.label !== undefined || undefined}
          />
        </FormField>
        <FormField id={id("type")} label="Type">
          <NativeSelect
            id={id("type")}
            value={draft.type}
            onChange={(event) =>
              onChange({ type: event.target.value as DetailFieldType })
            }
          >
            {DETAIL_FIELD_TYPES.map((type) => (
              <option key={type} value={type}>
                {DETAIL_TYPE_LABELS[type]}
              </option>
            ))}
          </NativeSelect>
        </FormField>
        <RequiredSwitch
          id={id("required")}
          className="sm:mt-6"
          checked={draft.required}
          onChange={(required) => onChange({ required })}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="sm:mt-5.5"
          aria-label={`Remove ${draft.label || "this detail"}`}
          title="Remove"
          onClick={onRemove}
        >
          <Trash2 className="text-destructive" />
        </Button>
      </div>

      {draft.type === "text" && (
        <FormField
          id={id("max")}
          label="Max characters"
          error={errors.maxLength}
          hint={`Optional, up to ${DETAIL_LIMITS.textMaxLength} (default ${DETAIL_LIMITS.textDefaultMaxLength}).`}
          className="sm:max-w-56"
        >
          <Input
            id={id("max")}
            type="number"
            inputMode="numeric"
            min={1}
            max={DETAIL_LIMITS.textMaxLength}
            value={draft.maxLength}
            onChange={(event) => onChange({ maxLength: event.target.value })}
            aria-invalid={errors.maxLength !== undefined || undefined}
          />
        </FormField>
      )}
      {draft.type === "number" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField
            id={id("min")}
            label="Minimum"
            error={errors.minValue}
            hint="Optional."
          >
            <Input
              id={id("min")}
              type="number"
              value={draft.minValue}
              onChange={(event) => onChange({ minValue: event.target.value })}
              aria-invalid={errors.minValue !== undefined || undefined}
            />
          </FormField>
          <FormField
            id={id("max-value")}
            label="Maximum"
            error={errors.maxValue}
            hint="Optional. Numbers drop leading zeros: use Text for codes like 018956."
          >
            <Input
              id={id("max-value")}
              type="number"
              value={draft.maxValue}
              onChange={(event) => onChange({ maxValue: event.target.value })}
              aria-invalid={errors.maxValue !== undefined || undefined}
            />
          </FormField>
        </div>
      )}
      <FormField
        id={id("hint")}
        label="Hint for the assistant"
        error={errors.description}
        hint="Optional, e.g. “6 digits” or “e.g. less sugar”."
        length={{
          current: draft.description.length,
          max: DETAIL_LIMITS.descriptionMaxLength,
        }}
      >
        <Input
          id={id("hint")}
          value={draft.description}
          onChange={(event) => onChange({ description: event.target.value })}
          aria-invalid={errors.description !== undefined || undefined}
        />
      </FormField>
    </li>
  );
}

/** "Required" switch: required details must be given before the chat moves on; optional ones can be skipped. */
function RequiredSwitch({
  id,
  checked,
  disabled,
  className,
  onChange,
}: {
  id: string;
  checked: boolean;
  disabled?: boolean;
  className?: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div
      className={`flex items-center gap-2 ${className ?? "mt-2"}`}
      title="Required details must be given before the chat moves on"
    >
      <Switch
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onChange}
      />
      <Label htmlFor={id} className="text-xs font-normal">
        Required
      </Label>
    </div>
  );
}
