variable "project_id" {
  description = "Existing GCP project ID with billing enabled."
  type        = string
}

variable "region" {
  description = "Compute region; keep it aligned with the free-tier storage region."
  type        = string
  default     = "us-central1"
}

variable "retire_us_resources" {
  description = "Destroy the superseded US regional stack after Singapore is active and backed up. Shared global resources remain."
  type        = bool
  default     = true
}

variable "enable_singapore_staging" {
  description = "Create parallel Singapore resources while US resources remain active for migration."
  type        = bool
  default     = false
}

variable "singapore_region" {
  description = "Destination region for the parallel Singapore migration resources."
  type        = string
  default     = "asia-southeast1"
}

variable "singapore_github_app_installation_id" {
  description = "GitHub App installation ID for the Singapore Cloud Build connection. Zero skips the connection."
  type        = number
  default     = 0
}

variable "singapore_github_token_version" {
  description = "Version number of the copied GitHub OAuth token in the Singapore-replicated secret."
  type        = string
  default     = "1"
}

variable "singapore_stage_backend_services" {
  description = "Backend services safe to stage in Singapore before the database cutover. Start with the ingesters; add other services deliberately."
  type        = set(string)
  default     = ["messaging-ingester", "payment-ingester", "messaging-service", "processing-service"]
  validation {
    condition = length(setsubtract(var.singapore_stage_backend_services, [
      "configuration-service", "messaging-service", "processing-service", "messaging-ingester", "payment-ingester"
    ])) == 0
    error_message = "Singapore staging can include only known backend service names."
  }
}

variable "singapore_build_triggers_enabled" {
  description = "Enable Singapore build and deploy triggers after the regional services are ready for cutover."
  type        = bool
  default     = false
}

variable "singapore_notification_scheduler_enabled" {
  description = "Start the Singapore notification schedule after the US schedule is paused and the job uses the promoted Singapore database."
  type        = bool
  default     = false
}

variable "singapore_sql_promoted" {
  description = "Set true only after the Singapore Cloud SQL replica has been promoted to a writable primary."
  type        = bool
  default     = false
}

variable "singapore_service_urls" {
  description = "Cloud Run URLs discovered after creating Singapore services; used to route service-to-service calls without resource cycles."
  type        = map(string)
  default     = {}
}

variable "singapore_queue_consumers_enabled" {
  description = "Enable Singapore Pub/Sub pull consumers only after the US consumers are stopped."
  type        = bool
  default     = false
}

variable "singapore_min_instances" {
  description = "Service-level minimum instances for Singapore Cloud Run services; zero while staging."
  type        = number
  default     = 0
  validation {
    condition     = var.singapore_min_instances >= 0 && var.singapore_min_instances <= 3
    error_message = "Singapore minimum instances must be between zero and three."
  }
}

variable "singapore_public_endpoints_enabled" {
  description = "Grant public invocation to Singapore browser and webhook endpoints after cutover."
  type        = bool
  default     = false
}

variable "us_queue_consumers_enabled" {
  description = "Turn off US Pub/Sub pull consumers before enabling the Singapore copies."
  type        = bool
  default     = true
}

variable "us_build_triggers_enabled" {
  description = "Turn off US build/deploy triggers before enabling Singapore triggers."
  type        = bool
  default     = true
}

variable "us_public_endpoints_enabled" {
  description = "Allow unauthenticated access to the existing US browser and webhook services. Turn off during Singapore database cutover."
  type        = bool
  default     = true
}

variable "us_legacy_messaging_ingester_public" {
  description = "Temporarily accept Meta callbacks at the old US messaging ingester URL during the Singapore webhook migration."
  type        = bool
  default     = false
}

variable "us_legacy_payment_ingester_public" {
  description = "Temporarily accept Xendit callbacks at the old US payment ingester URL during the Singapore webhook migration."
  type        = bool
  default     = false
}

