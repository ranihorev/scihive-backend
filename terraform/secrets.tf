resource "google_secret_manager_secret" "web_server_secrets" {
  secret_id = "web-server-secrets"

  replication {
    user_managed {
      replicas {
        location = "us-central1"
      }
    }
  }
}
