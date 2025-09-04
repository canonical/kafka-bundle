# Integrations between Kafka products

resource "juju_integration" "kafka_connect" {
  count = var.connect.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.kafka.broker_app_name
    endpoint = "kafka-client"
  }

  application {
    name = module.connect[0].app_name
  }
}

resource "juju_integration" "kafka_karapace" {
  count = var.karapace.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.kafka.broker_app_name
    endpoint = "kafka-client"
  }

  application {
    name = module.karapace[0].app_name
  }
}

resource "juju_integration" "kafka_ui" {
  count = var.ui.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.kafka.broker_app_name
    endpoint = "kafka-client"
  }

  application {
    name = module.ui[0].app_name
  }
}


resource "juju_integration" "karapace_ui" {
  count = var.karapace.units > 0 && var.ui.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.karapace[0].app_name
    endpoint = "karapace"
  }

  application {
    name = module.ui[0].app_name
  }
}

resource "juju_integration" "kafka_connect_ui" {
  count = var.connect.units > 0 && var.ui.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.connect[0].app_name
    endpoint = "connect-client"
  }

  application {
    name = module.ui[0].app_name
  }
}

resource "juju_integration" "integrator_kafka" {
  model = var.model

  application {
    name = juju_application.integrator.name
  }

  application {
    name = module.kafka.broker_app_name
  }
}

# TLS Integrations

resource "juju_integration" "kafka_tls" {
  count = local.tls_enabled ? 1 : 0
  model = var.model

  application {
    name     = module.kafka.broker_app_name
    endpoint = "certificates"
  }

  application {
    offer_url = var.tls_offer
  }
}

resource "juju_integration" "kafka_connect_tls" {
  count = local.tls_enabled && var.connect.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.connect[0].app_name
    endpoint = "certificates"
  }

  application {
    offer_url = var.tls_offer
  }
}

resource "juju_integration" "karapace_tls" {
  count = local.tls_enabled && var.karapace.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.karapace[0].app_name
    endpoint = "certificates"
  }

  application {
    offer_url = var.tls_offer
  }
}

resource "juju_integration" "kafka_ui_tls" {
  count = local.tls_enabled && var.ui.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.ui[0].app_name
    endpoint = "certificates"
  }

  application {
    offer_url = var.tls_offer
  }
}

# COS Integrations 

resource "juju_integration" "kafka_cos" {
  count = local.cos_enabled ? 1 : 0
  model = var.model

  application {
    name     = module.kafka.broker_app_name
    endpoint = "cos-agent"
  }

  application {
    name = juju_application.kafka_cos_agent[0].name
  }

}

resource "juju_integration" "kraft_cos" {
  count = local.cos_enabled && module.kafka.deployment_mode == "split" ? 1 : 0
  model = var.model

  application {
    name     = module.kafka.controller_app_name
    endpoint = "cos-agent"
  }

  application {
    name = juju_application.kraft_cos_agent[0].name
  }

}

resource "juju_integration" "connect_cos" {
  count = local.cos_enabled && var.connect.units > 0 ? 1 : 0
  model = var.model

  application {
    name     = module.connect[0].app_name
    endpoint = "cos-agent"
  }

  application {
    name = juju_application.connect_cos_agent[0].name
  }

}
