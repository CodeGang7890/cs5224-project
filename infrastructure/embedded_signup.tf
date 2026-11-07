# WhatsApp Embedded Signup: businesses connect WhatsApp through our Meta app ("Connect with Facebook").
# configuration-service needs the app's ID and App Secret, and the verify token of the app's own webhook
# (messaging-ingester /webhook). Terraform generates the verify token; add the App Secret once, before
# the first apply (README):
#   gcloud secrets versions add meta-app-secret --data-file=…

data "google_project" "current" {
  project_id = var.project_id
}

locals {
  # Cloud Run's default URL, https://<service>-<project number>.<region>.run.app (the service can't
  # reference its own instances' `uri`). Override for a custom domain or load balancer.
  messaging_ingester_public_url = (
    var.messaging_ingester_public_url != ""
    ? trimsuffix(var.messaging_ingester_public_url, "/")
    : "https://messaging-ingester-${data.google_project.current.number}.${var.region}.run.app"
  )
  meta_secrets = {
    META_APP_SECRET               = "meta-app-secret"
    META_APP_WEBHOOK_VERIFY_TOKEN = "meta-webhook-verify-token"
  }
}

resource "google_secret_manager_secret_version" "meta_webhook_verify_token" {
  secret      = google_secret_manager_secret.app["meta-webhook-verify-token"].id
  secret_data = var.meta_webhook_verify_token
}

resource "google_secret_manager_secret_iam_member" "configuration_meta" {
  for_each  = toset(values(local.meta_secrets))
  secret_id = each.key == "meta-app-secret" ? "projects/${var.project_id}/secrets/meta-app-secret" : google_secret_manager_secret.app[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["configuration-service"].email}"
}
