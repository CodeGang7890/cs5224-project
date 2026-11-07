resource "google_cloud_run_v2_job" "notification" {
  count               = var.enable_cloud_sql && !var.retire_us_resources ? 1 : 0
  name                = "notification-job"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.runtime["notification-job"].email
      timeout         = "900s"
      max_retries     = 1

      containers {
        image = var.notification_job_image

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
          value = "/cloudsql/${google_sql_database_instance.main[0].connection_name}"
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
          instances = [google_sql_database_instance.main[0].connection_name]
        }
      }
    }
  }

  lifecycle {
    # The notification-job Cloud Build trigger updates the deployed image.
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.api,
    google_project_iam_member.sql_client,
    google_secret_manager_secret_iam_member.notification_sql_password,
  ]
}

resource "google_service_account" "scheduler_invoker" {
  count        = var.enable_cloud_sql ? 1 : 0
  account_id   = "notification-scheduler"
  display_name = "Cloud Scheduler notification job invoker"
  depends_on   = [google_project_service.api]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  count    = var.enable_cloud_sql && !var.retire_us_resources ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.notification[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_invoker[0].email}"
}

resource "google_cloud_scheduler_job" "notification_tick" {
  count            = var.enable_cloud_sql && !var.retire_us_resources ? 1 : 0
  name             = "notification-tick"
  region           = var.region
  schedule         = var.notification_schedule
  time_zone        = "Etc/UTC"
  paused           = !var.enable_notification_scheduler
  attempt_deadline = "320s"
  description      = "Runs the notification Cloud Run Job on its hourly reminder schedule."

  retry_config {
    retry_count = 3
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.notification[0].name}:run"
    body        = base64encode("{}")
    headers = {
      "Content-Type" = "application/json"
    }

    oauth_token {
      service_account_email = google_service_account.scheduler_invoker[0].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.api,
    google_cloud_run_v2_job.notification,
    google_cloud_run_v2_job_iam_member.scheduler_invoker,
  ]
}

resource "google_secret_manager_secret_iam_member" "notification_sql_password" {
  count     = var.enable_cloud_sql ? 1 : 0
  secret_id = google_secret_manager_secret.sql_password[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["notification-job"].email}"
}
