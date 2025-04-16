#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
from tests.integration.e2e.literals import KAFKA_CHARM_NAME

logger = logging.getLogger(__name__)


def test_deploy(juju, deploy_cluster):
    juju.wait(lambda status: jubilant.all_active(status), timeout=1800)


def test_cluster_is_deployed_successfully(juju, kafka, zookeeper, tls, certificates):

    status = juju.status()
    assert status.apps[kafka].app_status.current == "active"
    assert status.apps[zookeeper].app_status.current == "active"

    if tls:
        assert status.apps[certificates].app_status.current == "active"


def test_clients_actually_set_up(juju, deploy_data_integrator):
    producer = deploy_data_integrator({"extra-user-roles": "producer", "topic-name": "test-topic"})
    consumer = deploy_data_integrator({"extra-user-roles": "producer", "topic-name": "test-topic"})

    juju.integrate(producer, KAFKA_CHARM_NAME)
    juju.wait(
        lambda status: jubilant.all_active(status, apps=[producer, KAFKA_CHARM_NAME]),
        timeout=1800,
        delay=10,
    )

    juju.integrate(consumer, KAFKA_CHARM_NAME)
    juju.wait(
        lambda status: jubilant.all_active(status, apps=[consumer, KAFKA_CHARM_NAME]),
        timeout=1800,
        delay=10,
    )

    status = juju.status()
    assert status.apps[consumer].app_status.current == "active"
    assert status.apps[producer].app_status.current == "active"


def test_clients_actually_tear_down_after_test_exit(juju):
    status = juju.status()
    assert "consumer" not in status.apps.keys()
    assert "producer" not in status.apps.keys()
