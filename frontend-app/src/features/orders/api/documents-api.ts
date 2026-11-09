import { configurationApiClient } from "@/lib/api-client";

/** An order's or booking's PDFs: the invoice (made with its payment link) and the receipt (made once paid). */
export type DocumentKind = "invoice" | "receipt";
export type DocumentOwner = "order" | "booking";

const OWNER_PATHS: Record<DocumentOwner, string> = {
  order: "orders",
  booking: "schedules",
};

/**
 * The PDF from configuration-service (GET /orders|schedules/{id}/invoice|receipt/), which reads it
 * from the private bucket. 404: no such PDF yet; 503: PDFs aren't stored in this environment.
 */
export async function getDocument(
  owner: DocumentOwner,
  id: number,
  kind: DocumentKind,
): Promise<Blob> {
  const { data } = await configurationApiClient.get<Blob>(
    `/${OWNER_PATHS[owner]}/${id}/${kind}/`,
    { responseType: "blob", timeout: 30_000 },
  );
  return data;
}
