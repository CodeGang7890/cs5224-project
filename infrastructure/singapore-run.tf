# Parallel Cloud Run services for a controlled regional migration.
# They initially use the US database and service URLs; pull consumers are off
# and min instances are zero so staging cannot steal queue messages.
locals {
  singapore_sql_connection_name           = var.singapore_sql_promoted ? google_sql_database_instance.singapore_replica[0].connection_name : google_sql_database_instance.main[0].connection_name
  singapore_configuration_api_url         = "${trimsuffix(lookup(var.singapore_service_urls, "configuration-service", "https://configuration-service-gq6jjn4afq-uc.a.run.app"), "/")}/api"
  singapore_messaging_service_url         = lookup(var.singapore_service_urls, "messaging-service", var.messaging_service_url)
  singapore_payment_ingester_url          = lookup(var.singapore_service_urls, "payment-ingester", var.payment_ingester_url)
  singapore_messaging_ingester_public_url = lookup(var.singapore_service_urls, "messaging-ingester", local.messaging_ingester_public_url)
  singapore_staging_images = {
    "configuration-service" = "asia-southeast1-docker.pkg.dev/${var.project_id}/apps/configuration-service:a144dfc"
    "messaging-ingester"    = "asia-southeast1-docker.pkg.dev/${var.project_id}/apps/messaging-ingester:f40f292"
    "messaging-service"     = "asia-southeast1-docker.pkg.dev/${var.project_id}/apps/messaging-service:f40f292"
    "payment-ingester"      = "asia-southeast1-docker.pkg.dev/${var.project_id}/apps/payment-ingester:ca9b92d"
    "processing-service"    = "asia-southeast1-docker.pkg.dev/${var.project_id}/apps/processing-service:945aa84"
  }
}
resource "google_cloud_run_v2_service" "singapore_backend" {
  for_each            = var.enable_singapore_staging ? setintersection(local.service_names, var.singapore_stage_backend_services) : toset([])
  name                = each.key
  location            = var.singapore_region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  scaling {
    min_instance_count = var.singapore_min_instances
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
          instances = [local.singapore_sql_connection_name]
        }
      }
    }

    containers {
      image = local.singapore_staging_images[each.key]
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
          GCP_PROJECT_ID            = var.project_id
          PUBSUB_TOPIC              = google_pubsub_topic.queue["payment-queue"].name
          PUBSUB_SUBSCRIPTION       = google_pubsub_subscription.queue["payment-queue"].name
          CONFIGURATION_SERVICE_URL = local.singapore_configuration_api_url
          SCHEDULE_TIME_ZONE        = "Asia/Singapore"
          PUBSUB_CONSUMER_ENABLED   = tostring(var.singapore_queue_consumers_enabled)
          PUBSUB_MAX_MESSAGES       = "5"
          WEB_CONCURRENCY           = "2"
          GCS_BUCKET                = google_storage_bucket.singapore_objects[0].name
          INVOICE_CURRENCY          = "SGD"
          EMAIL_ENABLED             = "true"
          EMAIL_FROM                = "ansera.admin@gmail.com"
          EMAIL_FROM_NAME           = "Ansera"
          SMTP_HOST                 = "smtp-relay.brevo.com"
          SMTP_PORT                 = "587"
          SMTP_USERNAME             = "bec985001@smtp-brevo.com"
          } : each.key == "messaging-ingester" ? {
          CONFIGURATION_SERVICE_URL = local.singapore_configuration_api_url
          GCP_PROJECT_ID            = var.project_id
          PUBSUB_TOPIC              = google_pubsub_topic.queue["messaging-queue"].name
          } : each.key == "messaging-service" ? {
          PAYMENT_INGESTER_URL      = local.singapore_payment_ingester_url
          CONFIGURATION_SERVICE_URL = local.singapore_configuration_api_url
          CORS_ALLOWED_ORIGINS      = "https://${var.firebase_hosting_site_id}.web.app,https://${var.firebase_hosting_site_id}.firebaseapp.com"
          PUBSUB_CONSUMER_ENABLED   = tostring(var.singapore_queue_consumers_enabled)
          GCP_PROJECT_ID            = var.project_id
          PUBSUB_TOPIC              = google_pubsub_topic.queue["messaging-queue"].name
          PUBSUB_SUBSCRIPTION       = google_pubsub_subscription.queue["messaging-queue"].name
          PUBSUB_MAX_MESSAGES       = "5"
          WEB_CONCURRENCY           = "2"
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
          MESSAGING_INGESTER_PUBLIC_URL = local.singapore_messaging_ingester_public_url
          META_GRAPH_API_URL            = "https://graph.facebook.com/v25.0"
          META_APP_ID                   = var.meta_app_id
          FIREBASE_PROJECT_ID           = var.enable_firebase ? var.project_id : ""
          DJANGO_NUM_PROXIES            = "1"
          # WhatsApp replies: to mock-whatsapp's fake Graph API or to Meta (mock-whatsapp.tf).
          WHATSAPP_REPLIES_TO         = local.replies_to_mock_whatsapp ? "mock" : "meta"
          MOCK_WHATSAPP_GRAPH_API_URL = local.mock_whatsapp_graph_api_url
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
          MESSAGING_SERVICE_URL              = local.singapore_messaging_service_url
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
          POSTGRES_HOST = "/cloudsql/${local.singapore_sql_connection_name}"
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

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_project_service.api, google_secret_manager_secret_iam_member.configuration_secret, google_secret_manager_secret_iam_member.configuration_encryption, google_secret_manager_secret_iam_member.configuration_sql_password, google_secret_manager_secret_iam_member.messaging_sql_password, google_secret_manager_secret_iam_member.processing_sql_password, google_secret_manager_secret_iam_member.processing_smtp_password, google_secret_manager_secret_iam_member.jwt, google_secret_manager_secret_version.django, google_secret_manager_secret_version.jwt, google_secret_manager_secret_version.internal_api, google_secret_manager_secret_iam_member.internal_api, google_secret_manager_secret_iam_member.configuration_meta, google_secret_manager_secret_version.meta_webhook_verify_token, google_secret_manager_secret_iam_member.payment_xendit_api, google_secret_manager_secret_iam_member.payment_xendit_webhook, google_storage_bucket_iam_member.singapore_processing_object_user, google_storage_bucket_iam_member.singapore_messaging_object_user, google_service_account_iam_member.processing_invoice_signer]
}

