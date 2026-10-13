# Vertex AI demo service

A standalone Cloud Run web service that demonstrates a two-stage Gemini workflow:

1. Interpret a customer message and extract its intent and facts.
2. Apply supplied business rules to draft a reply and suggest a next action.

The demo does not execute the suggested action. The backend should validate the model output, check authorization, and ask for human approval before it changes business data or triggers a transaction.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
gcloud auth application-default login
$env:GOOGLE_CLOUD_PROJECT = "YOUR_PROJECT_ID"
$env:GOOGLE_CLOUD_LOCATION = "us-central1"
$env:LLM_MODEL = "gemini-2.5-flash"
python app.py
```

Open `http://localhost:8080`. The local identity needs permission to call Vertex AI, and the Vertex AI API must be enabled in the project.

## Build and deploy

Terraform can provision a separate Cloud Run service account, Cloud Run service, Vertex AI permission, and optional Cloud Build trigger. In `infrastructure/terraform.tfvars`, set:

```hcl
enable_vertex_ai_demo                 = true
vertex_ai_demo_allow_unauthenticated = true # Set false to require Cloud Run IAM authentication.
```

If `enable_ci_cd = true`, apply Terraform, then push a commit that changes `vertex-ai-demo/**` or `infrastructure/cloudbuild-vertex-ai-demo.yaml` to the configured branch. Cloud Build builds and pushes the image to Artifact Registry, then updates the demo Cloud Run service.

For a local Docker build, from the repository root:

```powershell
docker build -t vertex-ai-demo:local .\vertex-ai-demo
$adcPath = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
docker run --rm -p 8080:8080 `
  -e GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID `
  -e GOOGLE_CLOUD_LOCATION=us-central1 `
  -e GOOGLE_GENAI_USE_VERTEXAI=True `
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json `
  -v "${adcPath}:/tmp/adc.json:ro" `
  vertex-ai-demo:local
```

This mounts your local Application Default Credentials file read-only for testing. Do not bake credentials into the image. For normal local Python development, the installed Google client library reads ADC directly from your user profile.

## Cloud Run configuration

The Terraform-managed runtime service account receives `roles/aiplatform.user`. In Cloud Run, the Google Gen AI SDK obtains credentials from the attached service account through Application Default Credentials; no API key or service-account key file is needed. Set the model, project, and location using the Cloud Run environment variables.

The public-access option is off by default. Turn it on only for a demo you intend to expose; anyone who can access the page can submit model requests that may incur Vertex AI charges. Input is capped at 2,000 characters, and Cloud Run is configured to scale to at most one instance by default.
