# Reproducible evaluation

See [REQUIREMENTS.md](REQUIREMENTS.md) for the remaining cases and proposed
report wording. [run_recovery.py](run_recovery.py) and the
[recovery runbook](../infrastructure/RECOVERY.md) cover backup and restore.

These scripts produce evidence for the report. Unit tests mock paid providers; the live runner
uses dedicated test accounts and deletes the sandbox chats it creates. Keep generated results
under `evaluation/results/` (Git-ignored); include only aggregate numbers in the report.

## Functional tests

The existing service suites cover the report's focus areas. `run_functional.py` executes the
same suites as CI, records exact test counts and failures, and fails if no tests are discovered.

| Service | Focus and principal suites |
| --- | --- |
| configuration-service | Auth and tenant scoping (`auth_app/test_api.py`, app API tests), Meta Embedded Signup (`configuration_app/tests.py`), stock/calendar (`checkout_app/tests/`, `product_app/tests.py`), migrations and fixtures |
| messaging-service | Chat and checkout/booking (`test_chat_*`), questions/tools/validation, Pub/Sub ack/nack and duplicates (`test_consumer.py`, `test_inbound*.py`), Vertex adapter (`test_llm_vertex.py`) |
| messaging-ingester | Meta webhook status/signature/payload/publisher (`tests/test_webhook.py`, `test_real_payloads.py`, `test_publisher.py`) |
| processing-service | Payment transitions/idempotence, invoice/storage/email and consumer (`tests/test_payments.py`, `test_documents.py`, `test_notifications.py`, `test_consumer.py`) |
| payment-ingester | Session creation, callback token and mapping (`tests/test_routes.py`) |
| notification-job | Payment/booking reminder windows, delivery and schema (`tests/test_job.py`, sender tests) |
| mock_whatsapp | Meta-compatible Graph API/signing/errors (`tests/test_mock_whatsapp.py`) |

Run with a Python environment containing each service's `requirements.txt`:

```powershell
python evaluation/run_functional.py --python .\configuration-service\.venv\Scripts\python.exe
```

CI additionally runs Django against PostgreSQL 17, checks migrations and fixtures, tests the
SQLAlchemy schema mappings against migrated PostgreSQL, and starts a Pub/Sub emulator for the
messaging-ingester integration test. Local runs without those services report skipped tests;
do not count a skip as a passed integration test. The runner writes `functional.json` and
`functional.md` with the commit and environment used.

Replay the deliberately injected failure/duplicate cases separately to get an auditable matrix:

```powershell
python evaluation/run_faults.py --python .\configuration-service\.venv\Scripts\python.exe
```

This selects 12 existing tests across five services: signature rejection, publish failure and
Meta retry, consumer nack, duplicate inbound, outbox retry, concurrent order/message handling,
invoice redelivery, repeated payment after upload failure, Xendit token rejection, and email
retry classification. It writes `evaluation/results/faults.json`. The mocks inject failures at
service boundaries; they do not measure deployed Pub/Sub delivery guarantees.

## Technical tests

| SLO | Automated method | Interpretation |
| --- | --- | --- |
| Webhook ACK p95 < 1 s | `load_test.py` posts uniquely signed payloads and records response p95/statuses | `meta-status.json` tests the app-level ACK/signature path without publishing. `meta-message.json` tests business webhook → Pub/Sub on a **local** stack. |
| Reply p95 < 10 s | `live_scenarios.py --mode reply --samples 20` creates separate sandbox chats and times the actual proxy → Gemini reply | Reports p95 only with at least 20 samples; deletes each chat afterward. |
| Availability ≥ 99.9%/month | Deferred; `load_test.py --method GET --rates 1 --seconds-per-step 60` gives a short live sample | A minute of successful probes cannot establish a monthly availability SLO. |
| Correctness: no observed lost/duplicate events | Consumer, idempotency, repeated-event, schema and migration suites; local Pub/Sub emulator integration | Report the event count and failures tested. Finite tests cannot prove absolute “zero lost.” |
| Isolation: no cross-tenant access | Tenant-scoping API suites plus `live_scenarios.py --mode isolation` | Other test tenant must receive 403 on both sandbox write and delete. `load_test.py --probe-url` measures other-tenant latency during a burst. |
| Elasticity: burst error rate < 0.1% | `load_test.py --rates 1,5,10,25,50 --error-rate-target 0.001` and `cloud_metrics.py` | Correlate request p95/error rate with peak Cloud Run instances and Pub/Sub backlog. A pull consumer alone does not scale Cloud Run on queue depth. |

