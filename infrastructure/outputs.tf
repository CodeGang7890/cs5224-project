output "artifact_registry_path" {
  value = var.singapore_build_triggers_enabled ? "${var.singapore_region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.singapore_apps[0].repository_id}" : "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.apps.repository_id}"
}

output "active_region" {
  value = var.singapore_public_endpoints_enabled ? var.singapore_region : var.region
}

output "singapore_staging" {
  description = "Singapore resources staged alongside the active US deployment."
  value = var.enable_singapore_staging ? {
    artifact_registry_path = "${var.singapore_region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.singapore_apps[0].repository_id}"
    object_bucket          = google_storage_bucket.singapore_objects[0].name
    sql_connection_name    = var.enable_cloud_sql ? google_sql_database_instance.singapore_replica[0].connection_name : null
    cloud_run_urls         = { for name, service in google_cloud_run_v2_service.singapore_backend : name => service.uri }
    vertex_ai_demo_url     = var.enable_vertex_ai_demo ? google_cloud_run_v2_service.singapore_vertex_ai_demo[0].uri : null
    notification_job_name  = var.enable_cloud_sql ? google_cloud_run_v2_job.singapore_notification[0].name : null
  } : null
}

output "object_bucket" {
  value = var.singapore_sql_promoted ? google_storage_bucket.singapore_objects[0].name : google_storage_bucket.objects.name
}

output "cloud_run_urls" {
  value = var.singapore_public_endpoints_enabled ? { for name, service in google_cloud_run_v2_service.singapore_backend : name => service.uri } : { for name, service in google_cloud_run_v2_service.backend : name => service.uri }
}

output "vertex_ai_demo_url" {
  value = var.enable_vertex_ai_demo ? (var.singapore_public_endpoints_enabled ? google_cloud_run_v2_service.singapore_vertex_ai_demo[0].uri : google_cloud_run_v2_service.vertex_ai_demo[0].uri) : null
}

output "vertex_ai_demo_service_account" {
  value = var.enable_vertex_ai_demo ? google_service_account.vertex_ai_demo[0].email : null
}

output "notification_job_name" {
  value = var.enable_cloud_sql ? google_cloud_run_v2_job.notification[0].name : null
}

output "notification_job_region" {
  value = var.singapore_notification_scheduler_enabled ? var.singapore_region : var.region
}

output "pubsub_topics" {
  value = { for name, topic in google_pubsub_topic.queue : name => topic.id }
}

output "sql_connection_name" {
  value = var.enable_cloud_sql ? (var.singapore_sql_promoted ? google_sql_database_instance.singapore_replica[0].connection_name : google_sql_database_instance.main[0].connection_name) : null
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

output "meta_webhook_verify_token" {
  description = "Verify token for our Meta app's webhook (App Dashboard → WhatsApp → Configuration): terraform output -raw meta_webhook_verify_token"
  value       = var.meta_webhook_verify_token
  sensitive   = true
}

output "meta_app_webhook_url" {
  description = "Callback URL for our Meta app's webhook (App Dashboard → WhatsApp → Configuration)."
  value       = "${var.singapore_public_endpoints_enabled ? local.singapore_messaging_ingester_public_url : local.messaging_ingester_public_url}/webhook"
}

output "firebase_web_config" {
  description = "frontend-app's VITE_FIREBASE_API_KEY / _AUTH_DOMAIN / _PROJECT_ID, for logging in with Google / Facebook (e.g. in a local .env)."
  value = var.enable_firebase ? {
    VITE_FIREBASE_API_KEY     = try(data.google_firebase_web_app_config.frontend[0].api_key, "")
    VITE_FIREBASE_AUTH_DOMAIN = local.identity_auth_domain
    VITE_FIREBASE_PROJECT_ID  = var.project_id
  } : null
}

output "identity_oauth_redirect_uri" {
  description = "Redirect URI to allow in the Google OAuth client and the Meta app's Facebook Login settings."
  value       = "https://${local.identity_auth_domain}/__/auth/handler"
}