variable "us_legacy_messaging_ingester_configuration_service_url" {
  description = "Configuration API used by the old US messaging webhook endpoint while forwarding callbacks to Singapore."
  type        = string
  default     = "https://configuration-service-gq6jjn4afq-uc.a.run.app/api"
}

variable "us_min_instances" {
  description = "Service-level minimum instances for the existing US Cloud Run services."
  type        = number
  default     = 1
  validation {
    condition     = var.us_min_instances >= 0 && var.us_min_instances <= 3
    error_message = "US minimum instances must be between zero and three."
  }
}

variable "pubsub_allowed_persistence_regions" {
  description = "Optional Pub/Sub message persistence regions. Set to [\"asia-southeast1\"] after the consumers move to Singapore."
  type        = list(string)
  default     = []
}

variable "bucket_name" {
  description = "Globally unique object bucket name; defaults to PROJECT_ID-app-objects."
  type        = string
  default     = ""
}

variable "service_images" {
  description = "Optional full image references for backend services. Services without an image use the Cloud Run hello placeholder until their Cloud Build trigger deploys an image."
  type        = map(string)
  default     = {}
  validation {
    condition = alltrue([
      for name, image in var.service_images :
      contains(["configuration-service", "messaging-service", "processing-service", "messaging-ingester", "payment-ingester"], name) && length(trimspace(image)) > 0
    ])
    error_message = "Use a known backend service name and a nonempty full image reference."
  }
}

variable "django_allowed_hosts" {
  description = "Comma-separated Django hostnames; the default accepts Cloud Run's run.app hostname. Add a custom domain when used."
  type        = string
  default     = ".run.app"
}

variable "frontend_configuration_service_url" {
  description = "Optional HTTPS /api root for the Firebase frontend. Set to the load balancer's trusted DNS hostname; empty uses the backend configuration API URL."
  type        = string
  default     = ""

  validation {
    condition     = var.frontend_configuration_service_url == "" || can(regex("^https://[^/]+/api/?$", var.frontend_configuration_service_url))
    error_message = "Use an HTTPS API root such as https://api.example.com/api, or leave it empty."
  }
}

variable "backend_configuration_service_url" {
  description = "Optional HTTPS /api root used by Singapore backend services and notification-job to reach configuration-service. Keep the load balancer URL until Cloud Run-to-Cloud Run VPC routing is ready, then use its run.app URL."
  type        = string
  default     = ""

  validation {
    condition     = var.backend_configuration_service_url == "" || can(regex("^https://[^/]+/api/?$", var.backend_configuration_service_url))
    error_message = "Use an HTTPS API root such as https://configuration-service.example.run.app/api, or leave it empty."
  }
}

variable "messaging_service_url" {
  description = "Root Cloud Run URL of the private messaging-service, without /api or a trailing slash."
  type        = string
  default     = "https://messaging-service-gq6jjn4afq-as.a.run.app"
}

variable "payment_ingester_url" {
  description = "Cloud Run URL used by messaging-service to create Xendit payment links."
  type        = string
  default     = "https://payment-ingester-gq6jjn4afq-as.a.run.app"
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

variable "github_connection_name" {
  description = "Name of the GitHub host connection created in Cloud Build (2nd gen) after installing the Cloud Build GitHub App."
  type        = string
  default     = "ansera"
}

variable "github_repository_name" {
  description = "Cloud Build linked-repository resource name."
  type        = string
  default     = "cs5224-project"
}

variable "github_repository_uri" {
  description = "HTTPS clone URL for the application repository."
  type        = string
  default     = "https://github.com/CodeGang7890/cs5224-project.git"
}

variable "firebase_hosting_site_id" {
  description = "Globally unique Firebase Hosting site ID; this determines the web.app/firebaseapp.com subdomains."
  type        = string
  default     = "cs5224-ansera"
}

variable "additional_browser_origins" {
  description = "Additional exact browser origins allowed to call the backend APIs, for example a custom HTTPS frontend domain."
  type        = list(string)
  default     = []
}

variable "github_branch_regex" {
  description = "Branch regex used by Cloud Build triggers."
  type        = string
  default     = "^main$"
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
      for name in var.ci_cd_services : contains(["configuration-service", "messaging-service", "processing-service", "messaging-ingester", "payment-ingester"], name)
    ])
    error_message = "CI/CD services must have a Dockerfile: configuration-service, messaging-service, processing-service, messaging-ingester, or payment-ingester."
  }
}

