resource "juju_application" "kafka" {
  depends_on = [juju_machine.kafka]
  model      = juju_model.kafka.name

  units = var.kafka.units

  charm {
    name    = "kafka"
    channel = var.kafka.channel
    base    = var.kafka.base
  }

  placement = join(",", juju_machine.kafka[*].machine_id)

  config = var.kafka.config
}

resource "juju_application" "zookeeper" {
  depends_on = [juju_machine.zookeeper]
  model      = juju_model.kafka.name

  units = var.zookeeper.units

  charm {
    name    = "zookeeper"
    channel = var.zookeeper.channel
    base    = var.zookeeper.base
  }

  placement = join(",", juju_machine.zookeeper[*].machine_id)

  config = var.zookeeper.config
}

resource "juju_application" "tls" {
  model = juju_model.kafka.name

  units = var.tls.units

  charm {
    name    = "self-signed-certificates"
    channel = var.tls.channel
    base    = var.tls.base
  }

  config = var.tls.config
}

resource "juju_application" "integrator" {
  model = juju_model.kafka.name

  units = var.integrator.units

  charm {
    name    = "data-integrator"
    channel = var.integrator.channel
    base    = var.integrator.base
  }

  config = var.integrator.config
}

resource "juju_integration" "kafka_zookeeper" {
  model = juju_model.kafka.name

  application {
    name = juju_application.kafka.name
  }

  application {
    name = juju_application.zookeeper.name
  }
}

resource "juju_integration" "zookeeper_tls" {
  model = juju_model.kafka.name

  application {
    name = juju_application.zookeeper.name
  }

  application {
    name = juju_application.tls.name
  }
}

resource "juju_integration" "kafka_tls" {
  model = juju_model.kafka.name

  application {
    name     = juju_application.kafka.name
    endpoint = "certificates"
  }

  application {
    name = juju_application.tls.name
  }
}

resource "juju_integration" "integrator_kafka" {
  model = juju_model.kafka.name

  application {
    name = juju_application.integrator.name
  }

  application {
    name = juju_application.kafka.name
  }
}

