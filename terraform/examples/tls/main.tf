resource "juju_model" "tls_provider" {
  name = "tls"
  cloud {
    name = var.cloud
  }
}


resource "juju_model" "kafka" {
  name = var.model
  cloud {
    name = var.cloud
  }

  config = {
    logging-config              = "<root>=INFO"
    update-status-hook-interval = "3m"
  }
}


module "tls" {
  depends_on  = [juju_model.tls_provider]
  source      = "git::https://github.com/canonical/self-signed-certificates-operator//terraform?ref=rev326"
  model       = juju_model.tls_provider.name
  app_name    = "certificates"
  channel     = "1/stable"
  revision    = 317
  constraints = "arch=amd64"
  base        = "ubuntu@24.04"
  units       = 1
  config = {
    ca-common-name = var.certificate_common_name
  }
}

module "kafka" {
  source     = "../../"
  depends_on = [juju_model.kafka, module.tls]
  model      = var.model
  profile    = var.profile
  tls_offer  = module.tls.offers.certificates.url
  broker = {
    units = 1
  }
  controller = {
    units = 1
  }
  connect = {
    units = 3
  }
  karapace = {
    units = 1
  }
  ui = {
    units = 1
  }
  integrator = {
    units = 1
  }
}