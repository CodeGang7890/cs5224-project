/** How much of a payment reference the tables show (the dialogs show it all). */
const SHORT_LENGTH = 8;

/** The first characters of a payment reference (32 hex characters), e.g. "3f9c1a2b…", for tables. */
export function shortPaymentReference(reference: string): string {
  return reference.length > SHORT_LENGTH
    ? `${reference.slice(0, SHORT_LENGTH)}…`
    : reference;
}