The read-only GET burst checks HTTP capacity and cross-tenant latency; it is **not** a 50
WhatsApp-messages/s result. The signed `meta-status.json` request checks the app-level ACK only;
the full business-webhook → Pub/Sub path requires the local seeded stack/emulator.

### Load balancer, Cloud Armor, and VPC

`run_platform.py` reads the live forwarding rule, managed certificate, URL map, serverless NEGs,
backend logging and Cloud Armor attachments. It checks DNS, verified HTTPS, all four backend
routes, prefix rewrites, Private Google Access, Cloud NAT, three VPC-attached Cloud Run services,
the four callers' routes to configuration-service, and that six direct `run.app` URLs reject
external requests. The optional Armor probe sends **one GET** with a synthetic SQLi query to a
read-only API, then looks for the preview rule in the load-balancer log. It changes no policy.

```powershell
python evaluation/run_platform.py --armor-probe --output evaluation/results/platform.json
python evaluation/load_test.py --url https://ansera.hopto.org/api/auth/subscription-tiers/ --method GET --rates 1,5,10,25,50 --seconds-per-step 5 --max-requests 455 --expected-status 200 --error-rate-target 0.001 --allow-remote --output evaluation/results/lb-burst.json
python evaluation/load_test.py --url https://ansera.hopto.org/api/auth/subscription-tiers/ --method GET --rates 1 --seconds-per-step 60 --max-requests 60 --expected-status 200 --error-rate-target 0 --allow-remote --output evaluation/results/lb-uptime-sample.json
```

The platform runner needs `gcloud` access to this project. An Armor preview `DENY` log proves
the rule matched; its enforced outcome remains `ACCEPT`. The current SQLi/XSS/LFI/RCE rules
are all in preview, with a default allow rule and no rate limit. The 50/s step exercises a
read-only API through the load balancer. Use Cloud Monitoring instance samples to determine
whether the application service actually scaled out. The live VPC settings confirm routing
configuration; successful sandbox replies exercise the configuration-service → messaging-service
path. They do not prove that every external dependency can be reached through Cloud NAT.

### Pub/Sub dead-letter policy

`run_dead_letter.py` creates disposable Pub/Sub topics and subscriptions, publishes one poison
message, nacks it repeatedly, and verifies that it reaches the dead-letter subscription. CI
runs this against the emulator. The live mode additionally checks both application worker
subscriptions' five-attempt policy, DLQ subscriptions, and Pub/Sub service-agent IAM. Its
delivery exercise also uses disposable resources; it does not publish to the application queues.

```powershell
$env:PUBSUB_EMULATOR_HOST = 'localhost:8085'
python evaluation/run_dead_letter.py --project local-project
Remove-Item Env:PUBSUB_EMULATOR_HOST
python evaluation/run_dead_letter.py --live --project cs5224-ansera --project-number 30883659663 --output evaluation/results/dead-letter-live.json
```

The emulator must already be running, and the live command needs Pub/Sub create/delete and
resource IAM permissions. Pub/Sub forwards after an *approximate* number of attempts, so the
test checks that five is configured and that the message eventually arrives, while recording
the actual delivery-attempt values. It does not prove that the production workers themselves
will nack a specific failing business event.

Run the local business webhook ACK test with the seeded Kopi account and Pub/Sub emulator:

```powershell
$env:META_TEST_SECRET = 'dev-app-secret-1'
python evaluation/load_test.py --url http://localhost:8002/webhook/1 --body-template evaluation/payloads/meta-message.json --meta-secret-env META_TEST_SECRET --slo webhook --rates 1,5,10,25,50 --seconds-per-step 10 --max-requests 910 --expected-status 200 --output evaluation/results/webhook-local.json
```

The example sends 910 synthetic messages. Only use this with an isolated local stack and test
data. For a harmless live app-level ACK measurement, use `meta-status.json` with `/webhook`,
the current app secret in an environment variable, and `--allow-remote`; that path does **not**
measure Pub/Sub publication. Never run the message payload against live test accounts at 50/s.

For the hosted app's real LLM latency and tenant isolation, provide two dedicated test accounts:

