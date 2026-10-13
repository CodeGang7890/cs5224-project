# GCP prototype infrastructure

Terraform targets an **existing, billing-enabled GCP project**. All files in this folder are infrastructure code; no app source files are changed. The default compute region is `us-central1`, which is one of the three US regions eligible for Cloud Storage Always Free usage. Resources still cost money once their free allowances are exceeded.

## What is provisioned

| Component | Terraform behavior |
| --- | --- |
| Artifact Registry | One regional Docker repository, `apps`. |
| Cloud Storage | Private Standard bucket in the compute region. The project ID based default name can be overridden. |
| Pub/Sub | Payment and messaging queues, plus the existing notification topic, each with a pull subscription. |
| Cloud Scheduler | One hourly UTC job that invokes the notification Cloud Run Job through the Cloud Run Jobs API. It is paused until `enable_notification_scheduler = true`. |
| Secret Manager | Secret containers for Django, LLM, WhatsApp, and Xendit. Terraform creates a Django key version. Add external API token versions separately. |
| Cloud Run | Five backend services are created with the hello placeholder image unless an image is set in `service_images`; Cloud Build replaces the image on matching pushes. Scale-to-zero, one instance maximum. |
| Cloud Run Jobs | `notification-job` runs once and exits. It connects to Cloud SQL and is started hourly by Cloud Scheduler; its image is updated by a separate Cloud Build trigger. |
| Cloud SQL | Optional small PostgreSQL 17 instance, database, user, and password secret. **Billed while running.** |
| Cloud DNS | Optional public zone and records for a domain you own. **Billed even when idle.** |
| Cloud Build | Backend build/deploy triggers and a Firebase Hosting frontend deployment trigger for a linked GitHub repository. |
| Vertex AI | Gemini API enabled by default; grants `roles/aiplatform.user` to the configuration-service runtime identity. Model and location are configurable. |
| Firebase | Optional Firebase enrollment, Ansera web app, and a Hosting site. Enrollment cannot be undone. |

The architecture also shows an in-memory store, load balancer, and observability. Those were not in the requested service list and are not provisioned here. Cloud Run provides a service URL; the Cloud DNS zone does not automatically map a custom domain to Cloud Run. That mapping requires a later domain or load-balancer decision.

## Prerequisites and authentication (PowerShell)

