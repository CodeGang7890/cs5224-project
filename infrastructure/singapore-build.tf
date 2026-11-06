# These triggers are created disabled. Enable them only after the matching
# Singapore services and job exist, and disable the US deployment triggers.
resource "google_cloudbuild_trigger" "singapore_backend" {
  for_each        = var.enable_singapore_staging && var.enable_ci_cd && var.singapore_github_app_installation_id > 0 ? var.ci_cd_services : toset([])
  name            = "${each.key}-sg-main"
  location        = var.singapore_region
  disabled        = !var.singapore_build_triggers_enabled
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild.yaml"
  included_files  = ["${each.key}/**", "infrastructure/cloudbuild.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.singapore_github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _REGION     = var.singapore_region
    _PROJECT_ID = var.project_id
    _REPOSITORY = google_artifact_registry_repository.singapore_apps[0].repository_id
    _SERVICE    = each.key
  }

  depends_on = [google_artifact_registry_repository_iam_member.singapore_builder_writer]
  lifecycle { prevent_destroy = true }
}

resource "google_cloudbuild_trigger" "singapore_notification_job" {
  count           = var.enable_singapore_staging && var.enable_ci_cd && var.enable_cloud_sql && var.singapore_github_app_installation_id > 0 ? 1 : 0
  name            = "notification-job-sg-main"
  location        = var.singapore_region
  disabled        = !var.singapore_build_triggers_enabled
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild-job.yaml"
  included_files  = ["notification-job/**", "infrastructure/cloudbuild-job.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.singapore_github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _REGION     = var.singapore_region
    _PROJECT_ID = var.project_id
    _REPOSITORY = google_artifact_registry_repository.singapore_apps[0].repository_id
  }
  lifecycle { prevent_destroy = true }
}

resource "google_cloudbuild_trigger" "singapore_vertex_ai_demo" {
  count           = var.enable_singapore_staging && var.enable_ci_cd && var.enable_vertex_ai_demo && var.singapore_github_app_installation_id > 0 ? 1 : 0
  name            = "vertex-ai-demo-sg-main"
  location        = var.singapore_region
  disabled        = !var.singapore_build_triggers_enabled
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild-vertex-ai-demo.yaml"
  included_files  = ["vertex-ai-demo/**", "infrastructure/cloudbuild-vertex-ai-demo.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.singapore_github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _REGION                  = var.singapore_region
    _PROJECT_ID              = var.project_id
    _REPOSITORY              = google_artifact_registry_repository.singapore_apps[0].repository_id
    _RUNTIME_SERVICE_ACCOUNT = google_service_account.vertex_ai_demo[0].email
  }
  lifecycle { prevent_destroy = true }
}

resource "google_cloudbuild_trigger" "singapore_frontend_hosting" {
  count           = var.enable_singapore_staging && var.enable_ci_cd && var.enable_firebase && var.singapore_github_app_installation_id > 0 ? 1 : 0
  name            = "frontend-hosting-sg-main"
  location        = var.singapore_region
  disabled        = !var.singapore_build_triggers_enabled
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild-frontend.yaml"
  included_files  = ["frontend-app/**", "infrastructure/firebase.json", "infrastructure/cloudbuild-frontend.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.singapore_github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _PROJECT_ID                = var.project_id
    _META_APP_ID               = var.meta_app_id
    _META_CONFIG_ID            = var.meta_embedded_signup_config_id
    _FIREBASE_API_KEY          = try(data.google_firebase_web_app_config.frontend[0].api_key, "")
    _FIREBASE_AUTH_DOMAIN      = local.identity_auth_domain
    _CONFIGURATION_SERVICE_URL = local.singapore_configuration_api_url
  }
  lifecycle { prevent_destroy = true }
}
