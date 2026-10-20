# Global external Application Load Balancer in front of the Cloud Run services, plus Cloud Armor.
#
# Off by default (var.enable_load_balancer): create it for a demo, then switch it off again. The static IP is
# always reserved, so the webhook URLs registered with Meta and Xendit survive a destroy / re-create.
#
#   Browser / Meta / Xendit -> static IP :443 -> URL map -> backend service (+ Cloud Armor) -> serverless NEG -> Cloud Run
#
# The frontend is not behind it (Firebase Hosting). Only the backend entry points are.

locals {
  lb_only_services = ["messaging-service", "messaging-ingester", "payment-ingester"]

  # Backend key => Cloud Run service. Only the services that receive traffic from outside Google Cloud.
  lb_backends = var.enable_load_balancer ? {
    "configuration-service" = "configuration-service"
    "messaging-service"     = "messaging-service"
    "messaging-ingester"    = "messaging-ingester"
    "payment-ingester"      = "payment-ingester"
  } : {}

  # Nobody can use sslip.io's wildcard DNS on its own, so without a domain the hostname is <ip-with-dashes>.sslip.io,
  # which resolves to the IP and lets Google issue a managed certificate for it.
  lb_hostname = var.dns_domain != "" ? trimsuffix(var.dns_domain, ".") : "${replace(google_compute_global_address.lb.address, ".", "-")}.sslip.io"

  # Longer than the default for the chat endpoint: the LLM reply is produced inside the request.
  lb_backend_timeout = {
    "messaging-service" = 120
  }
}

# --- Entry point ----------------------------------------------------------------------------------------------

resource "google_compute_global_address" "lb" {
  name = "lb-ip"

  depends_on = [google_project_service.api]
}

resource "google_compute_region_network_endpoint_group" "services" {
  for_each = local.lb_backends

  name                  = "${each.key}-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.backend[each.value].name
  }
}

