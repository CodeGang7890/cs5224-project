locals {
  objects_bucket     = var.bucket_name != "" ? var.bucket_name : "${var.project_id}-app-objects"
  service_names      = toset(["configuration-service", "messaging-service", "processing-service", "payment-ingester", "messaging-ingester"])
  runtime_identities = setunion(local.service_names, toset(["notification-job"]))
}

resource "google_artifact_registry_repository" "apps" {
  repository_id = "apps"
  location      = var.region
  format        = "DOCKER"
  description   = "Backend container images"
  depends_on    = [google_project_service.api]
}

resource "google_storage_bucket" "objects" {
  name                        = local.objects_bucket
  location                    = upper(var.region)
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  depends_on                  = [google_project_service.api]
}

resource "google_pubsub_topic" "queue" {
  for_each   = toset(["payment-queue", "messaging-queue", "notification-tick"])
  name       = each.key
  depends_on = [google_project_service.api]
}

resource "google_pubsub_subscription" "queue" {
  for_each                   = toset(["payment-queue", "messaging-queue", "notification-tick"])
  name                       = "${each.key}-worker"
  topic                      = google_pubsub_topic.queue[each.key].id
  ack_deadline_seconds       = 30
  message_retention_duration = "86400s"
}

resource "google_secret_manager_secret" "app" {
  for_each = toset(["django-secret-key","internal-api-key","jwt-signing-key","llm-api-key","whatsapp-token","xendit-api-key","meta-app-secret","meta-webhook-verify-token"])
  secret_id = each.key
  replication {
    auto {}
  }
  depends_on = [google_project_service.api]
}

resource "google_dns_managed_zone" "app" {
  count       = var.dns_domain == "" ? 0 : 1
  name        = "app-zone"
  dns_name    = "${trimsuffix(var.dns_domain, ".")}."
  description = "Public DNS for the prototype"
  depends_on  = [google_project_service.api]
}

resource "google_dns_record_set" "custom" {
  for_each     = var.dns_domain == "" ? {} : var.dns_records
  managed_zone = google_dns_managed_zone.app[0].name
  name         = each.key == "@" ? google_dns_managed_zone.app[0].dns_name : "${each.key}.${google_dns_managed_zone.app[0].dns_name}"
  type         = each.value.type
  ttl          = each.value.ttl
  rrdatas      = each.value.rrdatas
}

resource "google_firebase_project" "app" {
  provider   = google-beta
  count      = var.enable_firebase ? 1 : 0
  project    = var.project_id
  depends_on = [google_project_service.api]
}

resource "google_firebase_web_app" "frontend" {
  provider     = google-beta
  count        = var.enable_firebase ? 1 : 0
  project      = var.project_id
  display_name = "Ansera"
  depends_on   = [google_firebase_project.app]
}

resource "google_firebase_hosting_site" "frontend" {
  provider = google-beta
  count    = var.enable_firebase ? 1 : 0
  project  = var.project_id
  site_id  = var.firebase_hosting_site_id
  app_id   = google_firebase_web_app.frontend[0].app_id

  deletion_policy = "PREVENT"
  depends_on      = [google_project_service.api]
}
