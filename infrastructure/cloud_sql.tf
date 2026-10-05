resource "random_password" "db" {
  length = 32
  # Alphanumeric only, so the password never needs escaping in connection strings.
  special = false
}

resource "google_sql_database_instance" "main" {
  name             = "main-postgres"
  database_version = "POSTGRES_17"
  region           = var.region

  # Lets `terraform destroy` delete the instance. Turn on once it holds real data.
  deletion_protection = false

  settings {
    # Shared-core tiers like db-f1-micro only exist on the ENTERPRISE edition, and
    # Postgres 16+ defaults to ENTERPRISE_PLUS, so the edition must be explicit.
    edition           = "ENTERPRISE"
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = false

    backup_configuration {
      enabled = false
    }

    ip_configuration {
      # Public IP with no authorized networks: reachable only through the
      # Cloud SQL connector (e.g. Cloud Run's /cloudsql mount), not directly.
      ipv4_enabled = true
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "configuration_service" {
  name     = "configuration_service"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}
