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
        apps=[KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME, DATABASE_CHARM_NAME], status="active"
    )


@pytest.mark.abort_on_fail
async def test_test_app_actually_set_up(ops_test: OpsTest, deploy_test_app, deploy_data_integrator, kafka, integrator):
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

        data_integrator_consumer = await deploy_data_integrator({"topic-name": TOPIC, "extra-user-roles": "consumer", "consumer-group-prefix":"cg"})
        await ops_test.model.add_relation(data_integrator_consumer, kafka)
        await ops_test.model.wait_for_idle(
        apps=[data_integrator_consumer, kafka], idle_period=30, status="active", timeout=1800
        )
        consumer_credentials = await fetch_action_get_credentials(ops_test.model.applications[data_integrator_consumer].units[0])
        logger.info(f"Credentials form consumer DI: {consumer_credentials}")
        consumer_parameters = get_action_parameters(consumer_credentials, TOPIC)
        logger.info(f"Consumer action parameters: {consumer_parameters}")

    producer_1 = await deploy_test_app(role="producer", topic_name=TOPIC, num_messages=2000)
    assert ops_test.model.applications[producer_1].status == "active"
    
    if integrator:
        assert producer_parameters
        pid = await fetch_action_start_process(ops_test.model.applications[producer_1].units[0], producer_parameters)
        logger.info(f"Producer process started with pid: {pid}")


    consumer_1 = await deploy_test_app(
        role="consumer", topic_name=TOPIC, consumer_group_prefix="cg"
    )
    assert ops_test.model.applications[consumer_1].status == "active"
    if integrator:
        assert consumer_parameters
        pid = await fetch_action_start_process(ops_test.model.applications[consumer_1].units[0], consumer_parameters)
        logger.info(f"Consumer process started with pid: {pid}")

    await asyncio.sleep(100)

    # deploy second consumer

    consumer_2 = await deploy_test_app(
        role="consumer", topic_name=TOPIC, consumer_group_prefix="cg"
    )
    assert ops_test.model.applications[consumer_2].status == "active"
    if integrator:
        assert consumer_parameters
        pid = await fetch_action_start_process(ops_test.model.applications[consumer_2].units[0], consumer_parameters)
        logger.info(f"Consumer process started with pid: {pid}")

    await asyncio.sleep(100)

    # remove first consumer

    await ops_test.model.applications[consumer_1].remove()
    await ops_test.model.wait_for_idle(
        apps=[KAFKA_CHARM_NAME], idle_period=10, status="active", timeout=1800
    )
    await asyncio.sleep(100)

    # deploy new producer

    producer_2 = await deploy_test_app(role="producer", topic_name=TOPIC)
    assert ops_test.model.applications[producer_2].status == "active"
    if integrator:
        assert producer_parameters
        pid = await fetch_action_start_process(ops_test.model.applications[producer_2].units[0], producer_parameters)
        logger.info(f"Producer process started with pid: {pid}")

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
