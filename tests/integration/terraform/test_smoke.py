#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Smoke test suite for a Charmed Apache Kafka solution deployment."""

import logging

import pytest
from jubilant import Juju
from tests.integration.terraform.component_validation import ComponentValidation
from tests.integration.terraform.helpers import all_active_idle, is_deployed

logger = logging.getLogger(__name__)


class TestSmoke:
    """Smoke testing suite for Charmed Apache Kafka."""

    validator: ComponentValidation | None = None

    def _get_tls_state(self, juju) -> bool:
        """Check if TLS is being used on the deployment or not."""
        status = juju.status()
        tls_enabled = False
        for app in status.apps:
            if status.apps[app].charm_name != "kafka":
                continue

            unit = next(iter(status.apps[app].units))
            if tls_enabled := "9093/tcp" in status.apps[app].units[unit].open_ports:
                break
        logger.debug(f"TLS enabled: {tls_enabled}")
        return tls_enabled

    @pytest.fixture(autouse=True)
    def setup_method(self, juju: Juju):
        if not self.validator:
            self.validator = ComponentValidation(juju=juju, tls=self._get_tls_state(juju=juju))

    def test_deployment_active(self, juju: Juju):
        juju.wait(
            lambda status: all_active_idle(status),
            delay=5,
            successes=6,
            timeout=3600,
        )

    def test_kafka_admin_operations(self):
        """Test admin ops on the Kafka cluster using charmed-kafka snap apps."""
        self.validator.test_kafka_admin_operations()

    def test_kafka_producer_consumer(self):
        """Test produce/consume using charmed-kafka snap apps."""
        self.validator.test_kafka_producer_consumer()

    def test_schema_registry(self, juju: Juju):
        """Test Karapace health, and schema addition/deletion."""
        if not is_deployed(juju, "karapace"):
            logger.info("karapace is not deployed, skipping test_schema_registry")
            return

        self.validator.test_karapace()

    def test_kafka_ui(self, juju: Juju):
        """Test Kafka UI is accessible."""
        if not is_deployed(juju, "kafka-ui"):
            logger.info("kafka-ui is not deployed, skipping test_kafka_ui")
            return

        self.validator.test_ui_accessibility()

    def test_kafka_connect_health(self, juju: Juju):
        """Test Kafka Connect health endpoints."""
        if not is_deployed(juju, "kafka-connect"):
            logger.info("kafka-connect is not deployed, skipping test_kafka_connect_health")
            return

        self.validator.test_connect_endpoints()

    def test_connector_lifecycle(self, juju: Juju):
        """Test connector lifecycle by adding and then deleting a MM2 connector."""
        if not is_deployed(juju, "kafka-connect"):
            logger.info("kafka-connect is not deployed, skipping test_connector_lifecycle")
            return

        self.validator.test_create_mm2_connector()
