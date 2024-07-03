variable "model" {
  description = "The name of the Juju Model to deploy to"
  type        = string
  default     = "kafka"
}

variable "cloud" {
  description = "The name of the Juju Cloud to deploy to"
  type        = string
  default     = "localhost"
}

variable "kafka" {
  description = "Defines the Kafka application and machine configuration"
  type = object({
    units                = optional(number, 1)
    channel              = optional(string, "3/stable")
    base                 = optional(string, "ubuntu@22.04")
    series               = optional(string, "jammy")
    config               = optional(map(string), {})
    cpu_core_count       = optional(number, 2)
    memory_gb            = optional(number, 2)
    root_disk_storage_gb = optional(number, 1)
  })
  default = {}
}

variable "zookeeper" {
  description = "Defines the ZooKeeper application and machine configuration"
  type = object({
    units                = optional(number, 3)
    channel              = optional(string, "3/stable/sf")
    base                 = optional(string, "ubuntu@22.04")
    series               = optional(string, "jammy")
    config               = optional(map(string), {})
    cpu_core_count       = optional(number, 2)
    memory_gb            = optional(number, 2)
    root_disk_storage_gb = optional(number, 1)
  })
  default = {}
}

variable "tls" {
  description = "Defines the TLS application configuration"
  type = object({
    units   = optional(number, 1)
    channel = optional(string, "edge")
    base    = optional(string, "ubuntu@22.04")
    series  = optional(string, "jammy")
    config = optional(map(string), {
      ca-common-name = "Kafka"
    })
  })
  default = {}
}

variable "integrator" {
  description = "Defines the Integrator application configuration"
  type = object({
    units   = optional(number, 1)
    channel = optional(string, "edge")
    base    = optional(string, "ubuntu@22.04")
    series  = optional(string, "jammy")
    config = optional(map(string), {
      topic-name       = "default"
      extra-user-roles = "admin"
    })
  })
  default = {}
}
