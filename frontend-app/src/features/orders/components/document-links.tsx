import { FileText, Loader2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ApiError } from "@/types/api";

import {
  type DocumentKind,
  type DocumentOwner,
  getDocument,
} from "../api/documents-api";
import { availableDocuments } from "../documents";
import type { OrderStatus } from "../types";

const LABELS: Record<DocumentKind, string> = {
  invoice: "Invoice",
  receipt: "Receipt",
};

function errorMessage(error: ApiError): string {
  if (error.status === 404) return "Not ready yet.";
  if (error.status === 503) return "PDFs aren't stored in this environment.";
  return "Couldn't open it.";
}

/**
 * Buttons opening an order's / booking's invoice and receipt PDFs in a new tab (only the ones it should
 * have). The tab is opened in the click (popup blockers), then pointed at the PDF once it's downloaded.
 */
export function DocumentLinks({
  owner,
  item,
  compact = false,
  emptyText = "—",
}: {
  owner: DocumentOwner;
  item: { id: number; payment_link: string | null; order_status: OrderStatus };
  /** Small ghost buttons, for table rows. */
  compact?: boolean;
  emptyText?: string;
}) {
  const [opening, setOpening] = useState<DocumentKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const kinds = availableDocuments(item);

  if (kinds.length === 0) {
    return <span className="text-muted-foreground text-sm">{emptyText}</span>;
  }

  const open = async (kind: DocumentKind) => {
    setError(null);
    setOpening(kind);
    const tab = window.open("", "_blank");
    try {
      const blob = await getDocument(owner, item.id, kind);
      const url = URL.createObjectURL(
        new Blob([blob], { type: "application/pdf" }),
      );
      if (tab) tab.location.href = url;
      else window.location.assign(url);
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (caught) {
      tab?.close();
      setError(errorMessage(caught as ApiError));
    } finally {
      setOpening(null);
    }
  };

  return (
    <div className="grid gap-1">
      <div className={cn("flex flex-wrap", compact ? "gap-1" : "gap-2")}>
        {kinds.map((kind) => (
          <Button
            key={kind}
            type="button"
            variant={compact ? "ghost" : "outline"}
            size="sm"
            className={cn("gap-1.5", compact && "h-7 px-2")}
            disabled={opening !== null}
            onClick={(event) => {
              event.stopPropagation(); // in a table row, don't open the order too
              void open(kind);
            }}
          >
            {opening === kind ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <FileText className="size-3.5" />
            )}
            {LABELS[kind]}
          </Button>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      )}
    </div>
  );
}
