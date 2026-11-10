# Evaluation runs — 8–9 November 2026 (Singapore time)

This snapshot records tests actually run against the current local working tree and the
Singapore deployment. Scripts and exact commands are in [README.md](README.md). The local
source was at Git HEAD `013eed9` with uncommitted test fixes; the hosted service revisions
observed immediately after the live checks were configuration `configuration-service-00015-zb2`, messaging
`messaging-service-00012-s6f`, and Meta ingester `messaging-ingester-00004-9d4`.

| Evaluation | Observed result | Target / conclusion |
| --- | --- | --- |
| Functional suites | 1,359 tests run across seven services; 0 failures, 0 errors, 7 skipped integrations | Passed locally; skipped PostgreSQL/schema and Pub/Sub emulator cases need CI |
| Fault and duplicate matrix | 12/12 selected cases passed across five services | Mocked nack/retry, duplicate, signature, publisher and payment failure paths |
| SLO-1 webhook ACK | 20 signed status-only POSTs; 0 errors; p95 160 ms | < 1 s met for the app-level `/webhook` path |
| SLO-2 real LLM reply | 20 separate sandbox chats; 20 valid replies; p95 3.13 s | < 10 s met for the browser API → messaging service → Gemini path |
| SLO-5 tenant isolation | Other tenant's sandbox POST and DELETE both returned 403; owner cleanup returned 204 | Cross-tenant sandbox access denied in this check |
| SLO-5 noisy neighbour probe | Other tenant GET: baseline p95 439 ms (5 requests), during burst p95 375 ms (31 requests); 0 errors | No degradation observed in this short run |
| SLO-6 read-only HTTP burst | 1 → 5 → 10 → 25 → 50 requests/s, 5 s per step; 455/455 HTTP 200; overall p95 351 ms; max dispatch lag about 1 ms | 0% errors, below 0.1% target for **HTTP GET**, not WhatsApp messages |
| Cloud Run instances | Peak 1 instance in the 30-minute Monitoring window for configuration-service | The tested GET burst was served without observed horizontal scale-out |
| Isolated Cloud Run replacement | Canary had min=1/max=1/concurrency=1; `POST /fail` exited its container; a new process ID served `/health` after 1.37 s, with one failed probe | Replacement observed; brief interruption occurred |
| Isolated Cloud Run scale-out | Canary had min=1/max=3/concurrency=1; 24 delayed requests reached 3 distinct process IDs with 0 errors; Cloud Monitoring also sampled 3 instances | Cloud Run added instances under concurrent requests; p95 was 12.61 s including queueing/startup |
| Pub/Sub backlog | Latest sampled unacked count 0 for `messaging-queue-worker` | Context only; this run did not inject queue messages |
| Pub/Sub dead-letter policy (9 Nov) | Both live worker subscriptions configured for 5 attempts with required service-agent IAM; isolated live message was delivered 5 times, nacked 5 times, then forwarded to its DLQ in 78.19 s | Passed for the disposable delivery path; no production queue received a test message |

The signed webhook payload contained only a Meta delivery-status event, so it did not test
business webhook publication or downstream message processing. The 50 requests/s burst was
read-only and did not test 50 WhatsApp messages/s or queue-driven scaling. Current Singapore
Cloud Run settings specify a minimum of one instance, so scale-to-zero cannot pass under this
configuration. The availability target (99.9% over a month) was deferred because the remaining
project time cannot produce a meaningful monthly observation. Twelve injected-failure tests
show correct behavior for their scenarios; finite tests cannot establish an absolute guarantee
of zero lost or duplicate events.

The disposable canary used revisions `ansera-scaling-eval-00001-hps` for replacement and
`ansera-scaling-eval-00002-44q` for scale-out. It used a separate container and service identity;
its results establish Cloud Run platform behavior under concurrency=1, **not** that the live
application's configuration-service (concurrency=10) scaled out in its earlier HTTP burst.

Local raw JSON/Markdown results are in `evaluation/results/` on the machine that ran the
tests. That directory is ignored by Git because it can contain environment-specific details.
The dead-letter test's disposable topics and subscriptions were deleted and verified absent.
At the time of this test, both live worker subscriptions had a 30-second ACK deadline, while
Terraform specified 120 seconds for messaging and 60 seconds for payment. A subsequent
Terraform apply on 9 November brought the live deadlines to 120 and 60 seconds respectively.

## Re-evaluation — 9 November 2026

