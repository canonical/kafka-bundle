model = "prod"
cloud = "localhost"

kafka_cluster = {
  "kafka" = {
    units   = 3
  },
  "zookeeper" = {
    units   = 5
  },
  "data-integrator" = {
    units   = 1
  }
}
