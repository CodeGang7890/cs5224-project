# Reconciled from cs5224-ansera on 2026-11-09. Import blocks adopt the live
# resources, preserving their names, public IP, certificates and WAF preview.
locals {
  singapore_lb_services = var.enable_singapore_staging && var.manage_singapore_load_balancer ? toset([
    "configuration-service", "messaging-ingester", "payment-ingester", "mock-whatsapp"
  ]) : toset([])
  singapore_lb_enabled = var.enable_singapore_staging && var.manage_singapore_load_balancer
  singapore_lb_certificates = local.singapore_lb_enabled ? {
    ansera-managed-cert     = "ansera.hopto.org"
    ansera-sg-lb-sslip-cert = "34-149-82-198.sslip.io"
  } : {}
  # Preserve the live list order to avoid a routing-only diff during adoption.
  singapore_lb_paths = [
    { path = "payment", service = "payment-ingester" },
    { path = "messaging", service = "messaging-ingester" },
    { path = "whatsapp", service = "mock-whatsapp" },
    { path = "config", service = "configuration-service" },
  ]
}

resource "google_compute_security_policy" "singapore" {
  count       = local.singapore_lb_enabled ? 1 : 0
  name        = "armor-policy"
  description = "Permissive Cloud Armor policy for Cloud Run services"
  type        = "CLOUD_ARMOR"
  advanced_options_config { json_parsing = "STANDARD" }
  dynamic "rule" {
    for_each = { "1000" = "sqli", "1100" = "xss", "1200" = "lfi", "1300" = "rce" }
    content {
      priority    = tonumber(rule.key)
      action      = "deny(403)"
      preview     = true
      description = "WAF ${rule.value}-v422-stable, sensitivity 1"
      match {
        expr {
          expression = "evaluatePreconfiguredWaf('${rule.value}-v422-stable', {'sensitivity': 1})"
        }
      }
    }
  }
  rule {
    priority    = 2147483647
    action      = "allow"
    preview     = false
    description = "default rule"
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
  }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.api]
}

resource "google_compute_region_network_endpoint_group" "singapore" {
  for_each              = local.singapore_lb_services
  name                  = "neg-${each.key}"
  region                = var.singapore_region
  network_endpoint_type = "SERVERLESS"
  cloud_run { service = each.key }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.api]
}

resource "google_compute_backend_service" "singapore" {
  for_each                        = local.singapore_lb_services
  name                            = "backend-${each.key}"
  protocol                        = "HTTP"
  port_name                       = "http"
  timeout_sec                     = 30
  load_balancing_scheme           = "EXTERNAL_MANAGED"
  enable_cdn                      = false
  connection_draining_timeout_sec = 0
  security_policy                 = google_compute_security_policy.singapore[0].self_link
  backend {
    group = google_compute_region_network_endpoint_group.singapore[each.key].id
  }
  log_config {
    enable        = true
    sample_rate   = 1
    optional_mode = "EXCLUDE_ALL_OPTIONAL"
  }
  lifecycle { prevent_destroy = true }
}

resource "google_compute_url_map" "singapore" {
  count           = local.singapore_lb_enabled ? 1 : 0
  name            = "serverless-url-map"
  default_service = google_compute_backend_service.singapore["configuration-service"].self_link
  host_rule {
    hosts        = ["*"]
    path_matcher = "main-paths"
  }
  path_matcher {
    name            = "main-paths"
    default_service = google_compute_backend_service.singapore["configuration-service"].self_link
    dynamic "path_rule" {
      for_each = local.singapore_lb_paths
      content {
        paths   = ["/${path_rule.value.path}/*"]
        service = google_compute_backend_service.singapore[path_rule.value.service].self_link
        route_action {
          url_rewrite { path_prefix_rewrite = "/" }
        }
      }
    }
  }
  lifecycle { prevent_destroy = true }
}

resource "google_compute_global_address" "singapore_lb" {
  count        = local.singapore_lb_enabled ? 1 : 0
  name         = "my-loadbalancer-ip"
  address      = "34.149.82.198"
  address_type = "EXTERNAL"
  ip_version   = "IPV4"
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.api]
}

resource "google_compute_managed_ssl_certificate" "singapore" {
  for_each = local.singapore_lb_certificates
  name     = each.key
  managed { domains = [each.value] }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.api]
}

resource "google_compute_target_https_proxy" "singapore" {
  count            = local.singapore_lb_enabled ? 1 : 0
  name             = "serverless-https-proxy"
  url_map          = google_compute_url_map.singapore[0].self_link
  quic_override    = "NONE"
  ssl_certificates = [for name in ["ansera-managed-cert", "ansera-sg-lb-sslip-cert"] : google_compute_managed_ssl_certificate.singapore[name].self_link]
  lifecycle { prevent_destroy = true }
}

resource "google_compute_global_forwarding_rule" "singapore_https" {
  count                 = local.singapore_lb_enabled ? 1 : 0
  name                  = "serverless-https-forwarding-rule"
  target                = google_compute_target_https_proxy.singapore[0].self_link
  ip_address            = google_compute_global_address.singapore_lb[0].address
  ip_protocol           = "TCP"
  port_range            = "443"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  lifecycle { prevent_destroy = true }
}

import {
  for_each = local.singapore_lb_services
  to       = google_compute_region_network_endpoint_group.singapore[each.key]
  id       = "projects/${var.project_id}/regions/${var.singapore_region}/networkEndpointGroups/neg-${each.key}"
}
import {
  for_each = local.singapore_lb_services
  to       = google_compute_backend_service.singapore[each.key]
  id       = "projects/${var.project_id}/global/backendServices/backend-${each.key}"
}
import {
  for_each = local.singapore_lb_certificates
  to       = google_compute_managed_ssl_certificate.singapore[each.key]
  id       = "projects/${var.project_id}/global/sslCertificates/${each.key}"
}
import {
  for_each = local.singapore_lb_enabled ? toset(["existing"]) : toset([])
  to       = google_compute_security_policy.singapore[0]
  id       = "projects/${var.project_id}/global/securityPolicies/armor-policy"
}
import {
  for_each = local.singapore_lb_enabled ? toset(["existing"]) : toset([])
  to       = google_compute_url_map.singapore[0]
  id       = "projects/${var.project_id}/global/urlMaps/serverless-url-map"
}
import {
  for_each = local.singapore_lb_enabled ? toset(["existing"]) : toset([])
  to       = google_compute_global_address.singapore_lb[0]
  id       = "projects/${var.project_id}/global/addresses/my-loadbalancer-ip"
}
import {
  for_each = local.singapore_lb_enabled ? toset(["existing"]) : toset([])
  to       = google_compute_target_https_proxy.singapore[0]
  id       = "projects/${var.project_id}/global/targetHttpsProxies/serverless-https-proxy"
}
import {
  for_each = local.singapore_lb_enabled ? toset(["existing"]) : toset([])
  to       = google_compute_global_forwarding_rule.singapore_https[0]
  id       = "projects/${var.project_id}/global/forwardingRules/serverless-https-forwarding-rule"
}
