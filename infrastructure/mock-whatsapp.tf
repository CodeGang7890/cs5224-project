# mock_whatsapp (../mock_whatsapp): a stand-in for WhatsApp / Meta, to demo the chat without a real
# WhatsApp account. One Cloud Run service in Singapore, off unless enable_mock_whatsapp.
# - Exactly one instance (min = max = 1): its conversations live in a SQLite file inside the
#   container (and photo / document details in memory), so a second instance would show a different
#   history, and a reply could reach the instance the page isn't polling. They're lost when the
#   instance restarts or a new revision is deployed (intended: it's a demo).
# - Its webhooks go to the Singapore messaging-ingester (INGESTER_URL), signed with the dummy App
#   Secrets in mock_whatsapp/businesses.json: only businesses whose WhatsApp connection in the
#   database has those credentials (the sample fixtures) accept them.
# - Replies: with whatsapp_replies_to = "mock" (the default), the Singapore configuration-service
#   sends every WhatsApp reply to its fake Graph API (WHATSAPP_REPLIES_TO=mock,
#   MOCK_WHATSAPP_GRAPH_API_URL=<url>/v26.0; singapore-run.tf), not to Meta; "meta" sends them to Meta.
#   Connecting WhatsApp (Embedded Signup) always uses Meta.
# - The Invoker IAM binding permits unauthenticated calls when replies use the mock or when
#   mock_whatsapp_allow_unauthenticated is set. Ingress remains internal-and-load-balancer,
#   matching the existing Cloud Run service; a direct run.app call still needs a valid route.

locals {
  replies_to_mock_whatsapp    = var.enable_mock_whatsapp && var.whatsapp_replies_to == "mock"
  mock_whatsapp_graph_api_url = local.replies_to_mock_whatsapp ? "https://mock-whatsapp-${data.google_project.current.number}.${var.singapore_region}.run.app/v26.0" : ""
}

resource "google_service_account" "mock_whatsapp" {
  count        = var.enable_mock_whatsapp ? 1 : 0
  account_id   = "mock-whatsapp-runtime"
  display_name = "mock_whatsapp Cloud Run runtime"
  depends_on   = [google_project_service.api]
}

resource "google_cloud_run_v2_service" "mock_whatsapp" {
  count               = var.enable_mock_whatsapp ? 1 : 0
  name                = "mock-whatsapp"
  location            = var.singapore_region
  deletion_protection = true
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  scaling {
    min_instance_count = 1
    max_instance_count = 1
  }

  template {
    # Direct VPC egress makes the ingress-restricted ingester reachable.
    service_account                  = google_service_account.mock_whatsapp[0].email
    max_instance_request_concurrency = 20 # the page polls every 1.5 s per open tab
    dynamic "vpc_access" {
      for_each = var.enable_singapore_staging ? [1] : []
      content {
        egress = "ALL_TRAFFIC"
        network_interfaces {
          network    = data.google_compute_network.singapore_egress[0].name
          subnetwork = google_compute_subnetwork.singapore_egress[0].name
        }
      }
    }
    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image = var.mock_whatsapp_image # Cloud Build deploys the real image (cloudbuild-mock-whatsapp.yaml)
      ports { container_port = 9000 } # Cloud Run sets PORT=9000; the Dockerfile listens on $PORT
      resources {
        limits   = { cpu = "1", memory = "512Mi" } # the SQLite file is in memory too
        cpu_idle = true
      }
      env {
        name  = "INGESTER_URL"
        value = trimsuffix(local.singapore_messaging_ingester_public_url, "/")
      }
      env {
        name  = "MOCK_WHATSAPP_PUBLIC_PATH_PREFIX"
        value = var.mock_whatsapp_public_path_prefix
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [google_project_service.api, google_compute_router_nat.singapore_egress]
}

resource "google_cloud_run_v2_service_iam_member" "mock_whatsapp_public" {
  count    = var.enable_mock_whatsapp && (var.mock_whatsapp_allow_unauthenticated || local.replies_to_mock_whatsapp) ? 1 : 0
  project  = var.project_id
  location = var.singapore_region
  name     = google_cloud_run_v2_service.mock_whatsapp[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Cloud Build deploys its image as this runtime account.
resource "google_service_account_iam_member" "builder_mock_whatsapp_act_as" {
  count              = var.enable_mock_whatsapp && var.enable_ci_cd ? 1 : 0
  service_account_id = google_service_account.mock_whatsapp[0].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder.email}"
}

# Builds mock_whatsapp/ on pushes to the main branch and deploys it (its own file: the folder is
# mock_whatsapp, the service mock-whatsapp, so the shared cloudbuild.yaml doesn't fit).
resource "google_cloudbuild_trigger" "mock_whatsapp" {
  count           = var.enable_mock_whatsapp && var.enable_singapore_staging && var.enable_ci_cd && var.singapore_github_app_installation_id > 0 ? 1 : 0
  name            = "mock-whatsapp-sg-main"
  location        = var.singapore_region
  disabled        = !var.singapore_build_triggers_enabled
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild-mock-whatsapp.yaml"
  included_files  = ["mock_whatsapp/**", "infrastructure/cloudbuild-mock-whatsapp.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.singapore_github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _REGION                  = var.singapore_region
    _PROJECT_ID              = var.project_id
    _REPOSITORY              = google_artifact_registry_repository.singapore_apps[0].repository_id
    _RUNTIME_SERVICE_ACCOUNT = google_service_account.mock_whatsapp[0].email
  }

  depends_on = [google_service_account_iam_member.builder_mock_whatsapp_act_as]
}
