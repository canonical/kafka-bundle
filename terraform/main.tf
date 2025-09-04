locals {
  connect_app_name  = var.connect.units <= 0 ? module.connect[0].app_name : null
  karapace_app_name = var.karapace.units > 0 ? module.karapace[0].app_name : null
  ui_app_name       = var.ui.units > 0 ? module.ui[0].app_name : null
  cos_enabled       = var.cos_offers.dashboard != null ? true : false
  tls_enabled       = var.tls_offer != null ? true : false
  cos_agent_charm   = "grafana-agent"
  cos_agent_channel = "1/stable"
}

module "kafka" {
  source           = "git::https://github.com/canonical/kafka-operator//terraform?ref=feat/terraform"
  model            = var.model
  app_name         = var.kafka.app_name
  channel          = var.kafka.channel
  revision         = var.kafka.revision
  constraints      = var.kafka.constraints
  base             = var.kafka.base
  units            = var.kafka.units
  controller_units = var.kafka.controller_units
  config = {
    profile = var.profile
  }
}

module "connect" {
  count       = var.connect.units > 0 ? 1 : 0
  source      = "git::https://github.com/canonical/kafka-connect-operator//terraform?ref=feat/terraform"
  model       = var.model
  app_name    = var.connect.app_name
  channel     = var.connect.channel
  revision    = var.connect.revision
  constraints = var.connect.constraints
  base        = var.connect.base
  units       = var.connect.units
}

module "karapace" {
  count       = var.karapace.units > 0 ? 1 : 0
  source      = "git::https://github.com/canonical/karapace-operator//terraform?ref=feat/terraform"
  model       = var.model
  app_name    = var.karapace.app_name
  channel     = var.karapace.channel
  revision    = var.karapace.revision
  constraints = var.karapace.constraints
  base        = var.karapace.base
  units       = var.karapace.units
}

module "ui" {
  count       = var.ui.units > 0 ? 1 : 0
  source      = "git::https://github.com/canonical/kafka-ui-operator//terraform?ref=feat/terraform"
  model       = var.model
  app_name    = var.ui.app_name
  channel     = var.ui.channel
  revision    = var.ui.revision
  constraints = var.ui.constraints
  base        = var.ui.base
  units       = var.ui.units
}
