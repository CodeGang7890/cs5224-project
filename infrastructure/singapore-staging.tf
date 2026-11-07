# Parallel resources for the US -> Singapore migration. The current US stack
# stays active until data has been copied and external callbacks are cut over.
locals {
  singapore_objects_bucket = "${local.objects_bucket}-sg"
}

resource "google_artifact_registry_repository" "singapore_apps" {
  count         = var.enable_singapore_staging ? 1 : 0
  repository_id = "apps"
  location      = var.singapore_region
  format        = "DOCKER"
  description   = "Backend container images in Singapore"
  depends_on    = [google_project_service.api]
  lifecycle { prevent_destroy = true }
}

resource "google_artifact_registry_repository_iam_member" "singapore_builder_writer" {
  count      = var.enable_singapore_staging ? 1 : 0
  project    = var.project_id
  location   = var.singapore_region
  repository = google_artifact_registry_repository.singapore_apps[0].name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.builder.email}"
}

# The OAuth payload was copied from the existing US regional secret outside
# Terraform, so its value is never stored in Terraform state.
resource "google_secret_manager_secret" "singapore_github_oauth" {
  count     = var.enable_singapore_staging && var.enable_ci_cd && var.singapore_github_app_installation_id > 0 ? 1 : 0
  secret_id = "ansera-github-oauthtoken-sg"
  replication {
    user_managed {
      replicas { location = var.singapore_region }
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret_iam_member" "singapore_github_oauth_access" {
  count     = var.enable_singapore_staging && var.enable_ci_cd && var.singapore_github_app_installation_id > 0 ? 1 : 0
  secret_id = google_secret_manager_secret.singapore_github_oauth[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}

resource "google_cloudbuildv2_connection" "singapore_github" {
  count    = var.enable_singapore_staging && var.enable_ci_cd && var.singapore_github_app_installation_id > 0 ? 1 : 0
  project  = var.project_id
  location = var.singapore_region
  name     = var.github_connection_name
  github_config {
    app_installation_id = var.singapore_github_app_installation_id
    authorizer_credential {
      oauth_token_secret_version = "${google_secret_manager_secret.singapore_github_oauth[0].id}/versions/${var.singapore_github_token_version}"
    }
  }
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [google_secret_manager_secret_iam_member.singapore_github_oauth_access]
}

resource "google_cloudbuildv2_repository" "singapore_github" {
  count             = var.enable_singapore_staging && var.enable_ci_cd && var.singapore_github_app_installation_id > 0 ? 1 : 0
  project           = var.project_id
  location          = var.singapore_region
  name              = var.github_repository_name
  parent_connection = google_cloudbuildv2_connection.singapore_github[0].id
  remote_uri        = var.github_repository_uri
  lifecycle { prevent_destroy = true }
}

resource "google_storage_bucket" "singapore_objects" {
  count                       = var.enable_singapore_staging ? 1 : 0
  name                        = local.singapore_objects_bucket
  location                    = upper(var.singapore_region)
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  depends_on                  = [google_project_service.api]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "singapore_processing_object_user" {
  count  = var.enable_singapore_staging ? 1 : 0
  bucket = google_storage_bucket.singapore_objects[0].name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime["processing-service"].email}"
}

resource "google_storage_bucket_iam_member" "singapore_messaging_object_user" {
  count  = var.enable_singapore_staging ? 1 : 0
  bucket = google_storage_bucket.singapore_objects[0].name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime["messaging-service"].email}"
}

resource "google_sql_database_instance" "singapore_replica" {
  count                = var.enable_singapore_staging && var.enable_cloud_sql ? 1 : 0
  name                 = "main-postgres-sg"
  region               = var.singapore_region
  database_version     = "POSTGRES_17"
  master_instance_name = google_sql_database_instance.main[0].name
  instance_type        = "READ_REPLICA_INSTANCE"
  deletion_protection  = true

  settings {
    edition           = "ENTERPRISE"
    tier              = var.sql_tier
    availability_type = "ZONAL"
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = false
    backup_configuration { enabled = var.singapore_sql_promoted }
    ip_configuration { ipv4_enabled = true }
  }

  lifecycle {
    prevent_destroy = true
    # Promotion removes these replica attributes. Keep the promoted primary
    # in the same Terraform address; never replace it to recreate a replica.
    ignore_changes = [master_instance_name, instance_type]
  }
}