| Evaluation | Observed result | Limit |
| --- | --- | --- |
| Functional suites | 1,371 discovered across seven services; 0 failures, 0 errors, 7 skipped | PostgreSQL/schema and Pub/Sub emulator integrations were unavailable locally; skipped cases are not passes |
| Fault matrix | 12/12 selected cases passed | Mocks inject failures at service boundaries |
| HTTPS edge and VPC | 29/29 live platform checks passed: DNS, active certificate, four backend routes, prefix rewrite, NEGs, Armor attachment/logging, Private Google Access/NAT, VPC egress, caller routing, and six direct `run.app` 404s | VPC/NAT configuration checks do not separately prove external egress from every workload |
| Cloud Armor SQLi probe | Synthetic GET returned 200; LB log recorded preview `DENY` at priority 1000 and enforced `ACCEPT` | WAF detection observed; rules are **not enforcing** and no rate limiting is configured |
| Webhook ACK through LB | 20 signed status-only POSTs, 0 unexpected, p95 **196 ms** | Tests `/messaging/webhook` app-level ACK, not business message publication |
| Short availability sample | 60/60 HTTPS GETs at 1/s, p95 **180 ms** | One minute cannot establish 99.9% monthly availability |
| Read-only LB burst | 455/455 HTTP 200 across 1 → 5 → 10 → 25 → 50 GET/s, overall p95 **75.7 ms**, 0% errors | Does not establish 50 WhatsApp messages/s or backend scale-out |
| Live sandbox and isolation | 20/20 Gemini replies through LB, p95 **3.26 s**; other tenant POST/DELETE both 403 | Uses seeded test accounts and temporary sandbox sessions |
| Production Cloud Run instances | Configuration-service peak **1** in the sampled 30-minute Monitoring window | No application scale-out observed; queue backlog series had no data |
| Isolated Cloud Run replacement | New canary instance served in **0.71 s**, with one failed probe | Brief interruption observed; application services were untouched |
| Isolated Cloud Run scale-out | 24 concurrent delayed requests reached **3** instance IDs, 0 errors, p95 **12.58 s** including queueing/startup | Demonstrates canary platform behavior, not production throughput |

The new edge consists of a global HTTPS load balancer, four serverless NEGs and backends,
managed certificates, URL rewrites, and Cloud Armor. The VPC path also includes the Singapore
default subnet, Private Google Access, Direct VPC egress on configuration-service,
messaging-service and mock-whatsapp, plus a Cloud NAT gateway. The mock WhatsApp service is an
additional deployed component and its 16 local tests passed; its public `/whatsapp/` page
returned HTTP 200. Firebase Hosting, Cloud SQL, Pub/Sub, Cloud Scheduler, Vertex AI, and the
other services remain part of the system; this rerun did not repeat manual Meta/Xendit payment
or email-delivery scenarios. It also did not take a production load-balancer backend offline,
so no production failover claim follows from the canary replacement result. The temporary
scaling canary and its service account were deleted.

Raw results for this rerun are `functional.json`, `faults.json`, `platform.json`,
`platform-routing.json`, `lb-webhook-ack.json`, `lb-burst.json`, `lb-uptime-sample.json`,
`live-lb-scenarios.json`, `cloud-metrics-lb.json`, `cloud-run-recovery-1109.json`, and
`cloud-run-scaleout-1109.json` under the ignored `evaluation/results/` directory.

## Backup and reminder follow-up — 9 November 2026

| Check | Result | Limit |
| --- | --- | --- |
| Notification job unit suite | 41 discovered; 39 passed, 2 schema integration tests skipped because no migrated test database was supplied | Covers reminder windows, payment/appointment sending, channel failures and retry behavior; does not prove live delivery after the fix |
| SQL backup configuration | Live Singapore instance was RUNNABLE with backups enabled and 6 successful backups; PITR disabled and backup location unset | Five-minute RPO and SQL restore remain unverified until the reviewed Terraform change is applied and a PITR clone drill runs |
| Cloud Storage object restore | A unique disposable object was deleted, restored, and SHA-256 matched in **19.047 s**; live test copy removed | Seven-day soft delete was present; this is a single-object recovery, not a full bucket restore or region-outage test |

The targeted Terraform recovery apply completed with 1 dependency added, 2 resources
updated, and 0 destroyed. Cloud SQL restarted and returned to `RUNNABLE` with PITR,
seven days of transaction logs, 14 retained backups, and `asia-southeast1` backup
location. The first post-change automated backup completed successfully in Singapore.

| Follow-up check | Observed result | Limit |
| --- | --- | --- |
| SQL latest recoverable point | 4.436 minutes behind at 14:52:29 UTC; `run_recovery.py check` passed | One point sample only; the window initially returned no result while the first backup/log archive settled |
| SQL PITR clone | A two-minute-old point was accepted; disposable clone `ansera-recovery-eval-3411dcb44a` reached `RUNNABLE` in Singapore with `configuration_service` present. Clone request to operation completion: **13.325 min** | CLI stopped waiting early; the server-side operation finished successfully. No row-by-row or application cutover verification. Full-service RTO remains unmeasured |
| Clone cleanup | Temporary instance deleted; a subsequent list found no recovery-eval instances | No ongoing clone cost from this drill |
| Post-apply API smoke | 5/5 read-only HTTPS requests through the load balancer returned 200; p95 335 ms | Confirms this public API route responded after the database restart, not every workflow |

The recovery scripts and proposed requirement wording are in [run_recovery.py](run_recovery.py)
and [REQUIREMENTS.md](REQUIREMENTS.md). The script now handles Cloud SQL's long-running
clone operation by waiting before cleanup; that path has a local automated test.
