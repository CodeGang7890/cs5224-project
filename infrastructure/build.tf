resource "google_service_account" "builder" {
  account_id   = "cloud-build-deployer"
  display_name = "Cloud Build deployer"
  depends_on   = [google_project_service.api]
}

resource "google_artifact_registry_repository_iam_member" "builder_writer" {
  location   = var.region
  repository = google_artifact_registry_repository.apps.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_project_iam_member" "builder_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_project_iam_member" "builder_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "builder_act_as" {
  for_each           = var.enable_ci_cd ? var.ci_cd_services : toset([])
  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "builder_notification_act_as" {
  count              = var.enable_ci_cd && var.enable_cloud_sql ? 1 : 0
  service_account_id = google_service_account.runtime["notification-job"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_service_account_iam_member" "builder_vertex_ai_demo_act_as" {
  count              = var.enable_ci_cd && var.enable_vertex_ai_demo ? 1 : 0
  service_account_id = google_service_account.vertex_ai_demo[0].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_project_iam_member" "builder_firebase_hosting_admin" {
  count   = var.enable_ci_cd && var.enable_firebase ? 1 : 0
  project = var.project_id
  role    = "roles/firebasehosting.admin"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

# `firebase deploy` (firebase-tools 15.34.1+) checks that the Hosting API is enabled
# (serviceusage.services.get), which Firebase Hosting Admin doesn't include.
resource "google_project_iam_member" "builder_service_usage_consumer" {
  count   = var.enable_ci_cd && var.enable_firebase ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_cloudbuildv2_repository" "github" {
  count             = var.enable_ci_cd && var.github_connection_name != "" ? 1 : 0
  project           = var.project_id
  location          = var.region
  name              = var.github_repository_name
  parent_connection = "projects/${var.project_id}/locations/${var.region}/connections/${var.github_connection_name}"
  remote_uri        = var.github_repository_uri
}

resource "google_cloudbuild_trigger" "configuration" {
  for_each        = var.enable_ci_cd && var.github_connection_name != "" ? var.ci_cd_services : toset([])
  name            = "${each.key}-main"
  location        = var.region
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild.yaml"
  included_files  = ["${each.key}/**", "infrastructure/cloudbuild.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _REGION     = var.region
    _PROJECT_ID = var.project_id
    _REPOSITORY = google_artifact_registry_repository.apps.repository_id
    _SERVICE    = each.key
  }

  depends_on = [google_project_service.api, google_artifact_registry_repository_iam_member.builder_writer, google_project_iam_member.builder_run_admin, google_project_iam_member.builder_log_writer, google_service_account_iam_member.builder_act_as]
}

resource "google_cloudbuild_trigger" "notification_job" {
  count           = var.enable_ci_cd && var.enable_cloud_sql && var.github_connection_name != "" ? 1 : 0
  name            = "notification-job-main"
  location        = var.region
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild-job.yaml"
  included_files  = ["notification-job/**", "infrastructure/cloudbuild-job.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _REGION     = var.region
    _PROJECT_ID = var.project_id
    _REPOSITORY = google_artifact_registry_repository.apps.repository_id
  }

  depends_on = [
    google_project_service.api,
    google_artifact_registry_repository_iam_member.builder_writer,
    google_project_iam_member.builder_run_admin,
    google_project_iam_member.builder_log_writer,
    google_service_account_iam_member.builder_notification_act_as,
  ]
}

resource "google_cloudbuild_trigger" "vertex_ai_demo" {
  count           = var.enable_ci_cd && var.enable_vertex_ai_demo && var.github_connection_name != "" ? 1 : 0
  name            = "vertex-ai-demo-main"
  location        = var.region
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild-vertex-ai-demo.yaml"
  included_files  = ["vertex-ai-demo/**", "infrastructure/cloudbuild-vertex-ai-demo.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _REGION                  = var.region
    _PROJECT_ID              = var.project_id
    _REPOSITORY              = google_artifact_registry_repository.apps.repository_id
    _RUNTIME_SERVICE_ACCOUNT = google_service_account.vertex_ai_demo[0].email
  }

  depends_on = [
    google_project_service.api,
    google_artifact_registry_repository_iam_member.builder_writer,
    google_project_iam_member.builder_run_admin,
    google_project_iam_member.builder_log_writer,
    google_service_account_iam_member.builder_vertex_ai_demo_act_as,
  ]
}

resource "google_cloudbuild_trigger" "frontend_hosting" {
  count           = var.enable_ci_cd && var.enable_firebase && var.github_connection_name != "" ? 1 : 0
  name            = "frontend-hosting-main"
  location        = var.region
  service_account = google_service_account.builder.id
  filename        = "infrastructure/cloudbuild-frontend.yaml"
  included_files  = ["frontend-app/**", "infrastructure/firebase.json", "infrastructure/cloudbuild-frontend.yaml"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.github[0].id
    push { branch = var.github_branch_regex }
  }

  substitutions = {
    _PROJECT_ID = var.project_id
    # WhatsApp Embedded Signup ("Connect with Facebook"); no configuration ID: the button does nothing.
    _META_APP_ID    = var.meta_app_id
    _META_CONFIG_ID = var.meta_embedded_signup_config_id
  }

  depends_on = [google_project_service.api, google_project_iam_member.builder_log_writer, google_project_iam_member.builder_firebase_hosting_admin, google_project_iam_member.builder_service_usage_consumer]
}
