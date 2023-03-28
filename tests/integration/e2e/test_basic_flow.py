#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from literals import DATABASE_CHARM_NAME, KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME
from pytest_operator.plugin import OpsTest
from tests.integration.e2e.helpers import (
    check_produced_and_consumed_messages,
    fetch_action_get_credentials,
    fetch_action_start_process,
    get_action_parameters,
    get_random_topic,
)

logger = logging.getLogger(__name__)


TOPIC = get_random_topic()

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

    # deploy MongoDB

    await asyncio.gather(
        ops_test.model.deploy(
            DATABASE_CHARM_NAME,
            application_name=DATABASE_CHARM_NAME,
            num_units=1,
            series="jammy",
            channel="5/edge",
        ),
    )
    await ops_test.model.wait_for_idle(
        apps=[KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME, DATABASE_CHARM_NAME], status="active", timeout=1200, idle_period=30
    )


@pytest.mark.abort_on_fail
async def test_test_app_actually_set_up(ops_test: OpsTest, deploy_test_app, kafka, deploy_data_integrator, integrator):
    logger.info(f"Integrator: {integrator}")
    # deploy integrators and get credentials
    producer_parameters = None
    consumer_parameters = None
    if integrator:
        data_integrator_producer = await deploy_data_integrator({"topic-name": TOPIC, "extra-user-roles": "producer"})

        await ops_test.model.add_relation(data_integrator_producer, kafka)
        await ops_test.model.wait_for_idle(
        apps=[data_integrator_producer, kafka], idle_period=30, status="active", timeout=1800
        )


        producer_credentials = await fetch_action_get_credentials(ops_test.model.applications[data_integrator_producer].units[0])
        logger.info(f"Credentials from producer DI: {producer_credentials}")
        producer_parameters = get_action_parameters(producer_credentials, TOPIC)
        logger.info(f"Producer action parameters: {producer_parameters}")

        data_integrator_consumer = await deploy_data_integrator({"topic-name": TOPIC, "extra-user-roles": "consumer"})
        await ops_test.model.add_relation(data_integrator_consumer, kafka)
        await ops_test.model.wait_for_idle(
        apps=[data_integrator_consumer, kafka], idle_period=30, status="active", timeout=1800
        )
        consumer_credentials = await fetch_action_get_credentials(ops_test.model.applications[data_integrator_consumer].units[0])
        logger.info(f"Credentials form consumer DI: {consumer_credentials}")
        consumer_parameters = get_action_parameters(consumer_credentials, TOPIC)
        logger.info(f"Consumer action parameters: {consumer_parameters}")
    

    # deploy producer and consumer
    producer = await deploy_test_app(role="producer", topic_name=TOPIC)
    assert ops_test.model.applications[producer].status == "active"
    
    if integrator:
        assert producer_parameters
        pid = await fetch_action_start_process(ops_test.model.applications[producer].units[0], producer_parameters)
        logger.info(f"Producer process started with pid: {pid}")

    consumer = await deploy_test_app(role="consumer", topic_name=TOPIC)
    assert ops_test.model.applications[consumer].status == "active"

    if integrator:
        assert consumer_parameters
        pid = await fetch_action_start_process(ops_test.model.applications[consumer].units[0], consumer_parameters)
        logger.info(f"Consumer process started with pid: {pid}")
    
    
    await asyncio.sleep(100)

    # scale up producer
    logger.info("Scale up producer")
    await ops_test.model.applications[producer].add_units(count=2)
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[producer].units) == 3)
    await ops_test.model.wait_for_idle(
        apps=[producer], status="active", timeout=1000, idle_period=40
    )

    if integrator:
        assert producer_parameters
        pid_1 = await fetch_action_start_process(ops_test.model.applications[producer].units[1], producer_parameters)
        logger.info(f"Producer process started with pid: {pid_1}")
        pid_2 = await fetch_action_start_process(ops_test.model.applications[producer].units[2], producer_parameters)
        logger.info(f"Producer process started with pid: {pid_2}")

    await asyncio.sleep(100)

    # scale up consumer
    logger.info("Scale up consumer")
    await ops_test.model.applications[consumer].add_units(count=2)
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[consumer].units) == 3)
    await ops_test.model.wait_for_idle(
        apps=[consumer], status="active", timeout=1000, idle_period=40
    )

    if integrator:
        assert consumer_parameters
        pid_1 = await fetch_action_start_process(ops_test.model.applications[consumer].units[1], consumer_parameters)
        logger.info(f"Consumer process started with pid: {pid_1}")
        pid_2 = await fetch_action_start_process(ops_test.model.applications[consumer].units[2], consumer_parameters)
        logger.info(f"Consumer process started with pid: {pid_2}")

    await asyncio.sleep(100)

    logger.info("Scale down consumer")
    await ops_test.model.applications[consumer].destroy_units(f"{consumer}/2")
    await ops_test.model.applications[consumer].destroy_units(f"{consumer}/1")
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[consumer].units) == 1, timeout=1200)
    await ops_test.model.wait_for_idle(apps=[consumer], status="active", timeout=1000)

    logger.info("End scale down")

    await asyncio.sleep(100)

    # destroy producer and consumer during teardown.


    # scale up producer
    logger.info("Scale up producer")
    await ops_test.model.applications[producer].add_units(count=2)
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[producer].units) == 3)
    await ops_test.model.wait_for_idle(
        apps=[producer], status="active", timeout=1000, idle_period=40
    )

    await asyncio.sleep(100)

    # scale up consumer
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

    logger.info("End scale down")

    await asyncio.sleep(100)

    # destroy producer and consumer during teardown.


@pytest.mark.abort_on_fail
async def test_consumed_messages(ops_test: OpsTest, deploy_data_integrator):

    # get mongodb credentials
    mongo_integrator = await deploy_data_integrator({"database-name": TOPIC})

    await ops_test.model.add_relation(mongo_integrator, DATABASE_CHARM_NAME)
    await ops_test.model.wait_for_idle(
        apps=[mongo_integrator, DATABASE_CHARM_NAME], idle_period=30, status="active", timeout=1800
    )

    credentials = await fetch_action_get_credentials(
        ops_test.model.applications[mongo_integrator].units[0]
    )
    logger.info(f"Credentials: {credentials}")

    uris = credentials[DATABASE_CHARM_NAME]["uris"]

    check_produced_and_consumed_messages(uris, TOPIC)

    await ops_test.model.applications[DATABASE_CHARM_NAME].remove()
    await ops_test.model.wait_for_idle(
        apps=[mongo_integrator], idle_period=10, status="blocked", timeout=1800
    )
    logger.info(f"End of the test!")
