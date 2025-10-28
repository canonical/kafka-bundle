variable "model" {
  description = "The name of the Juju Model to deploy to"
  type        = string
  default     = "kafka"
}

variable "cloud" {
  description = "The name of the Juju VM Cloud to deploy to"
  type        = string
  default     = "localhost"
}

variable "certificate_common_name" {
  description = "Common name for the certificate to be used in self-signed provider"
  type        = string
  default     = "Kafka"
}

variable "profile" {
  description = "The deployment profile to use, either 'production' or 'testing'"
  type        = string
  default     = "testing"
}
