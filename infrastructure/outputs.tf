output "service_urls" {
  description = "Public URL of each Cloud Run service."
  value       = { for name, svc in google_cloud_run_v2_service.services : name => svc.uri }
}

output "artifact_registry" {
  description = "Push images here as <registry>/<service>:<tag>."
  value       = local.registry
}

output "sql_connection_name" {
  description = "Cloud SQL instance connection name (used for the /cloudsql/<name> socket)."
  value       = google_sql_database_instance.main.connection_name
}

output "db_password_secret" {
  description = "Secret Manager secret holding the database password."
  value       = google_secret_manager_secret.db_password.secret_id
}
