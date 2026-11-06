resource "random_password" "sql" {
  count   = var.enable_cloud_sql ? 1 : 0
  length  = 32
  special = false
}

resource "google_sql_database_instance" "main" {
  count               = var.enable_cloud_sql ? 1 : 0
  name                = "main-postgres"
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = false

  settings {
    edition           = "ENTERPRISE"
    tier              = var.sql_tier
    availability_type = "ZONAL"
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = false
    backup_configuration { enabled = true }
    ip_configuration { ipv4_enabled = true }
  }
  depends_on = [google_project_service.api]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_sql_database" "configuration" {
  count    = var.enable_cloud_sql ? 1 : 0
  name     = "configuration_service"
  instance = google_sql_database_instance.main[0].name
}

resource "google_sql_user" "app" {
  count    = var.enable_cloud_sql ? 1 : 0
  name     = "app"
  instance = google_sql_database_instance.main[0].name
  password = random_password.sql[0].result
}

resource "google_secret_manager_secret" "sql_password" {
  count     = var.enable_cloud_sql ? 1 : 0
  secret_id = "cloud-sql-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.api]
}

resource "google_secret_manager_secret_version" "sql_password" {
  count       = var.enable_cloud_sql ? 1 : 0
  secret      = google_secret_manager_secret.sql_password[0].id
  secret_data = random_password.sql[0].result
}
