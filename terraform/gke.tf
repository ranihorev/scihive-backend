variable "gke_username" {
  default     = ""
  description = "gke username"
}

variable "gke_password" {
  default     = ""
  description = "gke password"
}

variable "gke_num_nodes" {
  default     = 2
  description = "number of gke nodes"
}

variable "node_locations" {
  description = "node zones"
}

variable "cluster_location" {
  description = "Location of the cluster"
}

# GKE cluster
resource "google_container_cluster" "primary" {
  name     = "${var.project_id}-gke"
  location = var.cluster_location

  remove_default_node_pool = true
  initial_node_count       = 1
  node_locations           = var.node_locations

  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.subnet.name

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  master_auth {
    username = var.gke_username
    password = var.gke_password

    client_certificate_config {
      issue_client_certificate = false
    }
  }
}

# Separately Managed Node Pool
resource "google_container_node_pool" "primary_nodes" {
  name       = "${google_container_cluster.primary.name}-node-pool"
  location   = var.cluster_location
  cluster    = google_container_cluster.primary.name
  node_count = var.gke_num_nodes

  node_locations = var.node_locations

  node_config {
    preemptible = true
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      env = var.project_id
    }

    machine_type = "custom-2-2048"
    tags         = ["gke-node", "${var.project_id}-gke"]
    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

output "kubernetes_cluster_name" {
  value       = google_container_cluster.primary.name
  description = "GKE Cluster Name"
}

output "cluster_location" {
  value       = var.cluster_location
  description = "Location of the cluster (region or zone)"
}

resource "google_compute_global_address" "ingress_address" {
  name = "main-ingress-ip"
}