variable "notification_job_image" {
  description = "Container image used by the notification Cloud Run Job before its Cloud Build trigger deploys the application image."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "enable_notification_scheduler" {
  description = "Unpause the hourly Cloud Scheduler trigger after the notification-job image and database connection are verified."
  type        = bool
  default     = false
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
  description = "Backend runtime service accounts that can call Vertex AI. The chat workflow now runs in messaging-service."
  type        = set(string)
  default     = ["messaging-service"]
  validation {
    condition = alltrue([
      for name in var.vertex_ai_services : contains(["configuration-service", "messaging-service", "processing-service", "payment-ingester", "messaging-ingester"], name)
    ])
    error_message = "Vertex AI access must be granted to one of the five backend service identities."
  }
}

variable "vertex_ai_location" {
  description = "Vertex AI inference location. Gemini 3.5 Flash-Lite supports the global endpoint; choose a supported region if data residency is required."
  type        = string
  default     = "global"
}

variable "vertex_ai_model" {
  description = "Gemini model ID used by Vertex AI-enabled services."
  type        = string
  default     = "gemini-3.5-flash-lite"
}

variable "enable_mock_whatsapp" {
  description = "Create the mock-whatsapp Cloud Run service (mock-whatsapp.tf): a stand-in for WhatsApp / Meta for demos, one instance in the Singapore region."
  type        = bool
  default     = true
}

variable "whatsapp_replies_to" {
  description = "Where the Singapore configuration-service sends WhatsApp replies: \"mock\" (mock-whatsapp's fake Graph API; needs enable_mock_whatsapp) or \"meta\" (real WhatsApp)."
  type        = string
  default     = "mock"
  validation {
    condition     = contains(["mock", "meta"], var.whatsapp_replies_to)
    error_message = "whatsapp_replies_to must be \"mock\" or \"meta\"."
  }
}

variable "mock_whatsapp_allow_unauthenticated" {
  description = "Allow public access to mock-whatsapp even when replies go to Meta (it's public anyway while whatsapp_replies_to = \"mock\"). Anyone with its URL can chat as a customer of the sample businesses, which runs the LLM."
  type        = bool
  default     = false
}

variable "mock_whatsapp_image" {
  description = "Initial image for the mock-whatsapp Cloud Run service before Cloud Build deploys its Docker image."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "meta_app_id" {
  description = "Our Meta app's ID (App Dashboard), for WhatsApp Embedded Signup."
  type        = string
  default     = "2228337358565044"
}

variable "meta_embedded_signup_config_id" {
  description = "Facebook Login for Business configuration ID of the WhatsApp Embedded Signup configuration (frontend build). Empty: the Connect with Facebook button does nothing."
  type        = string
  default     = ""
}

variable "meta_app_secret_version" {
  description = "Version of the existing meta-app-secret Secret Manager secret used by configuration-service."
  type        = string
  default     = "3"
}

variable "meta_webhook_verify_token" {
  description = "Verify token configured in the Meta App Dashboard for this app's webhook. Set in ignored terraform.tfvars; do not commit it."
  type        = string
  sensitive   = true
  validation {
    condition     = length(trimspace(var.meta_webhook_verify_token)) > 0
    error_message = "Set meta_webhook_verify_token to the Meta app webhook verify token."
  }
}

variable "messaging_ingester_public_url" {
  description = "Public URL of messaging-ingester (webhook Callback URLs). Empty: its Cloud Run default URL."
  type        = string
  default     = ""
}

variable "alert_notification_email" {
  description = "Email address for Cloud Run HTTP error alert notifications. Leave blank to create incidents only in Cloud Monitoring."
  type        = string
  default     = ""
}
