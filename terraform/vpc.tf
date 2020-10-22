variable "project_id" {
  description = "project id"
}

variable "region" {
  description = "region"
}

variable "home_ip" {
  description = "Your home ip address for external access"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# VPC
resource "google_compute_network" "vpc" {
  name                    = "${var.project_id}-vpc"
  auto_create_subnetworks = "false"
}

# Private IP range
resource "google_compute_global_address" "private_ip_block" {
  name         = "private-ip-block"
  purpose      = "VPC_PEERING"
  address_type = "INTERNAL"
  ip_version   = "IPV4"
  prefix_length = 20
  network       = google_compute_network.vpc.self_link
}

# Private access
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.self_link
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_block.name]
}

# Allow shh access for Cloud Proxy (not implemented)
resource "google_compute_firewall" "allow_ssh" {
  name        = "allow-ssh"
  network     = google_compute_network.vpc.name
  direction   = "INGRESS"
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  target_tags = ["ssh-enabled"]
}

# Allow shh access for Cloud Proxy (not implemented)
resource "google_compute_firewall" "home_dev" {
  name        = "home-dev"
  network     = google_compute_network.vpc.name
  direction   = "INGRESS"
  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }
  source_ranges = [var.home_ip]
}


# Subnet
resource "google_compute_subnetwork" "subnet" {
  name          = "${var.project_id}-subnet"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.0.0.0/16"

  secondary_ip_range {
    ip_cidr_range = "10.1.0.0/16"
    range_name    = "pods"
  }

  secondary_ip_range {
    ip_cidr_range = "10.2.0.0/16"
    range_name    = "services"
  }
}

output "region" {
  value       = var.region
  description = "region"
}
