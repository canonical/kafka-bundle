resource "juju_model" "kafka" {
  name = var.model

  cloud {
    name = var.cloud
  }

  config = {
    logging-config              = "<root>=DEBUG"
    update-status-hook-interval = "2m"
  }
}