resource "google_compute_backend_service" "services" {
  for_each = local.lb_backends

  name                  = "${each.key}-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = lookup(local.lb_backend_timeout, each.key, 30)

  backend {
    group = google_compute_region_network_endpoint_group.services[each.key].id
  }

  security_policy = (
    !var.enable_cloud_armor ? null
    : each.key == "payment-ingester" ? google_compute_security_policy.xendit[0].id
    : google_compute_security_policy.general[0].id
  )

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# --- Routing --------------------------------------------------------------------------------------------------

resource "google_compute_url_map" "https" {
  count = var.enable_load_balancer ? 1 : 0

  name = "backend-url-map"

  # Anything not matched below is configuration-service's (/api/...).
  default_service = google_compute_backend_service.services["configuration-service"].id

  host_rule {
    hosts        = ["*"]
    path_matcher = "backend"
  }

  path_matcher {
    name            = "backend"
    default_service = google_compute_backend_service.services["configuration-service"].id

    # The service-to-service API and Django admin are never reachable through the load balancer.
    route_rules {
      priority = 1
      match_rules {
        prefix_match = "/api/internal/"
      }
      route_action {
        weighted_backend_services {
          backend_service = google_compute_backend_service.services["configuration-service"].id
          weight          = 100
        }
        fault_injection_policy {
          abort {
            http_status = 404
            percentage  = 100
          }
        }
      }
    }

    route_rules {
      priority = 2
      match_rules {
        prefix_match = "/admin/"
      }
      route_action {
        weighted_backend_services {
          backend_service = google_compute_backend_service.services["configuration-service"].id
          weight          = 100
        }
        fault_injection_policy {
          abort {
            http_status = 404
            percentage  = 100
          }
        }
      }
    }

    # The chat flow's two endpoints live in messaging-service, under the same /api/chat/ prefix configuration-service
    # uses for the rest of the chat API.
    route_rules {
      priority = 10
      match_rules {
        regex_match = "^/api/chat/(sandbox-sessions/[0-9]+|sessions)/messages/?$"
      }
      service = google_compute_backend_service.services["messaging-service"].id
    }

    # WhatsApp webhooks: /webhook/{business_id}
    route_rules {
      priority = 20
      match_rules {
        prefix_match = "/webhook/"
      }
      service = google_compute_backend_service.services["messaging-ingester"].id
    }

    # Xendit callbacks. payment-ingester isn't built yet, so this path is a placeholder.
    route_rules {
      priority = 30
      match_rules {
        prefix_match = "/xendit/"
      }
      service = google_compute_backend_service.services["payment-ingester"].id
    }
  }
}

# --- HTTPS ----------------------------------------------------------------------------------------------------

resource "google_compute_managed_ssl_certificate" "lb" {
  count = var.enable_load_balancer ? 1 : 0

  name_prefix = "lb-cert-"

  managed {
    domains = [local.lb_hostname]
  }

  # A certificate in use can't be replaced in place: make the new one first.
  lifecycle {
    create_before_destroy = true
  }
}

resource "google_compute_target_https_proxy" "lb" {
  count = var.enable_load_balancer ? 1 : 0

  name             = "lb-https-proxy"
  url_map          = google_compute_url_map.https[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb[0].id]
}

resource "google_compute_global_forwarding_rule" "https" {
  count = var.enable_load_balancer ? 1 : 0

  name                  = "lb-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb.address
  port_range            = "443"
  target                = google_compute_target_https_proxy.lb[0].id
}

# Port 80 only redirects to HTTPS.
resource "google_compute_url_map" "http_redirect" {
  count = var.enable_load_balancer ? 1 : 0

  name = "http-redirect-url-map"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  count = var.enable_load_balancer ? 1 : 0

  name    = "lb-http-proxy"
  url_map = google_compute_url_map.http_redirect[0].id
}

resource "google_compute_global_forwarding_rule" "http" {
  count = var.enable_load_balancer ? 1 : 0

  name                  = "lb-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect[0].id
}

# --- Cloud Armor ----------------------------------------------------------------------------------------------

locals {
  armor_enabled = var.enable_load_balancer && var.enable_cloud_armor
}

# Everything except the payment webhook.
resource "google_compute_security_policy" "general" {
  count = local.armor_enabled ? 1 : 0

  name        = "general-policy"
  description = "Rate limit per client IP, and OWASP rules (preview only: logged, not blocked)."

  rule {
    priority    = 800
    action      = "throttle"
    description = "Rate limit per client IP"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.rate_limit_per_minute
        interval_sec = 60
      }
    }
  }

  # Preview: matches show up in the logs, nothing is blocked. Check them after a demo run, then set preview = false.
  rule {
    priority    = 900
    action      = "deny(403)"
    description = "OWASP: SQL injection"
    preview     = true
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    priority    = 910
    action      = "deny(403)"
    description = "OWASP: cross-site scripting"
    preview     = true
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
      }
    }
  }

  rule {
    priority    = 2147483647
    action      = "allow"
    description = "Default: allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

# The payment webhook: rate limited, and (once var.xendit_ip_ranges is filled in) only Xendit may call it.
resource "google_compute_security_policy" "xendit" {
  count = local.armor_enabled ? 1 : 0

  name        = "xendit-policy"
  description = "Rate limit, and only Xendit's IP addresses when they are configured."

  rule {
    priority    = 800
    action      = "throttle"
    description = "Rate limit per client IP"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.rate_limit_per_minute
        interval_sec = 60
      }
    }
  }

  dynamic "rule" {
    for_each = length(var.xendit_ip_ranges) > 0 ? [1] : []
    content {
      priority    = 900
      action      = "allow"
      description = "Xendit's IP addresses"
      match {
        versioned_expr = "SRC_IPS_V1"
        config {
          src_ip_ranges = var.xendit_ip_ranges
        }
      }
    }
  }

  rule {
    priority    = 2147483647
    action      = length(var.xendit_ip_ranges) > 0 ? "deny(403)" : "allow"
    description = "Default: deny when Xendit's IPs are configured, allow otherwise"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}
