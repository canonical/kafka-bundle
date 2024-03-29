#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collection of globals common to the Kafka bundle."""

BUNDLE_PATH = "releases/3/kafka/bundle.yaml"
BUNDLE_BUILD = "build/kafka-bundle.zip"
APP_CHARM_PATH = "tests/integration/bundle/app-charm"
ZOOKEEPER = "zookeeper"
KAFKA = "kafka"
TLS_CHARM_NAME = "self-signed-certificates"

ZOOKEEPER_CONF_PATH = "/var/snap/charmed-zookeeper/current/etc/zookeeper"
KAFKA_CLIENT_PROPERTIES = "/var/snap/charmed-kafka/current/etc/kafka/client.properties"
TLS_PORT = 9093
