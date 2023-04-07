locals {
  tls_config = var.tls_config.generate-self-signed-certificates ? var.tls_config : merge({ ca-common-name = "" }, var.tls_config)
  tls = {
    "tls-certificates-operator" = {
      units   = 1
      channel = "edge"
      series  = "jammy"
      config  = local.tls_config
    }
  }

  applications = var.disable_tls ? var.kafka_cluster : merge(var.kafka_cluster, local.tls)
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
