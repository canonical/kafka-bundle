resource "juju_machine" "kafka" {
  count       = var.kafka.units
  model       = juju_model.kafka.name
  base        = "ubuntu@22.04"
  name        = "kafka-${count.index}"
  constraints = "cores=${var.kafka.cpu_core_count} mem=${var.kafka.memory_gb}G root-disk=${var.kafka.root_disk_storage_gb}G"
}

resource "juju_machine" "zookeeper" {
  count       = var.zookeeper.units
  model       = juju_model.kafka.name
  base        = "ubuntu@22.04"
  name        = "zookeeper-${count.index}"
  constraints = "cores=${var.zookeeper.cpu_core_count} mem=${var.zookeeper.memory_gb}G root-disk=${var.zookeeper.root_disk_storage_gb}G"
}
