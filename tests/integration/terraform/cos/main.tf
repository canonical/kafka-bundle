# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# NOTE [cross-controller]: This module deploys COS-lite on the same Juju controller
# as the Kafka machines model. In a real cross-substrate setup, COS-lite would run
# on a k8s cloud/controller. To support that, a second Juju provider alias targeting
# the k8s controller would need to be configured in providers.tf and passed here.

module "cos-lite" {
  source       = "git::https://github.com/canonical/observability-stack//terraform/cos-lite?ref=main"
  model_uuid   = var.model_uuid
  channel      = var.channel
  internal_tls = var.internal_tls
}
