variable "db_user" {}
variable "db_name" {}
variable "db_password" {}

resource "google_sql_database" "main" {
  name     = "main"
  instance = google_sql_database_instance.main_primary.name
}
resource "google_sql_database_instance" "main_primary" {
  name             = var.db_name
  database_version = "POSTGRES_11"
  depends_on       = [google_service_networking_connection.private_vpc_connection]
  settings {
    tier              = "custom-1-3840"
    availability_type = "ZONAL"
    disk_size         = 10 # 10 GB is the smallest disk size
    location_preference {
      zone = var.cluster_location
    }
    ip_configuration {
      private_network = google_compute_network.vpc.self_link
    }
    backup_configuration {
      enabled = true
    }
  }
}
resource "google_sql_user" "db_user" {
  name     = var.db_user
  instance = google_sql_database_instance.main_primary.name
  password = var.db_password
}
