# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variable "model_uuid" {
  description = "The Juju Model UUID for the COS model"
  type        = string
}

variable "channel" {
  description = "Channel for COS-lite charms (must start with 'dev/')"
  type        = string
  default     = "dev/edge"
}

variable "internal_tls" {
  description = "Whether COS-lite should be deployed with self-signed-certificates"
  type        = bool
  default     = false
}
