#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import time

import jubilant
import pytest
from literals import DATABASE_CHARM_NAME
from tests.integration.e2e.helpers import (
    check_produced_and_consumed_messages,
    fetch_action_get_credentials,
    fetch_action_start_process,
    get_action_parameters,
    get_random_topic,
)

logger = logging.getLogger(__name__)


TOPIC = get_random_topic()


def test_deploy(juju, deploy_cluster):
    juju.wait(lambda status: jubilant.all_active(status), timeout=1800)


def test_cluster_is_deployed_successfully(juju, kafka, zookeeper, tls, certificates, database):
    status = juju.status()
    assert status.apps[kafka].app_status.current == "active"
    assert status.apps[zookeeper].app_status.current == "active"

    if tls:
        assert status.apps[certificates].app_status.current == "active"

    # deploy MongoDB if it's not already deployed
    if database not in status.apps.keys():
        juju.deploy(
            DATABASE_CHARM_NAME,
            app=database,
            num_units=1,
            channel="5/edge",
        )
        juju.wait(
            lambda status: jubilant.all_active(status, kafka, zookeeper, database),
            timeout=1200,
            delay=10,
        )
        # teardown database at the end of the test
        pytest.remove_database = True


def test_test_app_actually_set_up(
    juju, deploy_test_app, kafka, deploy_data_integrator, integrator
):
    # consumer and producer params when deploying with data-integrator
    producer_parameters = None
    consumer_parameters = None
    if integrator:
        # deploy integrators and get credentials
        data_integrator_producer = deploy_data_integrator(
            {"topic-name": TOPIC, "extra-user-roles": "producer"}
        )

        juju.integrate(data_integrator_producer, kafka)
        juju.wait(
            lambda status: jubilant.all_active(status, data_integrator_producer, kafka),
            timeout=1800,
            delay=10,
        )
        producer_credentials = fetch_action_get_credentials(juju, data_integrator_producer)
        producer_parameters = get_action_parameters(producer_credentials, TOPIC)

        data_integrator_consumer = deploy_data_integrator(
            {"topic-name": TOPIC, "extra-user-roles": "consumer"}
        )
        juju.integrate(data_integrator_consumer, kafka)
        juju.wait(
            lambda status: jubilant.all_active(status, data_integrator_consumer, kafka),
            timeout=1800,
            delay=10,
        )
        consumer_credentials = fetch_action_get_credentials(juju, data_integrator_consumer)
        consumer_parameters = get_action_parameters(consumer_credentials, TOPIC)

        assert producer_parameters != consumer_parameters

    # deploy producer and consumer
    producer = deploy_test_app(role="producer", topic_name=TOPIC)
    assert juju.status().apps[producer].app_status.current == "active"

    if integrator:
        # start producer with action
        assert producer_parameters
        pid = fetch_action_start_process(juju, producer, producer_parameters)
        logger.info(f"Producer process started with pid: {pid}")
    else:
        # Relate with Kafka and automatically start producer
        juju.integrate(producer, kafka)
        juju.wait(
            lambda status: jubilant.all_active(status, producer, kafka),
            timeout=1800,
            delay=10,
        )
        logger.info(f"Producer {producer} related to Kafka")

    consumer = deploy_test_app(role="consumer", topic_name=TOPIC)
    assert juju.status().apps[consumer].app_status.current == "active"

    if integrator:
        # start consumer with action
        assert consumer_parameters
        pid = fetch_action_start_process(juju, consumer, consumer_parameters)
        logger.info(f"Consumer process started with pid: {pid}")
    else:
        # Relate with Kafka and automatically start consumer
        juju.integrate(consumer, kafka)
        juju.wait(
            lambda status: jubilant.all_active(status, consumer, kafka),
            timeout=1800,
            delay=10,
        )
        logger.info(f"Consumer {consumer} related to Kafka")

    time.sleep(100)

    # scale up producer
    logger.info("Scale up producer")
    juju.add_unit(producer, num_units=2)
    juju.wait(
        lambda status: len(status.apps[producer].units) == 3 and status.apps[producer].is_active,
        timeout=1200,
        delay=15,
    )

    if integrator:
        # start producer process on new units
        assert producer_parameters
        pid_1 = fetch_action_start_process(juju, producer, producer_parameters, unit_num=1)
        logger.info(f"Producer process started with pid: {pid_1}")
        pid_2 = fetch_action_start_process(juju, producer, producer_parameters, unit_num=2)
        logger.info(f"Producer process started with pid: {pid_2}")

    time.sleep(100)

    logger.info("Scale up consumer")
    juju.add_unit(consumer, num_units=2)
    juju.wait(
        lambda status: len(status.apps[consumer].units) == 3 and status.apps[consumer].is_active,
        timeout=1200,
        delay=15,
    )

    if integrator:
        # start consumer process on new units
        assert consumer_parameters
        pid_1 = fetch_action_start_process(juju, consumer, consumer_parameters, unit_num=1)
        logger.info(f"Consumer process started with pid: {pid_1}")
        pid_1 = fetch_action_start_process(juju, consumer, consumer_parameters, unit_num=2)
        logger.info(f"Consumer process started with pid: {pid_2}")

    time.sleep(100)

    logger.info("Scale down consumer")
    juju.remove_unit(f"{consumer}/1", f"{consumer}/2", force=True)
    juju.wait(
        lambda status: len(status.apps[consumer].units) == 1 and status.apps[consumer].is_active,
        timeout=1200,
        delay=15,
    )

    logger.info("End scale down")

    time.sleep(100)

    # destroy producer and consumer during teardown.


def test_consumed_messages(juju, deploy_data_integrator, database):

    # get mongodb credentials
    mongo_integrator = deploy_data_integrator({"database-name": TOPIC})

    juju.integrate(mongo_integrator, database)
    juju.wait(
        lambda status: jubilant.all_active(status, mongo_integrator, database),
        timeout=1800,
        delay=10,
    )

    credentials = fetch_action_get_credentials(juju, mongo_integrator)
    logger.info(f"Credentials: {credentials}")

    uris = credentials[DATABASE_CHARM_NAME]["uris"]

    check_produced_and_consumed_messages(uris, TOPIC)

    if pytest.remove_database:
        juju.remove_application(database)
        juju.wait(lambda status: status.apps[mongo_integrator].is_blocked, timeout=1800, delay=5)

    logger.info("End of the test!")
