resource "juju_application" "kafka" {
  depends_on = [juju_machine.kafka]
  model      = juju_model.kafka.name

  units = var.kafka.units

  charm {
    name    = "kafka"
    channel = var.kafka.channel
    series  = var.kafka.series
  }

  # loops over machine ids looking like lh:2:0, grabs juju machine id 2
  placement = join(",", [for machine in juju_machine.kafka : split(":", machine.id)[1]])

  config = var.kafka.config
}

resource "juju_application" "zookeeper" {
  depends_on = [juju_machine.zookeeper]
  model      = juju_model.kafka.name

  units = var.zookeeper.units

  charm {
    name    = "zookeeper"
    channel = var.zookeeper.channel
    series  = var.zookeeper.series
  }

  # loops over machine ids looking like lh:2:0, grabs juju machine id 2
  placement = join(",", [for machine in juju_machine.zookeeper : split(":", machine.id)[1]])

  config = var.zookeeper.config
}

resource "juju_application" "tls" {
  model = juju_model.kafka.name

  units = var.tls.units

  charm {
    name    = "tls-certificates-operator"
    channel = var.tls.channel
    series  = var.tls.series
  }

  config = var.tls.config
}

resource "juju_application" "integrator" {
  model = juju_model.kafka.name

  units = var.integrator.units

  charm {
    name    = "data-integrator"
    channel = var.integrator.channel
    series  = var.integrator.series
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

