#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest
from literals import DATABASE_CHARM_NAME
from tests.integration.e2e.helpers import check_messages, fetch_action_get_credentials

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
async def test_test_app_actually_set_up(ops_test: OpsTest, deploy_test_app):
    producer = await deploy_test_app(role="producer", topic_name="topic_0")
    assert ops_test.model.applications[producer].status == "active"
    consumer = await deploy_test_app(role="consumer", topic_name="topic_0")
    assert ops_test.model.applications[consumer].status == "active"
    await asyncio.sleep(100)
    logger.info("Scale up producer")
    await ops_test.model.applications[producer].add_units(count=2)
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[producer].units) == 3)
    await ops_test.model.wait_for_idle(
        apps=[producer], status="active", timeout=1000, idle_period=40
    )
    await asyncio.sleep(100)
    logger.info("Scale up consumer")
    await ops_test.model.applications[consumer].add_units(count=2)
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[consumer].units) == 3)
    await ops_test.model.wait_for_idle(
        apps=[consumer], status="active", timeout=1000, idle_period=40
    )
    await asyncio.sleep(100)
    logger.info("Scale down consumer")
    await ops_test.model.applications[consumer].destroy_units(f"{consumer}/2")
    await ops_test.model.applications[consumer].destroy_units(f"{consumer}/1")
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[consumer].units) == 1)
    await ops_test.model.wait_for_idle(apps=[consumer], status="active", timeout=1000)
    logger.info(f"End scale down")
    await asyncio.sleep(100)


@pytest.mark.abort_on_fail
async def test_consumed_messages(ops_test: OpsTest, deploy_data_integrator):

    # get mongodb credentials
    mongo_integrator = await deploy_data_integrator({"database-name":"topic_0"})

    await ops_test.model.add_relation(mongo_integrator, DATABASE_CHARM_NAME)
    await ops_test.model.wait_for_idle(
        apps=[mongo_integrator, DATABASE_CHARM_NAME], idle_period=30, status="active", timeout=1800
    )

    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[mongo_integrator].units[0]
    )
    
    logger.info(f"credentials: {credentials}")

    uris = credentials[DATABASE_CHARM_NAME]["uris"]

    check_messages(uris, "topic_0")