1. Install [Terraform](https://developer.hashicorp.com/terraform/install) and the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install). `gcloud` was not available on the machine when this was authored.
2. Create/select a GCP project, enable billing, and ensure your identity can enable APIs and create the listed resources. The organization may also restrict public Cloud Run access.
3. Authenticate in your own browser. Do not put a service-account JSON key in this repository:

   ```powershell
   gcloud auth login
   gcloud config set project YOUR_GCP_PROJECT_ID
   gcloud auth application-default login
   gcloud auth application-default set-quota-project YOUR_GCP_PROJECT_ID
   ```

4. Copy `terraform.tfvars.example` to `terraform.tfvars` and set `project_id`. The latter is Git-ignored. Run from this directory:

   ```powershell
   terraform init
   terraform fmt -check
   terraform validate
   terraform plan -out=prototype.tfplan
   terraform apply prototype.tfplan
   ```

The default Terraform state is **local** (`terraform.tfstate`, Git-ignored). It contains generated secret values, so keep it private and back it up. For group collaboration, migrate to a private versioned GCS state bucket before multiple people apply changes; create the bucket separately, then add a `backend "gcs"` block with its bucket and prefix and run `terraform init -migrate-state`. The state bucket itself has storage and operation costs. Never send state files or credentials in chat or commit them.

## Deployment order

1. Apply the base resources, with `enable_firebase = true` when ready. This adds Firebase to the existing project (a one-way action), creates the Ansera web app, and creates a Hosting site. The site ID must be globally unique; change `firebase_hosting_site_id` if `cs5224-ansera` is unavailable.
2. Build `frontend-app` with `npm ci` and `npm run build`. The Firebase Hosting config in this folder serves `frontend-app/dist` and rewrites client-side routes to `index.html`.
3. In Cloud Build > Repositories > 2nd gen, create a GitHub connection and authorize/install the Cloud Build GitHub App for `CodeGang7890/cs5224-project`. Set `github_connection_name = "ansera"`. With `enable_ci_cd = true` and the selected service names in `ci_cd_services`, Terraform links the repository and creates one build/deploy trigger per selected backend service. The frontend trigger builds and deploys Hosting on pushes to `main` when Firebase is enabled.
4. The five Cloud Run services are created on the first Terraform apply with the hello placeholder image unless `service_images` contains an image reference. `ci_cd_services` currently selects `configuration-service`, `messaging-service`, `messaging-ingester`, and `processing-service`. `payment-ingester` stays on the placeholder and has no build trigger until its Dockerfile is added. Push changes to a selected service folder on `main`; Cloud Build builds the Dockerfile, pushes an immutable commit-tagged image to Artifact Registry, and updates its Cloud Run service.
5. When `enable_cloud_sql = true`, Terraform creates the `notification-job` Cloud Run Job with the Cloud Run hello placeholder and configures its Cloud SQL socket and database credentials. Its Cloud Build trigger builds `notification-job/Dockerfile` and updates the job image on changes under `notification-job/`.
6. The scheduler remains paused by default. After the notification job image has been built and its database connection has been verified, set `enable_notification_scheduler = true` and apply. Cloud Scheduler then invokes the Cloud Run Jobs `:run` API hourly using a dedicated OAuth service account. The notification script currently logs draft reminders; it does not send WhatsApp messages yet.

Cloud Run services `configuration-service`, `payment-ingester`, and `messaging-ingester` receive public invoker access for browser or webhook traffic. The other services remain private. Set `django_allowed_hosts` when using a custom domain.

## Firebase, DNS, and queues

- `enable_firebase = true` adds Firebase to the existing project and creates the `Ansera` web app plus a Hosting site. The site URL is available as the `firebase_hosting_url` Terraform output. Firebase Authentication providers and the frontend's existing Django JWT auth remain separate choices.
- The Firebase Hosting trigger uses `infrastructure/firebase.json` and `infrastructure/cloudbuild-frontend.yaml`. It builds the Vite SPA and deploys it with Firebase CLI using the Cloud Build service account's Application Default Credentials. The build service account receives Firebase Hosting Admin when both Firebase and CI/CD are enabled.
- Set `dns_domain` to a domain you control to create a public zone. Point your registrar at `dns_nameservers`; add desired `dns_records` after the target IP/hostname is known. This zone alone does not create a load balancer or Cloud Run custom domain.
- The payment and messaging Pub/Sub subscriptions are **pull** subscriptions. Cloud Run instances scale to zero and will not poll while idle; use a worker design that can consume them reliably. The notification Cloud Run Job is invoked directly by Cloud Scheduler, not from the notification Pub/Sub subscription.
- Secret containers for third-party tokens intentionally have no versions. Add values with `gcloud secrets versions add SECRET_ID --data-file=FILE` using a protected local file, then configure the relevant app and runtime IAM. Avoid passing secrets in command arguments or Terraform variables.

## Vertex AI / Gemini integration

Terraform enables `aiplatform.googleapis.com` by default and gives only the services named in `vertex_ai_services` the `roles/aiplatform.user` role. The default is `configuration-service`, which currently owns the customer chat flow. Vertex AI API enablement and IAM do not call the model or incur token charges by themselves. The default runtime settings are `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=us-central1`, `GOOGLE_GENAI_USE_VERTEXAI=True`, `LLM_PROVIDER=vertex_ai`, and `LLM_MODEL=gemini-2.5-flash`. The location and model can be changed through Terraform variables. Check model availability and pricing for your chosen location before applying. No Gemini API key is needed on Cloud Run: the Google Gen AI SDK uses Application Default Credentials from the Cloud Run service account.

The existing `configuration-service/chat_app/llm.py` has three Ollama-facing functions to preserve: `generate_structured()` extracts workflow data as JSON; `generate_chat_reply()` writes a reply and may request read-only product/FAQ tools; `generate_reply()` handles a one-off chat. The workflow already runs extraction and deterministic workflow checks in `flow.py`. Replace the provider adapter behind these functions, rather than rewriting workflow state handling. Keep `prompts.py`, schema validation, `Toolbox.run()` and the deterministic checks as application logic.

In the Python app, add Google's supported `google-genai` package to `configuration-service/requirements.txt`, then initialize one client using the service identity:

```python
import os
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
)
model = os.getenv("LLM_MODEL", "gemini-2.5-flash")
```

For `generate_structured()`, pass the converted conversation history to `client.models.generate_content()`, mapping Ollama's `assistant` role to Gemini's `model` role. Pass the existing system prompt as `system_instruction`, the extraction schema as `response_schema`, `response_mime_type="application/json"`, and a low temperature. Parse the returned JSON and continue to run the app's existing schema and workflow checks; structured output does not replace server-side validation.

For `generate_chat_reply()`, convert `Toolbox.specs` into Gemini function declarations. Handle returned function calls in your adapter: dispatch only names through the existing `Toolbox.run()` allowlist, append the function result in Gemini's function-response format, and ask the model to finish its reply. Keep the current tool-call round limit. The tools currently only read the current business's products and FAQs. If you later add tools that change stock, place orders, send messages, or call payment APIs, validate the requested action and any needed customer confirmation in backend code before executing it. [Vertex AI function-calling guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling)

For local Python development, use `gcloud auth application-default login` and set the same three `GOOGLE_*` environment variables. If running the app inside Docker Compose, the container also needs access to local ADC credentials; do not copy credentials into an image or commit them. You can keep Ollama as a selectable local provider while adding Vertex AI for deployed Cloud Run. The provider switch itself requires application edits, which are outside this `infrastructure/` folder.

See Google's [Gen AI SDK for Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/sdks/overview), [Gemini API pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing), and [model list](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models).

## Cost notes

Google's free quotas are shared at the billing-account level where stated and may change. Cloud Storage Always Free covers Standard storage in `us-west1`, `us-central1`, and `us-east1`; it does **not** mean unlimited free storage, requests, or transfer. Cloud Scheduler has three free jobs per billing account. Cloud Run, Pub/Sub, Cloud Build, Artifact Registry, and Secret Manager each have distinct limits. Cloud SQL's ordinary small instance is billed continuously; a separate, time-limited Cloud SQL trial may be available for a new project but is not the same as this Terraform instance. Cloud DNS charges for managed zones and queries. External APIs and network egress can also cost money. Set a GCP Billing budget and alerts before applying; a budget alert does not automatically stop spend.

Current vendor pages: [Google Cloud Free Tier](https://cloud.google.com/free), [Cloud Storage pricing](https://cloud.google.com/storage/pricing), [Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing), [Cloud SQL trial](https://docs.cloud.google.com/sql/docs/postgres/free-trial-instance), [Cloud DNS pricing](https://cloud.google.com/dns/pricing).
