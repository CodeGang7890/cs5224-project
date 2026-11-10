# Requirement verification cases and proposed wording

Record each test's date, commit or Cloud Run revision, environment, and result.
The automated local suites and the 9 November live measurements are summarized
in `EVIDENCE.md`. Manual cases below are not marked passed until performed.

## Functional requirements

| ID | Proposed report wording | Additional case and pass criterion | Current state |
| --- | --- | --- | --- |
| F1 | Owners can register with password, Google or Facebook and maintain a business profile. | Fresh-profile signup through each provider, save/reload profile; other account cannot read it. | API tests and provider sign-in passed; full new-account browser journey remains manual. |
| F2 | Owners can manage products, stock, services, providers, weekly calendars and FAQs. | Create/edit/reload each in UI; stock and booked slots obey API rules. | API suites passed; UI check outstanding. |
| F3 | Owners can connect a supported WhatsApp Business account through Meta Embedded Signup. | Enroll a new Meta test business, complete verification, send one message and receive one reply. | Mocked signup and webhook tests passed; real enrollment outstanding. Replace “one click” because Meta authorization has several steps and external prerequisites. |
| F4 | The AI assists with questions and records orders and bookings through configured workflows. | Separate test chats for FAQ, order, available slot and status; compare resulting tenant records. | Unit suites and general live chat passed; full live matrix outstanding. |
| F5 | Customers can receive payment links; owners can track sandbox payments and issue PDF invoices and receipts. | Complete Xendit sandbox payment, inspect PDFs, replay callback; one paid transition, no duplicate order. | Unit tests and manual payment/email passed; PDF inspection and live replay outstanding. |
| F6 | The scheduled job sends unpaid-order and upcoming-appointment reminders through configured channels. | Create test order and booking in reminder windows, run job, check one delivery and job outcome. | 39 notification tests passed, 2 schema integrations skipped; live delivery remains manual. |
| F7 | Owners can use dashboard views for conversations, orders, bookings, payments and chat sandbox. | Visit/open records in each view after login; second tenant cannot open first tenant’s records. | Backend tests and sandbox passed; browser coverage absent. |

The earlier functional wording is largely achievable, but F3 should not promise
“one click,” and F5 should distinguish tested sandbox payments from live money.

## Non-functional requirements

| ID | Proposed measurable wording | Verification case and current evidence |
| --- | --- | --- |
| N1 | In a 20-turn sandbox sample, p95 reply time is below 10 seconds; report real WhatsApp timing separately. | `live_scenarios.py` measured 20/20 replies, p95 3.26 s. For a customer-channel claim, timestamp at least 20 real or mock WhatsApp messages through the full webhook/queue path. |
| N2 | During a stated 15-minute pilot, the public API and webhook health routes have no failed probes; report the observed window, not monthly uptime. | The one-minute sample had 60/60 successes. Extend the probe to 15 minutes and include each public route; a 99.9% monthly claim needs a month of monitoring. |
| N3 | In tested duplicate and failure cases, no duplicate state transition or reply occurs; failed messages are retried or sent to a DLQ. | Twelve fault cases passed; an isolated message reached its DLQ after five rejections. Add a local full business-event → queue → consumer replay, comparing database state before and after. |
| N4 | A read-only API burst from 1 to 50 requests/s has <0.1% errors without manual scaling; an isolated Cloud Run concurrency test reaches at least two instances. | 455/455 GETs passed; the canary reached three instances. Production scale-out and queue bursts remain unverified. Remove scale-to-zero while services have min instances = 1. |
| N5 | Tested cross-tenant reads and writes return 403/404; another tenant's API probe has no errors during the stated burst window. | Sandbox POST/DELETE returned 403; a short noisy-neighbour probe had no errors. Add UI/API checks for orders, bookings, payments and conversations with two tenants. |
| N6 | State Singapore placement for regional app data stores and explicitly disclose global/US provider processing; do not claim all personal data remains in Singapore. | Check deployed Cloud SQL, Storage, Pub/Sub policy and runtime locations; document Firebase Auth, global Gemini and external-provider flows. This is a location inventory, not a legal compliance test. |
| N7 | SQL has scheduled backups and PITR; the latest recoverable point is at most five minutes old when measured. Deleted objects are recoverable for seven days. Record SQL clone readiness and object restore times; claim a full-service RTO only after a cutover drill. | Live check passed with 4.44-minute lag; a two-minute-old SQL point was restored to a runnable clone in about 13.33 minutes; object restore took 19.047 seconds. These are point samples, not a full application recovery or guaranteed RTO. |

Never send the F3/F5/F6 manual probes to real customers. Use dedicated test
accounts and sandbox providers, and record the exact responses without tokens,
payment details, or customer data.
