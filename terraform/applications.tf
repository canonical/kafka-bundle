locals {
  tls_config = var.tls_config.generate-self-signed-certificates ? var.tls_config : merge({ ca-common-name = "" }, var.tls_config)

  tls = {
    "tls-certificates-operator" = {
      units     = 1
      channel   = "edge"
      series    = "jammy"
      config    = local.tls_config
      relations = ["zookeeper:certificates", "kafka:certificates"]
    }
  }

  applications = var.disable_tls ? var.kafka_cluster : merge(var.kafka_cluster, local.tls)
  relations    = flatten([for provider, config in local.applications : [for relation in config.relations : ["${provider},${relation}"]]])
}

resource "juju_application" "kafka_cluster" {
  for_each = local.applications

  model = juju_model.kafka.name

  units = each.value.units

  charm {
    name    = each.key
    channel = each.value.channel
    series  = each.value.series
  }

  config = each.value.config
}

resource "juju_integration" "kafka_relations" {
  for_each = toset(local.relations)

  model = juju_model.kafka.name

  application {
    name = split(",", each.value)[0]
  }

  application {
    name     = split(":", split(",", each.value)[1])[0]
    endpoint = split(":", split(",", each.value)[1])[1]
  }

  depends_on = [juju_application.kafka_cluster]
}
