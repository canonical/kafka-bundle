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
    units     = optional(number, 1)
    channel   = optional(string, "edge")
    series    = optional(string, "jammy")
    config    = optional(map(string), {})
    relations = optional(list(string), [])
  }))
}

variable "disable_tls" {
  description = "Do not enable TLS for the cluster"
  type        = bool
  default     = false
}
