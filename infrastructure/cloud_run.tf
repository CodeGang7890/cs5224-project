locals {
  registry = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.apps.repository_id}"

  # Service name => max instances.
  services = {
    "configuration-service" = 1
    "messaging-service"     = 2
    "processing-service"    = 1
    "payment-ingester"      = 1
    "messaging-ingester"    = 1
  }
}

# Shared runtime identity, so services don't depend on the default Compute Engine account.
resource "google_service_account" "cloud_run" {
  account_id   = "cloud-run-runtime"
  display_name = "Cloud Run runtime"

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "services" {
  for_each = local.services

  name     = each.key
  location = var.region

  # Lets `terraform destroy` delete the service.
  deletion_protection = false

  # Accept traffic from anywhere, and skip the IAM invoker check so anyone can call it.
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = true

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = 0
      max_instance_count = each.value
    }

    # No vpc_access block: egress goes straight to the internet, unrestricted.

    containers {
      image = (
        lookup(var.image_tags, each.key, "") != ""
        ? "${local.registry}/${each.key}:${var.image_tags[each.key]}"
        : var.placeholder_image
      )

      resources {
        # 1 vCPU / 512Mi is the smallest size without restrictions: under 1 vCPU forces
        # concurrency 1, and the 2nd-gen environment needs at least 512Mi.
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # Only bill CPU while handling requests.
        cpu_idle = true
      }
    }
  }
}