resource "google_cloud_run_v2_service" "singapore_vertex_ai_demo" {
  count               = var.enable_singapore_staging && var.enable_vertex_ai_demo ? 1 : 0
  name                = "vertex-ai-demo"
  location            = var.singapore_region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  scaling {
    min_instance_count = var.singapore_min_instances
    max_instance_count = 3
  }

  template {
    service_account                  = google_service_account.vertex_ai_demo[0].email
    max_instance_request_concurrency = 10
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = "asia-southeast1-docker.pkg.dev/${var.project_id}/apps/vertex-ai-demo:0e37b60"
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.vertex_ai_location
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "True"
      }
      env {
        name  = "LLM_MODEL"
        value = var.vertex_ai_model
      }
    }
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [template[0].containers[0].image]
  }
  depends_on = [google_project_iam_member.vertex_ai_demo_user]
}

resource "google_cloud_run_v2_service_iam_member" "singapore_configuration_calls_messaging" {
  count    = var.enable_singapore_staging && contains(var.singapore_stage_backend_services, "messaging-service") ? 1 : 0
  project  = var.project_id
  location = var.singapore_region
  name     = google_cloud_run_v2_service.singapore_backend["messaging-service"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["configuration-service"].email}"
}

resource "google_cloud_run_v2_service_iam_member" "singapore_vertex_ai_demo_public" {
  count    = var.enable_singapore_staging && var.enable_vertex_ai_demo && var.vertex_ai_demo_allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = var.singapore_region
  name     = google_cloud_run_v2_service.singapore_vertex_ai_demo[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "singapore_public" {
  for_each = var.enable_singapore_staging && var.singapore_public_endpoints_enabled ? {
    for k, v in google_cloud_run_v2_service.singapore_backend : k => v
    if contains(["configuration-service", "payment-ingester", "messaging-ingester"], k)
  } : {}
  project  = var.project_id
  location = var.singapore_region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

