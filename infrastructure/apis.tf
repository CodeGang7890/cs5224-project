locals {
  apis = toset(concat([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
  ], var.enable_cloud_sql ? ["sqladmin.googleapis.com"] : [], var.dns_domain != "" ? ["dns.googleapis.com"] : [], var.enable_firebase ? ["firebase.googleapis.com", "firebasehosting.googleapis.com", "identitytoolkit.googleapis.com"] : [], var.enable_vertex_ai ? ["aiplatform.googleapis.com"] : []))
}

resource "google_project_service" "api" {
  for_each           = local.apis
  service            = each.key
  disable_on_destroy = false
}
