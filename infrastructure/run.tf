locals {
  browser_cors_allowed_origins = join(",", distinct(concat(
    ["http://localhost:5173", "http://127.0.0.1:5173"],
    var.enable_firebase ? [
      "https://${var.firebase_hosting_site_id}.web.app",
      "https://${var.firebase_hosting_site_id}.firebaseapp.com",
    ] : [],
    var.additional_browser_origins,
  )))
}

resource "google_service_account" "runtime" {
  for_each     = local.runtime_identities
  account_id   = substr(replace(each.key, "-service", "-svc"), 0, 30)
  display_name = "${each.key} runtime"
  depends_on   = [google_project_service.api]
}

resource "google_project_iam_member" "sql_client" {
  for_each = var.enable_cloud_sql ? toset(["configuration-service", "messaging-service", "processing-service", "notification-job"]) : toset([])
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}

resource "google_project_iam_member" "vertex_ai_user" {
  for_each   = var.enable_vertex_ai ? var.vertex_ai_services : toset([])
  project    = var.project_id
  role       = "roles/aiplatform.user"
  member     = "serviceAccount:${google_service_account.runtime[each.key].email}"
  depends_on = [google_project_service.api]
}

resource "google_secret_manager_secret_iam_member" "configuration_secret" {
  secret_id = google_secret_manager_secret.app["django-secret-key"].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["configuration-service"].email}"
}

resource "google_secret_manager_secret_iam_member" "configuration_encryption" {
  secret_id = "projects/${var.project_id}/secrets/configuration-encryption-key"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["configuration-service"].email}"
}

resource "random_password" "django" {
  length  = 50
  special = false
}

resource "google_secret_manager_secret_version" "django" {
  secret      = google_secret_manager_secret.app["django-secret-key"].id
  secret_data = random_password.django.result
}

resource "random_password" "jwt" {
  length  = 50
  special = false
}

resource "google_secret_manager_secret_version" "jwt" {
  secret      = google_secret_manager_secret.app["jwt-signing-key"].id
  secret_data = random_password.jwt.result
}

resource "google_secret_manager_secret_iam_member" "jwt" {
  for_each  = toset(["configuration-service", "messaging-service"])
  secret_id = google_secret_manager_secret.app["jwt-signing-key"].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime[each.key].email}"
}

resource "random_password" "internal_api" {
  length  = 48
  special = false
}

resource "google_secret_manager_secret_version" "internal_api" {
  secret      = google_secret_manager_secret.app["internal-api-key"].id
  secret_data = random_password.internal_api.result
}

resource "google_secret_manager_secret_iam_member" "internal_api" {
  for_each  = toset(["configuration-service", "messaging-service", "messaging-ingester", "payment-ingester", "processing-service"])
  secret_id = google_secret_manager_secret.app["internal-api-key"].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime[each.key].email}"
}

resource "google_secret_manager_secret_iam_member" "payment_xendit_api" {
  secret_id = google_secret_manager_secret.app["xendit-api-key"].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["payment-ingester"].email}"
}

resource "google_secret_manager_secret_iam_member" "payment_xendit_webhook" {
  secret_id = "projects/${var.project_id}/secrets/xendit-webhook-key"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["payment-ingester"].email}"
}

resource "google_secret_manager_secret_iam_member" "configuration_sql_password" {
  count     = var.enable_cloud_sql ? 1 : 0
  secret_id = google_secret_manager_secret.sql_password[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["configuration-service"].email}"
}

resource "google_secret_manager_secret_iam_member" "messaging_sql_password" {
  count     = var.enable_cloud_sql ? 1 : 0
  secret_id = google_secret_manager_secret.sql_password[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["messaging-service"].email}"
}

resource "google_secret_manager_secret_iam_member" "processing_sql_password" {
  count     = var.enable_cloud_sql ? 1 : 0
  secret_id = google_secret_manager_secret.sql_password[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["processing-service"].email}"
}

resource "google_secret_manager_secret_iam_member" "processing_smtp_password" {
  secret_id = "projects/${var.project_id}/secrets/smtp-password"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["processing-service"].email}"
}

resource "google_storage_bucket_iam_member" "messaging_object_user" {
  count  = var.retire_us_resources ? 0 : 1
  bucket = google_storage_bucket.objects[0].name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime["messaging-service"].email}"
}

resource "google_storage_bucket_iam_member" "processing_object_user" {
  count  = var.retire_us_resources ? 0 : 1
  bucket = google_storage_bucket.objects[0].name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime["processing-service"].email}"
}

resource "google_service_account_iam_member" "processing_invoice_signer" {
  service_account_id = google_service_account.runtime["processing-service"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.runtime["processing-service"].email}"
}

resource "google_pubsub_topic_iam_member" "payment_publisher" {
  topic  = google_pubsub_topic.queue["payment-queue"].name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.runtime["payment-ingester"].email}"
}

resource "google_pubsub_topic_iam_member" "messaging_publisher" {
  topic  = google_pubsub_topic.queue["messaging-queue"].name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.runtime["messaging-ingester"].email}"
}