```powershell
$env:ANSERA_TEST_USERNAME = 'kopi_owner'
$env:ANSERA_TEST_PASSWORD = '<test password>'
$env:ANSERA_OTHER_TEST_USERNAME = 'bloom_owner'
$env:ANSERA_OTHER_TEST_PASSWORD = '<test password>'
python evaluation/live_scenarios.py --base-url https://ansera.hopto.org --mode both --samples 20 --allow-live
```

For a read-only HTTP burst, use `load_test.py --method GET` with an authenticated test endpoint;
add `--probe-url` and `--probe-bearer-env` for another tenant. After the run and a two-minute
Monitoring delay, capture instance counts and queue depth:

```powershell
python evaluation/cloud_metrics.py --project cs5224-ansera --service messaging-service --subscription messaging-queue-worker --minutes 30
```

Cloud Run currently keeps at least one service instance warm. **Scale-to-zero is not an
applicable pass criterion** under that configuration. The maximum of three instances should be
verified with the recorded instance-count series, not inferred from Terraform settings alone.

## Cloud Run scale-out and instance replacement

`cloud_run_canary/` is a disposable, private service for testing Cloud Run's instance lifecycle
without changing business endpoints. Its `/work` route holds a request for at most three seconds;
`POST /fail` returns its process ID, then exits that one container. `run_cloud_run_scaling.py`
checks that a different process takes over and that concurrent delayed requests reach more than
one process. The canary uses a dedicated unprivileged service account and is deleted after the
test. It demonstrates Cloud Run behavior under the canary's settings, not the throughput of the
application services.

Build with the project's existing Cloud Build deployer and Singapore source bucket:

```powershell
gcloud builds submit evaluation/cloud_run_canary --config=evaluation/cloud_run_canary/cloudbuild.yaml --gcs-source-staging-dir=gs://cs5224-ansera-build-source-sg/source --region=asia-southeast1 --project=cs5224-ansera
gcloud iam service-accounts create cloud-run-scaling-eval --project=cs5224-ansera --display-name='Temporary Cloud Run scaling evaluation'
gcloud run deploy ansera-scaling-eval --image=asia-southeast1-docker.pkg.dev/cs5224-ansera/apps/cloud-run-scaling-eval:eval-20261108 --region=asia-southeast1 --project=cs5224-ansera --service-account=cloud-run-scaling-eval@cs5224-ansera.iam.gserviceaccount.com --ingress=all --no-allow-unauthenticated --concurrency=1 --min-instances=1 --max-instances=1 --memory=256Mi --cpu=1 --timeout=60s
```

Test replacement with exactly one warm instance, then allow up to three and force scale-out:

```powershell
$canary = 'https://ansera-scaling-eval-30883659663.asia-southeast1.run.app'
python evaluation/run_cloud_run_scaling.py --url $canary --phase recovery --gcloud-token --allow-remote --output evaluation/results/cloud-run-recovery.json
gcloud run services update ansera-scaling-eval --project=cs5224-ansera --region=asia-southeast1 --min-instances=1 --max-instances=3 --concurrency=1
python evaluation/run_cloud_run_scaling.py --url $canary --phase scaleout --gcloud-token --allow-remote --requests 12 --rounds 2 --delay-ms 2500 --output evaluation/results/cloud-run-scaleout.json
```

Remove the disposable runtime and its service identity when finished:

```powershell
gcloud run services delete ansera-scaling-eval --project=cs5224-ansera --region=asia-southeast1 --quiet
gcloud iam service-accounts delete cloud-run-scaling-eval@cs5224-ansera.iam.gserviceaccount.com --project=cs5224-ansera --quiet
```

The Docker image remains in the existing Artifact Registry for a later rerun. An instance exit
can produce a brief 5XX window; record failed probes and replacement time rather than claiming
uninterrupted availability. Cloud Run service instances cannot be individually stopped with the
`gcloud beta run instances stop` command, which addresses a separate single-instance resource.

The load runner requires `--allow-remote` for hosted endpoints and an explicit higher
`--max-requests` for large runs. It never saves credentials or response bodies. The Cloud Run
instance-count and Pub/Sub backlog metrics are sampled every minute and may appear after a delay
([Cloud Run monitoring](https://docs.cloud.google.com/run/docs/monitoring),
[Pub/Sub monitoring](https://docs.cloud.google.com/pubsub/docs/monitoring)).
