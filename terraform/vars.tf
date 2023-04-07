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

variable "kafka_cluster" {
  description = "Manages the Kafka applications to deploy"
  type = map(object({
    units   = number
    channel = string
    series  = string
    config  = map(string)
  }))
  default = {
    "kafka" = {
      units   = 1
      channel = "edge"
      series  = "jammy"
      config  = {}
    },
    "zookeeper" = {
      units   = 1
      channel = "edge"
      series  = "jammy"
      config  = {}
    },
    "data-integrator" = {
      units   = 1
      channel = "edge"
      series  = "jammy"
      config = {
        topic-name       = "default"
        extra-user-roles = "admin"
      }
    },
  }
}

variable "disable_tls" {
  description = "Do not enable TLS for the cluster"
  type = bool
  default = false
}

variable "tls_config" {
  description = "Base64 encoded certificate and CA to create sign internal certificates for the Kafka cluster."
  type = object({
    certificate                       = optional(string)
    ca                                = optional(string)
    ca-common-name                    = optional(string, "Kafka")
    generate-self-signed-certificates = bool
  })
  default = {
    generate-self-signed-certificates = true
  }
}