resource "google_pubsub_subscription_iam_member" "payment_subscriber" {
  subscription = google_pubsub_subscription.queue["payment-queue"].name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.runtime["processing-service"].email}"
}

resource "google_pubsub_subscription_iam_member" "messaging_subscriber" {
  subscription = google_pubsub_subscription.queue["messaging-queue"].name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.runtime["messaging-service"].email}"
}

resource "google_cloud_run_v2_service" "backend" {
  for_each            = var.retire_us_resources ? toset([]) : local.service_names
  name                = each.key
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  scaling {
    min_instance_count = var.us_min_instances
    max_instance_count = 3
  }

  template {
    service_account                  = google_service_account.runtime[each.key].email
    max_instance_request_concurrency = 10
    scaling {
      # Service-level minimum keeps one warm instance without stacking revision minimums.
      min_instance_count = 0
      max_instance_count = 1
    }

    dynamic "volumes" {
      for_each = var.enable_cloud_sql && contains(["configuration-service", "messaging-service", "processing-service"], each.key) ? [1] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main[0].connection_name]
        }
      }
    }

    containers {
      image = lookup(var.service_images, each.key, "us-docker.pkg.dev/cloudrun/container/hello")
      ports { container_port = 8000 }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = !contains(["messaging-service", "processing-service"], each.key)
      }
      dynamic "env" {
        for_each = each.key == "payment-ingester" ? {
          GCP_PROJECT_ID = var.project_id
          PUBSUB_TOPIC   = google_pubsub_topic.queue["payment-queue"].name
          } : each.key == "processing-service" ? {
          GCP_PROJECT_ID              = var.project_id
          PUBSUB_TOPIC                = google_pubsub_topic.queue["payment-queue"].name
          PUBSUB_SUBSCRIPTION         = google_pubsub_subscription.queue["payment-queue"].name
          PUBSUB_ACK_DEADLINE_SECONDS = tostring(google_pubsub_subscription.queue["payment-queue"].ack_deadline_seconds)
          CONFIGURATION_SERVICE_URL   = "https://configuration-service-gq6jjn4afq-uc.a.run.app/api"
          SCHEDULE_TIME_ZONE          = "Asia/Singapore"
          PUBSUB_CONSUMER_ENABLED     = tostring(var.us_queue_consumers_enabled)
          PUBSUB_MAX_MESSAGES         = "5"
          WEB_CONCURRENCY             = "2"
          GCS_BUCKET                  = google_storage_bucket.objects[0].name
          INVOICE_CURRENCY            = "SGD"
          EMAIL_ENABLED               = "true"
          EMAIL_FROM                  = "ansera.admin@gmail.com"
          EMAIL_FROM_NAME             = "Ansera"
          SMTP_HOST                   = "smtp-relay.brevo.com"
          SMTP_PORT                   = "587"
          SMTP_USERNAME               = "bec985001@smtp-brevo.com"
          } : each.key == "messaging-ingester" ? {
          CONFIGURATION_SERVICE_URL = var.us_legacy_messaging_ingester_configuration_service_url
          GCP_PROJECT_ID            = var.project_id
          PUBSUB_TOPIC              = google_pubsub_topic.queue["messaging-queue"].name
          } : each.key == "messaging-service" ? {
          PAYMENT_INGESTER_URL        = var.payment_ingester_url
          CONFIGURATION_SERVICE_URL   = "https://configuration-service-gq6jjn4afq-uc.a.run.app/api"
          CORS_ALLOWED_ORIGINS        = "https://${var.firebase_hosting_site_id}.web.app,https://${var.firebase_hosting_site_id}.firebaseapp.com"
          PUBSUB_CONSUMER_ENABLED     = tostring(var.us_queue_consumers_enabled)
          GCP_PROJECT_ID              = var.project_id
          PUBSUB_TOPIC                = google_pubsub_topic.queue["messaging-queue"].name
          PUBSUB_SUBSCRIPTION         = google_pubsub_subscription.queue["messaging-queue"].name
          PUBSUB_ACK_DEADLINE_SECONDS = tostring(google_pubsub_subscription.queue["messaging-queue"].ack_deadline_seconds)
          PUBSUB_MAX_MESSAGES         = "5"
          WEB_CONCURRENCY             = "2"
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = contains(["configuration-service", "messaging-service", "messaging-ingester", "payment-ingester", "processing-service"], each.key) ? [1] : []
        content {
          name = "INTERNAL_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["internal-api-key"].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = each.key == "processing-service" ? [1] : []
        content {
          name = "SMTP_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = "smtp-password"
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = each.key == "payment-ingester" ? {
          XENDIT_SECRET_KEY     = google_secret_manager_secret.app["xendit-api-key"].secret_id
          XENDIT_WEBHOOK_SECRET = "xendit-webhook-key"
        } : {}
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = each.key == "configuration-service" ? [1] : []
        content {
          name  = "DJANGO_DEBUG"
          value = "False"
        }
      }
      dynamic "env" {
        for_each = each.key == "configuration-service" ? [1] : []
        content {
          name = "CONFIGURATION_ENCRYPTION_KEY"
          value_source {
            secret_key_ref {
              secret  = "configuration-encryption-key"
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = var.enable_vertex_ai && contains(var.vertex_ai_services, each.key) ? {
          LLM_PROVIDER              = "vertex_ai"
          GOOGLE_CLOUD_PROJECT      = var.project_id
          GOOGLE_CLOUD_LOCATION     = var.vertex_ai_location
          GOOGLE_GENAI_USE_VERTEXAI = "True"
          LLM_MODEL                 = var.vertex_ai_model
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        # WhatsApp webhook Callback URLs (set by Embedded Signup), our Meta app, the project whose Identity
        # Platform signs Google / Facebook logins (identity.tf; empty: off), and Cloud Run's front end, which
        # appends the client's IP to X-Forwarded-For (the login / sign-up rate limits count per client).
        for_each = each.key == "configuration-service" ? {
          MESSAGING_INGESTER_PUBLIC_URL = local.messaging_ingester_public_url
          META_GRAPH_API_URL            = "https://graph.facebook.com/v25.0"
          META_APP_ID                   = var.meta_app_id
          FIREBASE_PROJECT_ID           = var.enable_firebase ? var.project_id : ""
          DJANGO_NUM_PROXIES            = "1"
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = each.key == "configuration-service" ? local.meta_secrets : {}
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value == "meta-app-secret" ? env.value : google_secret_manager_secret.app[env.value].secret_id
              version = env.value == "meta-app-secret" ? var.meta_app_secret_version : "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = each.key == "configuration-service" ? [1] : []
        content {
          name  = "DJANGO_ALLOWED_HOSTS"
          value = var.django_allowed_hosts
        }
      }
      dynamic "env" {
        for_each = each.key == "configuration-service" ? {
          MESSAGING_SERVICE_URL              = var.messaging_service_url
          MESSAGING_SERVICE_REQUIRE_ID_TOKEN = "True"
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = contains(["configuration-service", "messaging-service"], each.key) ? [1] : []
        content {
          name = "JWT_SIGNING_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["jwt-signing-key"].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = each.key == "configuration-service" ? [1] : []
        content {
          name  = "DJANGO_CORS_ALLOWED_ORIGINS"
          value = local.browser_cors_allowed_origins
        }
      }
      dynamic "env" {
        for_each = each.key == "configuration-service" ? [1] : []
        content {
          name = "DJANGO_SECRET_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["django-secret-key"].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = var.enable_cloud_sql && contains(["configuration-service", "messaging-service", "processing-service"], each.key) ? merge({
          POSTGRES_DB   = "configuration_service"
          POSTGRES_USER = "app"
          POSTGRES_HOST = "/cloudsql/${google_sql_database_instance.main[0].connection_name}"
          POSTGRES_PORT = "5432"
        }, each.key == "configuration-service" ? { DJANGO_DB_ENGINE = "postgresql" } : {}) : {}
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = contains(["configuration-service", "messaging-service", "processing-service"], each.key) && var.enable_cloud_sql ? [1] : []
        content {
          name = "POSTGRES_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.sql_password[0].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "volume_mounts" {
        for_each = var.enable_cloud_sql && contains(["configuration-service", "messaging-service", "processing-service"], each.key) ? [1] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }

  lifecycle { ignore_changes = [template[0].containers[0].image] }
  depends_on = [google_project_service.api, google_secret_manager_secret_iam_member.configuration_secret, google_secret_manager_secret_iam_member.configuration_encryption, google_secret_manager_secret_iam_member.configuration_sql_password, google_secret_manager_secret_iam_member.messaging_sql_password, google_secret_manager_secret_iam_member.processing_sql_password, google_secret_manager_secret_iam_member.processing_smtp_password, google_secret_manager_secret_iam_member.jwt, google_secret_manager_secret_version.django, google_secret_manager_secret_version.jwt, google_secret_manager_secret_version.internal_api, google_secret_manager_secret_iam_member.internal_api, google_secret_manager_secret_iam_member.configuration_meta, google_secret_manager_secret_version.meta_webhook_verify_token, google_secret_manager_secret_iam_member.payment_xendit_api, google_secret_manager_secret_iam_member.payment_xendit_webhook, google_storage_bucket_iam_member.processing_object_user, google_service_account_iam_member.processing_invoice_signer]
}

resource "google_cloud_run_v2_service_iam_member" "configuration_calls_messaging" {
  count    = var.retire_us_resources ? 0 : 1
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend["messaging-service"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["configuration-service"].email}"
}

# Only the public API endpoints accept unauthenticated webhook/browser calls.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = var.retire_us_resources ? toset([]) : toset([for k in local.service_names : k if(var.us_public_endpoints_enabled && contains(["configuration-service", "payment-ingester", "messaging-ingester"], k)) || (var.us_legacy_messaging_ingester_public && k == "messaging-ingester") || (var.us_legacy_payment_ingester_public && k == "payment-ingester")])
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend[each.key].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
