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
    fetch_action_stop_process,
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
async def test_test_app_actually_set_up(
    ops_test: OpsTest, deploy_test_app, deploy_data_integrator, kafka, integrator
):
    # producer credentials
    producer_parameters_1 = None
    producer_parameters_2 = None
    # consumer credentials
    consumer_parameters_1 = None
    consumer_parameters_2 = None

    if integrator:
        # get credentials for producers and consumers
        data_integrator_producer_1 = await deploy_data_integrator(
            {"topic-name": TOPIC, "extra-user-roles": "producer"}
        )
        await ops_test.model.add_relation(data_integrator_producer_1, kafka)
        await ops_test.model.wait_for_idle(
            apps=[data_integrator_producer_1, kafka], idle_period=30, status="active", timeout=1800
        )
        producer_credentials_1 = await fetch_action_get_credentials(
            ops_test.model.applications[data_integrator_producer_1].units[0]
        )
        producer_parameters_1 = get_action_parameters(producer_credentials_1, TOPIC)
        data_integrator_producer_2 = await deploy_data_integrator(
            {"topic-name": TOPIC, "extra-user-roles": "producer"}
        )
        await ops_test.model.add_relation(data_integrator_producer_2, kafka)
        await ops_test.model.wait_for_idle(
            apps=[data_integrator_producer_2, kafka], idle_period=30, status="active", timeout=1800
        )
        producer_credentials_2 = await fetch_action_get_credentials(
            ops_test.model.applications[data_integrator_producer_2].units[0]
        )
        producer_parameters_2 = get_action_parameters(producer_credentials_2, TOPIC)

        assert producer_parameters_2 != producer_parameters_1

        data_integrator_consumer_1 = await deploy_data_integrator(
            {"topic-name": TOPIC, "extra-user-roles": "consumer", "consumer-group-prefix": "cg"}
        )
        await ops_test.model.add_relation(data_integrator_consumer_1, kafka)
        await ops_test.model.wait_for_idle(
            apps=[data_integrator_consumer_1, kafka], idle_period=30, status="active", timeout=1800
        )
        consumer_credentials_1 = await fetch_action_get_credentials(
            ops_test.model.applications[data_integrator_consumer_1].units[0]
        )
        consumer_parameters_1 = get_action_parameters(consumer_credentials_1, TOPIC)
        data_integrator_consumer_2 = await deploy_data_integrator(
            {"topic-name": TOPIC, "extra-user-roles": "consumer", "consumer-group-prefix": "cg"}
        )
        await ops_test.model.add_relation(data_integrator_consumer_2, kafka)
        await ops_test.model.wait_for_idle(
            apps=[data_integrator_consumer_2, kafka], idle_period=30, status="active", timeout=1800
        )
        consumer_credentials_2 = await fetch_action_get_credentials(
            ops_test.model.applications[data_integrator_consumer_2].units[0]
        )
        consumer_parameters_2 = get_action_parameters(consumer_credentials_2, TOPIC)

        assert consumer_parameters_2 != consumer_parameters_1

    producer_1 = await deploy_test_app(role="producer", topic_name=TOPIC, num_messages=2500)
    assert ops_test.model.applications[producer_1].status == "active"

    if integrator:
        # start producer
        assert producer_parameters_1
        pid = await fetch_action_start_process(
            ops_test.model.applications[producer_1].units[0], producer_parameters_1
        )
        logger.info(f"Producer process started with pid: {pid}")

    consumer_1 = await deploy_test_app(
        role="consumer", topic_name=TOPIC, consumer_group_prefix="cg"
    )
    assert ops_test.model.applications[consumer_1].status == "active"

    if integrator:
        # start consumer
        assert consumer_parameters_1
        pid = await fetch_action_start_process(
            ops_test.model.applications[consumer_1].units[0], consumer_parameters_1
        )
        logger.info(f"Consumer process started with pid: {pid}")

    await asyncio.sleep(100)

    # deploy second consumer

    consumer_2 = await deploy_test_app(
        role="consumer", topic_name=TOPIC, consumer_group_prefix="cg"
    )
    assert ops_test.model.applications[consumer_2].status == "active"
    if integrator:
        assert consumer_parameters_2
        # start second consumer
        pid = await fetch_action_start_process(
            ops_test.model.applications[consumer_2].units[0], consumer_parameters_2
        )
        logger.info(f"Consumer process started with pid: {pid}")

    await asyncio.sleep(100)

    # remove first consumer
    pid = await fetch_action_stop_process(ops_test.model.applications[consumer_1].units[0])
    logger.info(f"Consumer 1 process stopped with pid: {pid}")

    await ops_test.model.wait_for_idle(
        apps=[KAFKA_CHARM_NAME], idle_period=10, status="active", timeout=1800
    )
    await asyncio.sleep(100)

    # deploy new producer

    producer_2 = await deploy_test_app(role="producer", topic_name=TOPIC, num_messages=2000)
    assert ops_test.model.applications[producer_2].status == "active"
    if integrator:
        assert producer_parameters_2
        # start second producer
        pid = await fetch_action_start_process(
            ops_test.model.applications[producer_2].units[0], producer_parameters_2
        )
        logger.info(f"Producer process started with pid: {pid}")

    await asyncio.sleep(100)

    # destroy producer and consumer during teardown.

    if integrator:
        # stop process
        pid = await fetch_action_stop_process(ops_test.model.applications[producer_2].units[0])
        logger.info(f"Producer process stopped with pid: {pid}")
        pid = await fetch_action_stop_process(ops_test.model.applications[producer_1].units[0])
        logger.info(f"Producer process stopped with pid: {pid}")

        await asyncio.sleep(60)

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
