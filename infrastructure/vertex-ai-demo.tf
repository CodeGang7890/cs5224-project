resource "google_service_account" "vertex_ai_demo" {
  count        = var.enable_vertex_ai_demo ? 1 : 0
  account_id   = "vertex-ai-demo-runtime"
  display_name = "Vertex AI demo Cloud Run runtime"
  depends_on   = [google_project_service.api]
}

resource "google_project_iam_member" "vertex_ai_demo_user" {
  count   = var.enable_vertex_ai_demo ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.vertex_ai_demo[0].email}"
}

resource "google_cloud_run_v2_service" "vertex_ai_demo" {
  count               = var.enable_vertex_ai_demo && !var.retire_us_resources ? 1 : 0
  name                = "vertex-ai-demo"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  scaling {
    min_instance_count = var.us_min_instances
    max_instance_count = 3
  }

  template {
    service_account                  = google_service_account.vertex_ai_demo[0].email
    max_instance_request_concurrency = 10
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.vertex_ai_demo_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.vertex_ai_location
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "True"
      }
      env {
        name  = "LLM_MODEL"
        value = var.vertex_ai_model
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.api,
    google_project_iam_member.vertex_ai_demo_user,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "vertex_ai_demo_public" {
  count    = var.enable_vertex_ai_demo && var.vertex_ai_demo_allow_unauthenticated && var.us_vertex_ai_demo_public && !var.retire_us_resources ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.vertex_ai_demo[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
