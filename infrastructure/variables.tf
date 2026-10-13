variable "project_id" {
  description = "Existing GCP project ID with billing enabled."
  type        = string
}

variable "region" {
  description = "Compute region; keep it aligned with the free-tier storage region."
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "Globally unique object bucket name; defaults to PROJECT_ID-app-objects."
  type        = string
  default     = ""
}

variable "service_images" {
  description = "Full immutable image references for services ready to deploy. Missing services are not created."
  type        = map(string)
  default     = {}
  validation {
    condition = alltrue([
      for name, image in var.service_images :
      contains(["configuration-service", "messaging-service", "processing-service", "messaging-ingester"], name) && length(trimspace(image)) > 0
    ])
    error_message = "Use a known backend service name and a nonempty full image reference."
  }
}

variable "django_allowed_hosts" {
  description = "Comma-separated Django hostnames; the default accepts Cloud Run's run.app hostname. Add a custom domain when used."
  type        = string
  default     = ".run.app"
}

variable "enable_cloud_sql" {
  description = "Cloud SQL is billed continuously; enable only when ready to pay."
  type        = bool
  default     = false
}

variable "sql_tier" {
  description = "Smallest shared-core Cloud SQL tier; still billable."
  type        = string
  default     = "db-f1-micro"
}

variable "dns_domain" {
  description = "Owned DNS domain, e.g. example.com; blank disables the billable DNS zone."
  type        = string
  default     = ""
}

variable "dns_records" {
  description = "Records to create inside dns_domain, keyed by label. Values contain type, ttl, and rrdatas."
  type = map(object({
    type    = string
    ttl     = number
    rrdatas = list(string)
  }))
  default = {}
}

variable "enable_firebase" {
  description = "Permanently adds Firebase to the existing GCP project."
  type        = bool
  default     = false
}

variable "github_owner" {
  description = "Deprecated GitHub owner setting retained for existing tfvars; triggers use the 2nd gen repository connection below."
  type        = string
  default     = "michac789"
}

variable "github_repo" {
  description = "Deprecated GitHub repository setting retained for existing tfvars; triggers use the 2nd gen repository connection below."
  type        = string
  default     = "cs5224-project"
}

variable "github_connection_name" {
  description = "Name of the GitHub host connection created in Cloud Build (2nd gen) after installing the Cloud Build GitHub App."
  type        = string
  default     = ""
}

variable "github_repository_name" {
  description = "Cloud Build linked-repository resource name."
  type        = string
  default     = "cs5224-project"
}

variable "github_repository_uri" {
  description = "HTTPS clone URL for the application repository."
  type        = string
  default     = "https://github.com/michac789/cs5224-project.git"
}

variable "firebase_hosting_site_id" {
  description = "Globally unique Firebase Hosting site ID; this determines the web.app/firebaseapp.com subdomains."
  type        = string
  default     = "cs5224-ansera"
}

variable "github_branch_regex" {
  type    = string
  default = "^main$"
}

variable "enable_ci_cd" {
  description = "Enable GitHub Cloud Build triggers after images are safe to deploy."
  type        = bool
  default     = false
}

variable "ci_cd_services" {
  description = "Backend directories with a production-ready Dockerfile and an existing Terraform-managed Cloud Run service."
  type        = set(string)
  default     = []
  validation {
    condition = alltrue([
      for name in var.ci_cd_services : contains(["configuration-service", "messaging-service", "processing-service", "messaging-ingester"], name)
    ])
    error_message = "CI/CD services must have a Dockerfile: configuration-service, messaging-service, processing-service, or messaging-ingester."
  }
}

variable "notification_schedule" {
  description = "Cron schedule for a Pub/Sub notification tick."
  type        = string
  default     = "0 * * * *"
}

variable "enable_vertex_ai" {
  description = "Enable the Vertex AI API and Gemini access for selected backend service identities. API enablement alone does not invoke or bill models."
  type        = bool
  default     = true
}

variable "vertex_ai_services" {
  description = "Backend runtime service accounts that can call Vertex AI. Start with configuration-service, which currently owns the chat workflow."
  type        = set(string)
  default     = ["configuration-service"]
  validation {
    condition = alltrue([
      for name in var.vertex_ai_services : contains(["configuration-service", "messaging-service", "processing-service", "payment-ingester", "messaging-ingester"], name)
    ])
    error_message = "Vertex AI access must be granted to one of the five backend service identities."
  }
}

variable "vertex_ai_location" {
  description = "Vertex AI inference location. Choose a location supported by the selected model."
  type        = string
  default     = "us-central1"
}

variable "vertex_ai_model" {
  description = "Gemini model ID used by application code after the Ollama adapter is replaced."
  type        = string
  default     = "gemini-2.5-flash"
}
