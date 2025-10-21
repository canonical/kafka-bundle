#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests specific functionality of each component."""

import logging
import re
from subprocess import PIPE, CalledProcessError, check_output
from uuid import uuid4

import jubilant
import requests
from tests.integration.terraform.helpers import (
    CA_FILE,
    CONNECT_API_PORT,
    CONNECT_APP_NAME,
    KAFKA_BROKER_APP_NAME,
    KAFKA_UI_APP_NAME,
    KAFKA_UI_PORT,
    KAFKA_UI_PROTO,
    KAFKA_UI_SECRET_KEY,
    KARAPACE_APP_NAME,
    KARAPACE_PORT,
    SECURITY_PROTOCOL_PORTS,
    check_socket,
    get_secret_by_label,
)

logger = logging.getLogger(__name__)


class ComponentValidation:
    """Test all Kafka ecosystem components functionality."""

    def __init__(self, model: str, tls: bool = False):
        self.model = model
        self.tls = tls

    def test_kafka_admin_operations(self):
        """Test basic Kafka admin operations.

        Creates `test` topic and adds ACLs for principal `User:*`.
        """
        bootstrap_server = self.get_kafka_bootstrap_server(unit_name=f"{KAFKA_BROKER_APP_NAME}/0")
        _ = check_output(
            f"JUJU_MODEL={self.model} juju ssh {KAFKA_BROKER_APP_NAME}/0 sudo -i 'sudo charmed-kafka.topics --bootstrap-server {bootstrap_server} --command-config $CONF/client.properties -create -topic test'",
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
        )

        _ = check_output(
            f"JUJU_MODEL={self.model} juju ssh {KAFKA_BROKER_APP_NAME}/0 sudo -i 'sudo charmed-kafka.acls --bootstrap-server {bootstrap_server} --add --allow-principal=User:* --operation READ --operation WRITE --operation CREATE --topic test --command-config $CONF/client.properties'",
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
        )

        _ = check_output(
            f"JUJU_MODEL={self.model} juju ssh {KAFKA_BROKER_APP_NAME}/0 sudo -i 'sudo charmed-kafka.topics --bootstrap-server {bootstrap_server} --command-config $CONF/client.properties -delete -topic test'",
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
        )

    def test_kafka_producer_consumer(self):
        """Test Kafka producer and consumer operations using charmed-kafka CLI tools."""
        test_topic = f"test-topic-{uuid4().hex[:8]}"
        test_message = f"test-message-{uuid4().hex}"
        bootstrap_server = self.get_kafka_bootstrap_server(unit_name=f"{KAFKA_BROKER_APP_NAME}/0")

        try:
            # Create topic using charmed-kafka.topics
            _ = check_output(
                f"JUJU_MODEL={self.model} juju ssh {KAFKA_BROKER_APP_NAME}/0 sudo -i 'sudo charmed-kafka.topics --bootstrap-server {bootstrap_server} --command-config $CONF/client.properties --create --topic {test_topic} --partitions 1 --replication-factor 1'",
                stderr=PIPE,
                shell=True,
                universal_newlines=True,
            )

            # Produce message using charmed-kafka.console-producer
            check_output(
                f"JUJU_MODEL={self.model} juju ssh {KAFKA_BROKER_APP_NAME}/0 sudo -i 'echo \"{test_message}\" | sudo charmed-kafka.console-producer --bootstrap-server {bootstrap_server} --producer.config $CONF/client.properties --topic {test_topic}'",
                stderr=PIPE,
                shell=True,
                universal_newlines=True,
            )

            output = check_output(
                f"JUJU_MODEL={self.model} juju ssh {KAFKA_BROKER_APP_NAME}/0 sudo -i 'sudo timeout 10 charmed-kafka.console-consumer --bootstrap-server {bootstrap_server} --consumer.config $CONF/client.properties --topic {test_topic} --from-beginning --max-messages 1'",
                stderr=PIPE,
                shell=True,
                universal_newlines=True,
            )

            # Verify message was consumed
            assert test_message in output.strip()

        finally:
            # Clean up topic
            try:
                check_output(
                    f"JUJU_MODEL={self.model} juju ssh {KAFKA_BROKER_APP_NAME}/0 sudo -i 'sudo charmed-kafka.topics --bootstrap-server {bootstrap_server} --command-config $CONF/client.properties --delete --topic {test_topic}'",
                    stderr=PIPE,
                    shell=True,
                    universal_newlines=True,
                )
            except CalledProcessError:
                # Ignore cleanup errors
                pass

    def test_karapace(self, juju: jubilant.Juju):
        """Test creating a schema subject in Karapace, listing it and then deletes it."""
        schema_name = "test-key"
        result = juju.run(unit=f"{KARAPACE_APP_NAME}/0", action="get-password")
        password = result.results.get("password")
        karapace_endpoint = self.get_karapace_endpoint()
        base_url = f"http://{karapace_endpoint}"
        auth = ("operator", password)

        # Create the schema
        schema_data = {
            "schema": '{"type": "record", "name": "Obj", "fields":[{"name": "age", "type": "int"}]}'
        }

        response = requests.post(
            f"{base_url}/subjects/{schema_name}/versions",
            json=schema_data,
            headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            auth=auth,
        )
        response.raise_for_status()
        result = response.text
        assert '{"id":1}' in result

        # Listing it
        expected_schema = f'["{schema_name}"]'

        logger.info("Requesting schemas")
        response = requests.get(
            f"{base_url}/subjects",
            auth=auth,
        )
        response.raise_for_status()
        result = response.text
        assert expected_schema in result

        # Deleting the schema
        logger.info("Deleting schema")
        response = requests.delete(
            f"{base_url}/subjects/{schema_name}",
            auth=auth,
        )
        response.raise_for_status()

    def test_connect_endpoints(self):
        """Test Kafka Connect health."""
        connect_address = self.get_unit_ipv4_address(f"{CONNECT_APP_NAME}/0")
        status = check_socket(connect_address, CONNECT_API_PORT)

        # assert all endpoints are up
        assert status

    def test_create_mm2_connector(self):
        """Test creating a basic MM2 (MirrorMaker 2) connector."""
        connector_name = "mm2-test"
        connect_endpoint = self.get_connect_endpoint()
        connect_password = self._get_connect_admin_password()

        # TLS setup
        protocol = "https" if self.tls else "http"
        base_url = f"{protocol}://{connect_endpoint}"
        verify = CA_FILE if self.tls else False

        # Basic MM2 connector configuration
        mm2_config = {
            "name": connector_name,
            "config": {
                "connector.class": "org.apache.kafka.connect.mirror.MirrorSourceConnector",
                "source.cluster.alias": "source",
                "target.cluster.alias": "target",
                "source.cluster.bootstrap.servers": "localhost:9092",
                "target.cluster.bootstrap.servers": "localhost:9092",
                "topics": "test.*",
                "groups": "test-group",
                "replication.factor": 1,
                "checkpoints.topic.replication.factor": 1,
                "heartbeats.topic.replication.factor": 1,
                "offset-syncs.topic.replication.factor": 1,
                "sync.topic.acls.enabled": "false",
            },
        }

        # Create connector
        response = requests.post(
            f"{base_url}/connectors",
            json=mm2_config,
            headers={"Content-Type": "application/json"},
            auth=("admin", connect_password),
            verify=verify,
        )

        assert response.status_code in [200, 201, 400, 409]

        if response.status_code in [200, 201]:
            requests.delete(
                f"{base_url}/connectors/{connector_name}",
                auth=("admin", connect_password),
                verify=verify,
            )

    def test_ui_accessibility(self):
        """Test that Kafka UI is accessible."""
        secret_data = get_secret_by_label(
            self.model, f"cluster.{KAFKA_UI_APP_NAME}.app", owner=KAFKA_UI_APP_NAME
        )
        password = secret_data.get(KAFKA_UI_SECRET_KEY)

        if not password:
            raise Exception("Can't fetch the admin user's password.")

        # Verify that we're using TLS provider's cert in case TLS enabled.
        _verify = False
        if self.tls:
            _verify = CA_FILE

        unit_ip = self.get_unit_ipv4_address(f"{KAFKA_UI_APP_NAME}/0")
        url = f"{KAFKA_UI_PROTO}://{unit_ip}:{KAFKA_UI_PORT}"

        login_resp = requests.post(
            f"{url}/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"username": "admin", "password": password},
            verify=_verify,
        )
        assert login_resp.status_code == 200
        # Successful login would lead to a redirect
        assert len(login_resp.history) > 0

        cookies = login_resp.history[0].cookies
        clusters_resp = requests.get(
            f"{url}/api/clusters",
            headers={"Content-Type": "application/json"},
            cookies=cookies,
            verify=_verify,
        )

        clusters_json = clusters_resp.json()
        logger.info(f"{clusters_json=}")
        assert len(clusters_json) > 0
        assert clusters_json[0].get("status") == "online"

    def get_kafka_bootstrap_server(
        self, unit_name: str = f"{KAFKA_BROKER_APP_NAME}/0"
    ) -> str | None:
        """Get the Kafka bootstrap server address."""
        return f"{self.get_unit_ipv4_address(unit_name)}:{SECURITY_PROTOCOL_PORTS['SASL_SSL', 'SCRAM-SHA-512'].internal}"

    def get_karapace_endpoint(self, unit_name: str = f"{KARAPACE_APP_NAME}/0") -> str | None:
        """Get the Karapace endpoint address."""
        return f"{self.get_unit_ipv4_address(unit_name)}:{KARAPACE_PORT}"

    def get_connect_endpoint(self, unit_name: str = f"{CONNECT_APP_NAME}/0") -> str | None:
        """Get the Connect endpoint address."""
        return f"{self.get_unit_ipv4_address(unit_name)}:{CONNECT_API_PORT}"

    def get_unit_ipv4_address(self, unit_name: str) -> str | None:
        """A safer alternative for `juju.unit.get_public_address()` which is robust to network changes."""
        try:
            stdout = check_output(
                f"JUJU_MODEL={self.model} juju ssh {unit_name} hostname -i",
                stderr=PIPE,
                shell=True,
                universal_newlines=True,
            )
        except CalledProcessError:
            return None

        ipv4_matches = re.findall(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", stdout)

        if ipv4_matches:
            return ipv4_matches[0]

        return None

    def _get_connect_admin_password(self) -> str:
        """Get admin user's password of a unit by reading credentials file."""
        password_path = "/var/snap/charmed-kafka/current/etc/connect/connect.password"
        res = check_output(
            f"JUJU_MODEL={self.model} juju ssh {CONNECT_APP_NAME}/0 sudo -i 'sudo cat {password_path}'",
            shell=True,
            universal_newlines=True,
        )
        raw = res.strip().split("\n")

        if not raw:
            raise Exception("Unable to read the Connect credentials file.")

        for line in raw:
            if line.startswith("admin"):
                return line.split(":")[-1].strip()

        raise Exception("Admin user not defined in the Connect credentials file.")
