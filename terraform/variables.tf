variable "model" {
  description = "The name of the Juju Model to deploy to"
  type        = string
}

variable "profile" {
  description = "The deployment profile to use, either 'production' or 'testing'"
  type        = string
  default     = "testing"
}

variable "tls_offer" {
  description = "TLS Provider endpoint to be used on Client relations."
  type        = string
  default     = null
}

variable "cos_offers" {
  type = object({
    dashboard = optional(string, null),
    metrics   = optional(string, null),
    logging   = optional(string, null)
  })

  default = {}

  validation {
    condition = ((
      var.cos_offers.dashboard != null &&
      var.cos_offers.metrics != null &&
      var.cos_offers.logging != null
      ) || (
      var.cos_offers.dashboard == null &&
      var.cos_offers.metrics == null &&
      var.cos_offers.logging == null
    ))
    error_message = "Either all or none of the COS offers should be provided: 'dashboard', 'metrics', 'logging'."
  }
}

variable "broker" {
  description = "Defines the Apache Kafka broker application configuration"
  type = object({
    app_name    = optional(string, "kafka-broker")
    channel     = optional(string, "4/edge")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 3)
    storage     = optional(map(string), {})
  })
  default = {}
}

variable "controller" {
  description = "Defines the Apache Kafka KRaft controller application configuration"
  type = object({
    app_name    = optional(string, "kafka-controller")
    channel     = optional(string, "4/edge")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 3)
    storage     = optional(map(string), {})
  })
  default = {}

  validation {
    condition     = var.controller.units == 0 || var.controller.units % 2 != 0
    error_message = "The number of Apache Kafka KRaft controllers must be odd (e.g., 1, 3, 5, ...)."
  }
}


variable "connect" {
  description = "Defines the Kafka Connect application configuration"
  type = object({
    app_name    = optional(string, "kafka-connect")
    channel     = optional(string, "latest/edge")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@22.04")
    units       = optional(number, 1)
  })
  default = {}
}

variable "karapace" {
  description = "Defines the Karapace application configuration"
  type = object({
    app_name    = optional(string, "karapace")
    channel     = optional(string, "latest/edge")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })
  default = {}
}

variable "ui" {
  description = "Defines the Kafbat Kafka UI application configuration"
  type = object({
    app_name    = optional(string, "kafka-ui")
    channel     = optional(string, "latest/edge")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })
  default = {}
}

variable "integrator" {
  description = "Defines the Integrator application configuration"
  type = object({
    app_name = optional(string, "data-integrator")
    channel  = optional(string, "latest/edge")
    config = optional(map(string), {
      topic-name       = "__admin-user"
      extra-user-roles = "admin"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })
  default = {}
}
