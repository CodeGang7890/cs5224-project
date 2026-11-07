# Logging in with Google / Facebook: Google Cloud Identity Platform (Firebase Authentication). frontend-app
# runs the provider's popup with the Firebase JS SDK (the Firebase web app's config, below) and sends the
# ID token to configuration-service (FIREBASE_PROJECT_ID), which issues our usual JWTs. Username / password
# logins don't use it. On with Firebase (enable_firebase); enabling Identity Platform can't be undone.
#
# The providers (Google, Facebook) are set up only in the console (Identity Platform → Providers; README),
# with OAuth clients made by hand, so their secrets stay out of Terraform. Terraform owns the authorized
# domains: add more here, not in the console (apply would remove them).

locals {
  # The login popup's auth domain: the Hosting site frontend-app is served from (its /__/auth/handler),
  # as Firebase recommends, so the popup is same-site with the app (no third-party cookies needed).
  identity_auth_domain = "${var.firebase_hosting_site_id}.web.app"
  # Pages allowed to run the login popup: local dev, and the Firebase Hosting site.
  identity_authorized_domains = [
    "localhost",
    "${var.project_id}.firebaseapp.com",
    "${var.project_id}.web.app",
    "${var.firebase_hosting_site_id}.web.app",
    "${var.firebase_hosting_site_id}.firebaseapp.com",
  ]
}

resource "google_identity_platform_config" "auth" {
  count              = var.enable_firebase ? 1 : 0
  project            = var.project_id
  authorized_domains = distinct(local.identity_authorized_domains)

  sign_in {
    # One account per email: logging in with Facebook with an email that already uses Google asks to
    # use Google (the frontend says so).
    allow_duplicate_emails = false
    email {
      enabled           = false
      password_required = false
    }
    phone_number {
      enabled = false
    }
  }

  depends_on = [google_project_service.api, google_firebase_project.app]
}

# The Firebase web app's config (its apiKey): built into frontend-app (build.tf) and shown by
# `terraform output firebase_web_config` for local .env files. The API key isn't a secret.
data "google_firebase_web_app_config" "frontend" {
  provider   = google-beta
  count      = var.enable_firebase ? 1 : 0
  project    = var.project_id
  web_app_id = google_firebase_web_app.frontend[0].app_id
}
