#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest
from tests.integration.e2e.literals import KAFKA_CHARM_NAME

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest, deploy_cluster):
    await asyncio.sleep(0)  # do nothing, await deploy_cluster


@pytest.mark.abort_on_fail
async def test_cluster_is_deployed_successfully(
    ops_test: OpsTest, kafka, zookeeper, tls, certificates
):
    assert ops_test.model.applications[kafka].status == "active"
    assert ops_test.model.applications[zookeeper].status == "active"

    if tls:
        assert ops_test.model.applications[certificates].status == "active"


@pytest.mark.abort_on_fail
async def test_clients_actually_set_up(ops_test: OpsTest, deploy_data_integrator):
    producer = await deploy_data_integrator(
        {"extra-user-roles": "producer", "topic-name": "test-topic"}
    )
    consumer = await deploy_data_integrator(
        {"extra-user-roles": "producer", "topic-name": "test-topic"}
    )

    await ops_test.model.add_relation(producer, KAFKA_CHARM_NAME)
    await ops_test.model.wait_for_idle(
        apps=[producer, KAFKA_CHARM_NAME], idle_period=30, status="active", timeout=1800
    )

    await ops_test.model.add_relation(consumer, KAFKA_CHARM_NAME)
    await ops_test.model.wait_for_idle(
        apps=[consumer, KAFKA_CHARM_NAME], idle_period=30, status="active", timeout=1800
    )

    assert ops_test.model.applications[consumer].status == "active"
    assert ops_test.model.applications[producer].status == "active"


@pytest.mark.abort_on_fail
async def test_clients_actually_tear_down_after_test_exit(ops_test: OpsTest):
    assert "consumer" not in "".join(ops_test.model.applications.keys())
    assert "producer" not in "".join(ops_test.model.applications.keys())
