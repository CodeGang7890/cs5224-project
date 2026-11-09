# Evaluation run — 8 November 2026 (Singapore time)

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
