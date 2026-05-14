# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variable "model_uuid" {
  description = "The Juju Model UUID for the COS model"
  type        = string
}

variable "risk" {
  description = "Risk level that the COS-lite applications are deployed from"
  type        = string
  default     = "edge"
}

variable "internal_tls" {
  description = "Whether COS-lite should be deployed with self-signed-certificates"
  type        = bool
  default     = false
}
