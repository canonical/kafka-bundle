variable "model_uuid" {
  description = "The Model UUID to deploy to"
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

variable "enable_rack_awareness" {
  description = "Whether the deployment is using machines in separate racks (AZs) or not."
  type        = bool
  default     = false
}

variable "oauth_offers" {
  description = "OAuth offers to be used on Kafka and Kafka UI."
  type = object({
    oauth    = optional(string, null),
    oauth_ca = optional(string, null)
  })

  default = {}

  validation {
    condition = ((
      var.oauth_offers.oauth != null &&
      var.oauth_offers.oauth_ca != null
      ) || (
      var.oauth_offers.oauth == null &&
      var.oauth_offers.oauth_ca == null
    ))
    error_message = "Either all or none of the OAuth offers should be provided: 'oauth', 'oauth_ca'."
  }
}

variable "cos_offers" {
  description = "COS offers for observability."
  type = object({
    dashboard           = optional(string, null),
    metrics             = optional(string, null),
    logging             = optional(string, null),
    tracing             = optional(string, null),
    offering_controller = optional(string, null),
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
    channel     = optional(string, "4/stable")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 3)
    storage     = optional(map(string), {})
    machines    = optional(set(string), [])
    endpoint_bindings = optional(set(object({
      space    = string
      endpoint = optional(string)
  })), []) })
  default = {}
}

variable "controller" {
  description = "Defines the Apache Kafka KRaft controller application configuration"
  type = object({
    app_name    = optional(string, "kafka-controller")
    channel     = optional(string, "4/stable")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 3)
    storage     = optional(map(string), {})
    machines    = optional(set(string), [])
    endpoint_bindings = optional(set(object({
      space    = string
      endpoint = optional(string)
    })), [])
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
    channel     = optional(string, "4/stable")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
    machines    = optional(set(string), [])
    endpoint_bindings = optional(set(object({
      space    = string
      endpoint = optional(string)
    })), [])
  })
  default = {}
}

variable "karapace" {
  description = "Defines the Karapace application configuration"
  type = object({
    app_name    = optional(string, "karapace")
    channel     = optional(string, "latest/stable")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
    machines    = optional(set(string), [])
    endpoint_bindings = optional(set(object({
      space    = string
      endpoint = optional(string)
    })), [])
  })
  default = {}
}

variable "ui" {
  description = "Defines the Kafbat Kafka UI application configuration"
  type = object({
    app_name    = optional(string, "kafka-ui")
    channel     = optional(string, "latest/stable")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
    machines    = optional(set(string), [])
    endpoint_bindings = optional(set(object({
      space    = string
      endpoint = optional(string)
    })), [])
  })
  default = {}
}

variable "integrator" {
  description = "Defines the Integrator application configuration"
  type = object({
    app_name = optional(string, "data-integrator")
    channel  = optional(string, "latest/stable")
    config = optional(map(string), {
      topic-name       = "__admin-user"
      extra-user-roles = "admin"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number, null)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
    machines    = optional(set(string), [])
    endpoint_bindings = optional(set(object({
      space    = string
      endpoint = optional(string)
    })), [])
  })
  default = {}
}
