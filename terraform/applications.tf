resource "juju_application" "integrator" {
  model = var.model
  name  = var.integrator.app_name
  units = var.integrator.units

  charm {
    name     = "data-integrator"
    channel  = var.integrator.channel
    revision = var.integrator.revision
    base     = var.integrator.base
  }

  config = var.integrator.config
}


resource "juju_application" "kafka_cos_agent" {
  count = local.cos_enabled ? 1 : 0
  model = var.model
  name  = "${module.kafka.broker_app_name}-cos-agent"

  charm {
    name    = local.cos_agent_charm
    channel = local.cos_agent_channel
    base    = var.kafka.base
  }
}

resource "juju_application" "kraft_cos_agent" {
  count = local.cos_enabled && module.kafka.deployment_mode == "split" ? 1 : 0
  model = var.model
  name  = "${module.kafka.controller_app_name}-cos-agent"

  charm {
    name    = local.cos_agent_charm
    channel = local.cos_agent_channel
    base    = var.kafka.base
  }
}

resource "juju_application" "connect_cos_agent" {
  count = local.cos_enabled && var.connect.units > 0 ? 1 : 0
  model = var.model
  name  = "${module.connect[0].app_name}-cos-agent"

  charm {
    name    = local.cos_agent_charm
    channel = local.cos_agent_channel
    base    = var.connect.base
  }
}