model = "prod"
cloud = "localhost"

kafka = {
  units                = 3
  cpu_core_count       = 24
  memory_gb            = 64
  root_disk_storage_gb = 300
}

zookeeper = {
  units                = 5
  cpu_core_count       = 8
  memory_gb            = 16
  root_disk_storage_gb = 100
}
