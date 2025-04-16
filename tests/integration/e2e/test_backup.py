#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import socket

import boto3
import jubilant
import pytest
import pytest_microceph
from tests.integration.e2e.helpers import (
    create_topic,
    get_random_topic,
    read_topic_config,
    write_topic_message_size_config,
)
from tests.integration.e2e.literals import ZOOKEEPER_CHARM_NAME

logger = logging.getLogger(__name__)

TOPIC = get_random_topic()
S3_INTEGRATOR = "s3-integrator"
S3_CHANNEL = "latest/stable"

NON_DEFAULT_TOPIC_SIZE = 123_123
UPDATED_TOPIC_SIZE = 456_456


@pytest.fixture(scope="session")
def cloud_credentials(microceph: pytest_microceph.ConnectionInformation) -> dict[str, str]:
    """Read cloud credentials."""
    return {
        "access-key": microceph.access_key_id,
        "secret-key": microceph.secret_access_key,
    }


@pytest.fixture(scope="session")
def cloud_configs(microceph: pytest_microceph.ConnectionInformation):
    host_ip = socket.gethostbyname(socket.gethostname())
    return {
        "endpoint": f"http://{host_ip}",
        "bucket": microceph.bucket,
        "path": "mysql",
        "region": "",
    }


@pytest.fixture(scope="function")
def s3_bucket(cloud_credentials, cloud_configs):

    session = boto3.Session(
        aws_access_key_id=cloud_credentials["access-key"],
        aws_secret_access_key=cloud_credentials["secret-key"],
        region_name=cloud_configs["region"] if cloud_configs["region"] else None,
    )
    s3 = session.resource("s3", endpoint_url=cloud_configs["endpoint"])
    bucket = s3.Bucket(cloud_configs["bucket"])
    yield bucket


def test_deploy(juju, deploy_cluster):
    juju.wait(lambda status: jubilant.all_active(status), timeout=1800)


def test_set_up_deployment(
    juju,
    kafka,
    zookeeper,
    cloud_configs,
    cloud_credentials,
    s3_bucket,
):
    status = juju.status()
    assert status.apps[kafka].app_status.current == "active"
    assert status.apps[zookeeper].app_status.current == "active"

    juju.deploy(S3_INTEGRATOR, channel=S3_CHANNEL)
    juju.wait(lambda status: status.apps[S3_INTEGRATOR].is_blocked, timeout=1000, delay=5)

    logger.info("Syncing credentials")
    juju.config(S3_INTEGRATOR, cloud_configs)

    leader_unit = list(juju.status().apps[S3_INTEGRATOR].units)[0]
    juju.run(leader_unit, "sync-s3-credentials", params=cloud_credentials)

    juju.integrate(zookeeper, S3_INTEGRATOR)
    juju.wait(
        lambda status: jubilant.all_active(status, apps=[zookeeper, S3_INTEGRATOR]), timeout=1000
    )

    # bucket exists
    assert s3_bucket.meta.client.head_bucket(Bucket=s3_bucket.name)


def test_point_in_time_recovery(juju, s3_bucket, kafka, zookeeper):

    logger.info("Creating topic")

    create_topic(model_full_name=juju.model, app_name=kafka, topic=TOPIC)
    write_topic_message_size_config(
        model_full_name=juju.model,
        app_name=kafka,
        topic=TOPIC,
        size=NON_DEFAULT_TOPIC_SIZE,
    )
    assert f"max.message.bytes={NON_DEFAULT_TOPIC_SIZE}" in read_topic_config(
        model_full_name=juju.model, app_name=kafka, topic=TOPIC
    )

    logger.info("Creating initial backup")

    for unit_name, unit_status in juju.status().apps[zookeeper].units.items():
        if unit_status.leader:
            leader_unit = unit_name

    juju.run(leader_unit, "create-backup")
    list_action = juju.run(leader_unit, "list-backups")

    backups = json.loads(list_action.results.get("backups", "[]"))
    assert len(backups) == 1

    logger.info("Restoring backup")

    write_topic_message_size_config(
        model_full_name=juju.model,
        app_name=kafka,
        topic=TOPIC,
        size=UPDATED_TOPIC_SIZE,
    )

    assert f"max.message.bytes={UPDATED_TOPIC_SIZE}" in read_topic_config(
        model_full_name=juju.model, app_name=kafka, topic=TOPIC
    )

    backup_to_restore = backups[0]["id"]
    list_action = juju.run(leader_unit, "restore", params={"backup-id": backup_to_restore})

    juju.wait(
        lambda status: jubilant.all_active(status, apps=[zookeeper, kafka]), timeout=1800, delay=10
    )
    assert f"max.message.bytes={NON_DEFAULT_TOPIC_SIZE}" in read_topic_config(
        model_full_name=juju.model, app_name=kafka, topic=TOPIC
    )

    status = juju.status()
    assert status.apps[kafka].app_status.current == "active"
    assert status.apps[zookeeper].app_status.current == "active"


def test_new_cluster_migration(juju, s3_bucket, kafka, zookeeper):

    status = juju.status()
    zookeeper_status = status.apps[zookeeper]

    logger.info(f"status: {zookeeper_status}")
    logger.info(f"charm url: {zookeeper_status.charm}")

    data = {
        "channel": zookeeper_status.charm_channel,
        "revision": zookeeper_status.charm_rev,
    }

    logger.info(f"Fetched current deployment revision: {data}")
    logger.info("Removing and redeploying apps")

    juju.remove_application(zookeeper)

    juju.deploy(ZOOKEEPER_CHARM_NAME, app="new-zk", num_units=3, **data)
    juju.wait(
        lambda status: jubilant.all_active(status, apps=[kafka, "new-zk"]), timeout=3600, delay=10
    )

    juju.integrate("new-zk", S3_INTEGRATOR)
    juju.wait(
        lambda status: jubilant.all_active(status, apps=["new-zk", S3_INTEGRATOR]),
        timeout=1000,
        delay=10,
    )

    logger.info("Restoring backup")

    for unit_name, unit_status in juju.status().apps["new-zk"].units.items():
        if unit_status.leader:
            leader_unit = unit_name

    list_action = juju.run(leader_unit, "list-backups")
    backups = json.loads(list_action.results.get("backups", "[]"))
    assert len(backups) == 1

    backup_to_restore = backups[0]["id"]
    list_action = juju.run(leader_unit, "restore", params={"backup-id": backup_to_restore})
    juju.wait(lambda status: status.apps["new-zk"].is_active, timeout=1000, delay=10)

    juju.integrate(kafka, "new-zk")
    juju.wait(
        lambda status: jubilant.all_active(status, apps=[kafka, "new-zk"]), timeout=1200, delay=10
    )

    assert f"max.message.bytes={NON_DEFAULT_TOPIC_SIZE}" in read_topic_config(
        model_full_name=juju.model, app_name=kafka, topic=TOPIC
    )
