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

  lifecycle {
    prevent_destroy = true
  }
}

# The queues and their worker subscriptions (docker-compose's pubsub-init sets up the same locally).
# A message nacked or not acked within the ack deadline is redelivered after a backoff of 30s growing
# to 600s; after 5 delivery attempts Pub/Sub moves it to the queue's dead-letter topic (<queue>-dlq).
# The consumers' leases match the ack deadlines (PUBSUB_ACK_DEADLINE_SECONDS in run.tf).
locals {
  pubsub_queues = {
    # WhatsApp messages → messaging-service: a chat turn can take a while. Not ordered: a customer's
    # messages sent close together are handled at once and get one reply (messaging-service/app/inbound.py).
    "messaging-queue" = { ack_deadline_seconds = 120, ordered = false, dead_letter = true }
    # Xendit payment events → processing-service.
    "payment-queue" = { ack_deadline_seconds = 60, ordered = false, dead_letter = true }
    # Unused by the notification job (Cloud Scheduler runs it directly): unchanged.
    "notification-tick" = { ack_deadline_seconds = 30, ordered = false, dead_letter = false }
  }
  pubsub_dead_letter_queues    = toset([for name, queue in local.pubsub_queues : name if queue.dead_letter])
  pubsub_min_backoff           = "30s"
  pubsub_max_backoff           = "600s"
  pubsub_max_delivery_attempts = 5
  # Pub/Sub's service agent forwards dead letters: it publishes to the dead-letter topic and acks the
  # message on the original subscription.
  pubsub_service_agent = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic" "queue" {
  for_each   = local.pubsub_queues
  name       = each.key
  depends_on = [google_project_service.api]

  dynamic "message_storage_policy" {
    for_each = length(var.pubsub_allowed_persistence_regions) > 0 ? [1] : []
    content {
      allowed_persistence_regions = var.pubsub_allowed_persistence_regions
    }
  }
}

resource "google_pubsub_topic" "dead_letter" {
  for_each   = local.pubsub_dead_letter_queues
  name       = "${each.key}-dlq"
  depends_on = [google_project_service.api]
}

resource "google_pubsub_subscription" "queue" {
  for_each                   = local.pubsub_queues
  name                       = "${each.key}-worker"
  topic                      = google_pubsub_topic.queue[each.key].id
  ack_deadline_seconds       = each.value.ack_deadline_seconds
  enable_message_ordering    = each.value.ordered
  message_retention_duration = "86400s"

  dynamic "retry_policy" {
    for_each = each.value.dead_letter ? [1] : []
    content {
      minimum_backoff = local.pubsub_min_backoff
      maximum_backoff = local.pubsub_max_backoff
    }
  }

  dynamic "dead_letter_policy" {
    for_each = each.value.dead_letter ? [1] : []
    content {
      dead_letter_topic     = google_pubsub_topic.dead_letter[each.key].id
      max_delivery_attempts = local.pubsub_max_delivery_attempts
    }
  }
}

# Keeps what lands in each dead-letter topic (Pub/Sub drops messages a topic has no subscription for),
# to look at or replay: gcloud pubsub subscriptions pull <queue>-dlq-sub --limit=10
resource "google_pubsub_subscription" "dead_letter" {
  for_each                   = local.pubsub_dead_letter_queues
  name                       = "${each.key}-dlq-sub"
  topic                      = google_pubsub_topic.dead_letter[each.key].id
  ack_deadline_seconds       = 60
  message_retention_duration = "604800s" # 7 days, the most a subscription keeps
  expiration_policy {
    ttl = "" # never expires, even unused
  }
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  for_each = local.pubsub_dead_letter_queues
  topic    = google_pubsub_topic.dead_letter[each.key].name
  role     = "roles/pubsub.publisher"
  member   = local.pubsub_service_agent
}

resource "google_pubsub_subscription_iam_member" "dead_letter_subscriber" {
  for_each     = local.pubsub_dead_letter_queues
  subscription = google_pubsub_subscription.queue[each.key].name
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_service_agent
}

resource "google_secret_manager_secret" "app" {
  for_each  = toset(["django-secret-key", "internal-api-key", "jwt-signing-key", "llm-api-key", "whatsapp-token", "xendit-api-key", "meta-webhook-verify-token"])
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
