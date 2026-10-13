output "artifact_registry_path" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.apps.repository_id}"
}

output "object_bucket" {
  value = google_storage_bucket.objects.name
}

output "cloud_run_urls" {
  value = { for name, service in google_cloud_run_v2_service.backend : name => service.uri }
}

output "vertex_ai_demo_url" {
  value = var.enable_vertex_ai_demo ? google_cloud_run_v2_service.vertex_ai_demo[0].uri : null
}

output "vertex_ai_demo_service_account" {
  value = var.enable_vertex_ai_demo ? google_service_account.vertex_ai_demo[0].email : null
}

output "notification_job_name" {
  value = var.enable_cloud_sql ? google_cloud_run_v2_job.notification[0].name : null
}

output "pubsub_topics" {
  value = { for name, topic in google_pubsub_topic.queue : name => topic.id }
}

output "sql_connection_name" {
  value = var.enable_cloud_sql ? google_sql_database_instance.main[0].connection_name : null
}

output "dns_nameservers" {
  value = var.dns_domain != "" ? google_dns_managed_zone.app[0].name_servers : []
}

output "firebase_web_app_id" {
  value = var.enable_firebase ? google_firebase_web_app.frontend[0].app_id : null
}

output "firebase_hosting_url" {
  value = var.enable_firebase ? google_firebase_hosting_site.frontend[0].default_url : null
}
