# The parallel Singapore notification job is never scheduled until cutover.
resource "google_cloud_run_v2_job" "singapore_notification" {
  count               = var.enable_singapore_staging && var.enable_cloud_sql ? 1 : 0
  name                = "notification-job"
  location            = var.singapore_region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.runtime["notification-job"].email
      timeout         = "900s"
      max_retries     = 1

      containers {
        image = "asia-southeast1-docker.pkg.dev/${var.project_id}/apps/notification-job:f40f292"

        env {
          name  = "POSTGRES_DB"
          value = "configuration_service"
        }
        env {
          name  = "POSTGRES_USER"
          value = "app"
        }
        env {
          name  = "POSTGRES_HOST"
          value = "/cloudsql/${local.singapore_sql_connection_name}"
        }
        env {
          name  = "POSTGRES_PORT"
          value = "5432"
        }
        env {
          name = "POSTGRES_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.sql_password[0].secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [local.singapore_sql_connection_name]
        }
      }
    }
  }

  lifecycle {
    # The notification-job Cloud Build trigger updates the deployed image.
    prevent_destroy = true
    ignore_changes  = [template[0].template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.api,
    google_project_iam_member.sql_client,
    google_secret_manager_secret_iam_member.notification_sql_password,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "singapore_scheduler_invoker" {
  count    = var.enable_singapore_staging && var.enable_cloud_sql ? 1 : 0
  project  = var.project_id
  location = var.singapore_region
  name     = google_cloud_run_v2_job.singapore_notification[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_invoker[0].email}"
}

resource "google_cloud_scheduler_job" "singapore_notification_tick" {
  count            = var.enable_singapore_staging && var.enable_cloud_sql ? 1 : 0
  name             = "notification-tick"
  region           = var.singapore_region
  schedule         = var.notification_schedule
  time_zone        = "Etc/UTC"
  paused           = !var.singapore_notification_scheduler_enabled
  attempt_deadline = "320s"
  description      = "Runs the Singapore notification Cloud Run Job after regional cutover."

  retry_config { retry_count = 3 }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.singapore_region}/jobs/${google_cloud_run_v2_job.singapore_notification[0].name}:run"
    body        = base64encode("{}")
    headers = {
      "Content-Type" = "application/json"
    }
    oauth_token {
      service_account_email = google_service_account.scheduler_invoker[0].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.singapore_scheduler_invoker]
  lifecycle { prevent_destroy = true }
}

