locals {
<<<<<<< HEAD
  deployment_mode     = var.controller.units > 0 ? "split" : "single"
  controller_app_name = var.controller.units > 0 ? var.controller.app_name : var.broker.app_name
  connect_app_name    = var.connect.units > 0 ? module.connect[0].app_name : null
  karapace_app_name   = var.karapace.units > 0 ? module.karapace[0].app_name : null
  ui_app_name         = var.ui.units > 0 ? module.ui[0].app_name : null
  integrator_app_name = var.integrator.units > 0 ? juju_application.integrator[0].name : null
  cos_enabled         = var.cos_offers.dashboard != null ? true : false
  tls_enabled         = var.tls_offer != null ? true : false
  cos_agent_charm     = "grafana-agent"
  cos_agent_channel   = "1/stable"
=======
  connect_app_name  = var.connect.units > 0 ? module.connect[0].app_name : null
  karapace_app_name = var.karapace.units > 0 ? module.karapace[0].app_name : null
  ui_app_name       = var.ui.units > 0 ? module.ui[0].app_name : null
  cos_enabled       = var.cos_offers.dashboard != null ? true : false
  tls_enabled       = var.tls_offer != null ? true : false
  cos_agent_charm   = "grafana-agent"
  cos_agent_channel = "1/stable"
>>>>>>> a1d722e (fix: wrong ternary)
}

module "broker" {
  source      = "git::https://github.com/canonical/kafka-operator//terraform?ref=main"
  model       = var.model
  app_name    = var.broker.app_name
  channel     = var.broker.channel
  revision    = var.broker.revision
  constraints = var.broker.constraints
  base        = var.broker.base
  units       = var.broker.units
  storage     = var.broker.storage
  config = merge(var.broker.config, {
    profile = var.profile
    roles   = local.deployment_mode == "single" ? "broker,controller" : "broker"
  })
}

module "controller" {
  count       = local.deployment_mode == "split" ? 1 : 0
  source      = "git::https://github.com/canonical/kafka-operator//terraform?ref=main"
  model       = var.model
  app_name    = var.controller.app_name
  channel     = var.controller.channel
  revision    = var.controller.revision
  constraints = var.controller.constraints
  base        = var.controller.base
  units       = var.controller.units
  storage     = var.controller.storage
  config = merge(var.controller.config, {
    profile = var.profile
    roles   = "controller"
  })
}


module "connect" {
  count       = var.connect.units > 0 ? 1 : 0
  source      = "git::https://github.com/canonical/kafka-connect-operator//terraform?ref=main"
  model       = var.model
  app_name    = var.connect.app_name
  channel     = var.connect.channel
  revision    = var.connect.revision
  constraints = var.connect.constraints
  base        = var.connect.base
  units       = var.connect.units
  config      = var.connect.config
}

module "karapace" {
  count       = var.karapace.units > 0 ? 1 : 0
  source      = "git::https://github.com/canonical/karapace-operator//terraform?ref=main"
  model       = var.model
  app_name    = var.karapace.app_name
  channel     = var.karapace.channel
  revision    = var.karapace.revision
  constraints = var.karapace.constraints
  base        = var.karapace.base
  units       = var.karapace.units
  config      = var.karapace.config
}

module "ui" {
  count       = var.ui.units > 0 ? 1 : 0
  source      = "git::https://github.com/canonical/kafka-ui-operator//terraform?ref=main"
  model       = var.model
  app_name    = var.ui.app_name
  channel     = var.ui.channel
  revision    = var.ui.revision
  constraints = var.ui.constraints
  base        = var.ui.base
  units       = var.ui.units
  config      = var.ui.config
}
