# Existing default VPC: adopt only the Singapore subnet and application NAT.
# Other default subnets and firewall rules remain outside this configuration.
data "google_compute_network" "singapore_egress" {
  count = var.enable_singapore_staging ? 1 : 0
  name  = var.singapore_vpc_network
}

resource "google_compute_subnetwork" "singapore_egress" {
  count                    = var.enable_singapore_staging ? 1 : 0
  name                     = var.singapore_vpc_subnetwork
  region                   = var.singapore_region
  network                  = data.google_compute_network.singapore_egress[0].self_link
  ip_cidr_range            = var.singapore_vpc_subnet_cidr
  private_ip_google_access = true
  stack_type               = "IPV4_ONLY"
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.api]
}

resource "google_compute_router" "singapore_egress" {
  count   = var.enable_singapore_staging ? 1 : 0
  name    = "messaging-nat-router"
  region  = var.singapore_region
  network = data.google_compute_network.singapore_egress[0].self_link
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.api]
}

resource "google_compute_router_nat" "singapore_egress" {
  count                               = var.enable_singapore_staging ? 1 : 0
  name                                = "messaging-nat-gateway"
  router                              = google_compute_router.singapore_egress[0].name
  region                              = var.singapore_region
  nat_ip_allocate_option              = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat  = "LIST_OF_SUBNETWORKS"
  enable_endpoint_independent_mapping = false
  type                                = "PUBLIC"
  endpoint_types                      = ["ENDPOINT_TYPE_VM"]
  subnetwork {
    name                    = google_compute_subnetwork.singapore_egress[0].self_link
    source_ip_ranges_to_nat = ["PRIMARY_IP_RANGE"]
  }
  lifecycle { prevent_destroy = true }
}

import {
  for_each = var.enable_singapore_staging ? toset(["existing"]) : toset([])
  to       = google_compute_subnetwork.singapore_egress[0]
  id       = "projects/${var.project_id}/regions/${var.singapore_region}/subnetworks/${var.singapore_vpc_subnetwork}"
}
import {
  for_each = var.enable_singapore_staging ? toset(["existing"]) : toset([])
  to       = google_compute_router.singapore_egress[0]
  id       = "projects/${var.project_id}/regions/${var.singapore_region}/routers/messaging-nat-router"
}
import {
  for_each = var.enable_singapore_staging ? toset(["existing"]) : toset([])
  to       = google_compute_router_nat.singapore_egress[0]
  id       = "projects/${var.project_id}/regions/${var.singapore_region}/routers/messaging-nat-router/messaging-nat-gateway"
}
