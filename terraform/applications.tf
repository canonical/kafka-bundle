resource "juju_application" "integrator" {
  count             = var.integrator.units > 0 ? 1 : 0
  model_uuid        = var.model_uuid
  name              = var.integrator.app_name
  units             = length(var.integrator.machines) == 0 ? var.integrator.units : null
  machines          = length(var.integrator.machines) > 0 ? var.integrator.machines : null
  endpoint_bindings = var.integrator.endpoint_bindings

  charm {
    name     = "data-integrator"
    channel  = var.integrator.channel
    revision = var.integrator.revision
    base     = var.integrator.base
  }

  config = var.integrator.config
}

locals {
  # Machine IDs hosting the brokers, either user-provided or created by this module.
  broker_machine_ids = (
    length(var.broker.machines) > 0
    ? tolist(var.broker.machines)
    : juju_machine.broker_machines[*].machine_id
  )
}

resource "juju_application" "rack" {
  count       = var.enable_rack_awareness ? var.broker.units : 0
  model_uuid  = var.model_uuid
  name        = "rack-of-machine${juju_machine.broker_machines[count.index].machine_id}"
  machines    = [local.broker_machine_ids[count.index]]
  constraints = var.broker.constraints

  config = {
    "broker-rack" = lookup(var.rack_config, local.broker_machine_ids[count.index], "default")
  }

  endpoint_bindings = var.broker.endpoint_bindings

  charm {
    name    = "kafka-broker-rack-awareness"
    channel = "latest/stable"
    base    = var.broker.base
  }

}


resource "juju_application" "kafka_cos_agent" {
  count      = local.cos_enabled ? 1 : 0
  model_uuid = var.model_uuid
  name       = "${module.broker.app_name}-cos-agent"

  charm {
    name    = local.cos_agent_charm
    channel = local.cos_agent_channel
    base    = var.broker.base
  }
}

resource "juju_application" "kraft_cos_agent" {
  count      = local.cos_enabled && local.deployment_mode == "split" ? 1 : 0
  model_uuid = var.model_uuid
  name       = "${module.controller[0].app_name}-cos-agent"

  charm {
    name    = local.cos_agent_charm
    channel = local.cos_agent_channel
    base    = var.controller.base
  }
}

resource "juju_application" "connect_cos_agent" {
  count      = local.cos_enabled && var.connect.units > 0 ? 1 : 0
  model_uuid = var.model_uuid
  name       = "${module.connect[0].app_name}-cos-agent"

  charm {
    name    = local.cos_agent_charm
    channel = local.cos_agent_channel
    base    = var.connect.base
  }
}
