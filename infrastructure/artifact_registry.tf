# One Docker repo holding an image per service:
#   asia-southeast1-docker.pkg.dev/<project>/apps/<service>:<tag>
resource "google_artifact_registry_repository" "apps" {
  repository_id = "apps"
  location      = var.region
  format        = "DOCKER"
  description   = "Container images for all services."

  cleanup_policy_dry_run = false

  # KEEP wins over DELETE: the 3 newest versions of each image are always kept,
  # anything else is deleted once it is older than 7 days.
  cleanup_policies {
    id     = "keep-3-most-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }

  cleanup_policies {
    id     = "delete-older-than-7-days"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "604800s" # 7 days
    }
  }

  depends_on = [google_project_service.apis]
}
