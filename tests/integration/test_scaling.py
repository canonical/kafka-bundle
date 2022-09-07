#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import time
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tests.integration.utils import get_active_brokers

from tests.integration.zookeeper_helpers import (
    check_key,
    get_password,
    ping_servers,
    restart_unit,
    write_key,
)

# from tests.integration.kafka_helpers import (
#     get_kafka_zk_relation_data,
# )

logger = logging.getLogger(__name__)


def is_k8s(bundle_path):
    try:
        bundle_data = yaml.safe_load(Path(bundle_path).read_text())
        if bundle_data["bundle"] == "kubernetes":
            return True
        else:
            return False
    except KeyError:
        return False


@pytest.mark.abort_on_fail
async def test_deploy_active(ops_test: OpsTest, bundle):
    bundle_data = yaml.safe_load(Path(bundle).read_text())

    applications = []

    for app in bundle_data["applications"]:
        applications.append(app)

    await ops_test.deploy_bundle(bundle=bundle, build=False)
    time.sleep(60)
    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications["zookeeper"].units) == 3
            and len(ops_test.model.applications["kafka"].units) == 3
        )
    )
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})
    await ops_test.model.wait_for_idle(apps=applications, status="active", timeout=1000)

    for app in applications:
        assert ops_test.model.applications[app].status == "active"

    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_zookeeper_simple_scale_up(ops_test: OpsTest, bundle):
    await ops_test.model.applications["zookeeper"].add_units(count=3)
    await ops_test.model.block_until(
        lambda: len(ops_test.model.applications["zookeeper"].units) == 6
    )
    await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)
    assert ping_servers(ops_test)


@pytest.mark.abort_on_fail
async def test_zookeeper_simple_scale_down(ops_test: OpsTest, bundle):
    if not is_k8s(bundle):
        await ops_test.model.applications["zookeeper"].destroy_units(
            f"{'zookeeper'}/5", f"{'zookeeper'}/4", f"{'zookeeper'}/3"
        )
    else:
        await ops_test.model.applications["zookeeper"].scale(scale_change=-3)
    await ops_test.model.block_until(
        lambda: len(ops_test.model.applications["zookeeper"].units) == 3
    )
    await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)
    assert ping_servers(ops_test)


@pytest.mark.abort_on_fail
async def test_zookeeper_scale_up_replication(ops_test: OpsTest, bundle):
    await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)
    assert ping_servers(ops_test)
    host = ops_test.model.applications["zookeeper"].units[0].public_address
    model_full_name = ops_test.model_full_name
    password = get_password(model_full_name or "")
    write_key(host=host, password=password)
    await ops_test.model.applications["zookeeper"].add_units(count=1)
    await ops_test.model.block_until(
        lambda: len(ops_test.model.applications["zookeeper"].units) == 4
    )
    await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)
    check_key(host=host, password=password)


@pytest.mark.abort_on_fail
async def test_zookeeper_kill_quorum_leader_remove(ops_test: OpsTest, bundle):
    """Gracefully removes ZK quorum leader using `juju remove`."""
    if not is_k8s(bundle):
        await ops_test.model.set_config({"update-status-hook-interval": "1m"})
        await ops_test.model.applications["zookeeper"].destroy_units(f"{'zookeeper'}/0")
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications["zookeeper"].units) == 3
        )
        await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)
        assert ping_servers(ops_test)
        await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_zookeeper_kill_juju_leader_remove(ops_test: OpsTest, bundle):
    """Gracefully removes Juju leader using `juju remove`."""
    if not is_k8s(bundle):
        await ops_test.model.set_config({"update-status-hook-interval": "1m"})
        leader = None
        for unit in ops_test.model.applications["zookeeper"].units:
            if await unit.is_leader_from_status():
                leader = unit.name
                break

        if leader:
            await ops_test.model.applications["zookeeper"].destroy_units(leader)
            await ops_test.model.block_until(
                lambda: len(ops_test.model.applications["zookeeper"].units) == 2
            )
            await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)
            assert ping_servers(ops_test)
        await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_zookeeper_kill_juju_leader_restart(ops_test: OpsTest, bundle):
    """Rudely removes Juju leader by restarting the LXD container."""
    if not is_k8s(bundle):
        await ops_test.model.set_config({"update-status-hook-interval": "1m"})
        leader = None
        for unit in ops_test.model.applications["zookeeper"].units:
            if await unit.is_leader_from_status():
                leader = unit.name
                break

        if leader:
            # adding another unit to ensure minimum units for quorum
            await ops_test.model.applications["zookeeper"].add_units(count=1)
            await ops_test.model.block_until(
                lambda: len(ops_test.model.applications["zookeeper"].units) == 3
            )
            await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)

            model_full_name = ops_test.model_full_name
            if model_full_name:
                restart_unit(model_full_name=model_full_name, unit=leader)
                time.sleep(10)
                assert ping_servers(ops_test)
            else:
                raise


@pytest.mark.abort_on_fail
async def test_zookeeper_same_model_application_deploys(ops_test: OpsTest, bundle):
    """Ensures that re-deployments of the charm starts on the same model."""
    await asyncio.gather(ops_test.model.applications["zookeeper"].remove())
    time.sleep(60)
    zoo = await ops_test.model.deploy("zookeeper", application_name="zookeeper", num_units=3)
    await zoo.add_relation("zookeeper", "kafka")
    await ops_test.model.block_until(
        lambda: len(ops_test.model.applications["zookeeper"].units) == 3
    )
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})
    await ops_test.model.wait_for_idle(apps=["zookeeper"], status="active", timeout=1000)

    assert ops_test.model.applications["zookeeper"].status == "active"

    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


# @pytest.mark.abort_on_fail
# async def test_kafka_simple_scale_up(ops_test: OpsTest, bundle):
#     await ops_test.model.applications["kafka"].add_units(count=2)
#     await ops_test.model.block_until(lambda: len(ops_test.model.applications["kafka"].units) == 3)
#     await ops_test.model.wait_for_idle(apps=["kafka"], status="active", timeout=1000)

#     kafka_zk_relation_data = get_kafka_zk_relation_data(
#         unit_name="kafka/2", model_full_name=ops_test.model_full_name
#     )
#     active_brokers = get_active_brokers(zookeeper_config=kafka_zk_relation_data)
#     chroot = kafka_zk_relation_data.get("chroot", "")
#     assert f"{chroot}/brokers/ids/0" in active_brokers
#     assert f"{chroot}/brokers/ids/1" in active_brokers
#     assert f"{chroot}/brokers/ids/2" in active_brokers


# @pytest.mark.abort_on_fail
# async def test_kafka_simple_scale_down(ops_test: OpsTest, bundle):
#     if not is_k8s(bundle):
#         await ops_test.model.applications["kafka"].destroy_units(f"{'kafka'}/1")
#         await ops_test.model.block_until(
#             lambda: len(ops_test.model.applications["kafka"].units) == 2
#         )
#         await ops_test.model.wait_for_idle(apps=["kafka"], status="active", timeout=1000)

#         time.sleep(30)

#         kafka_zk_relation_data = get_kafka_zk_relation_data(
#             unit_name="kafka/2", model_full_name=ops_test.model_full_name
#         )
#         active_brokers = get_active_brokers(zookeeper_config=kafka_zk_relation_data)
#         chroot = kafka_zk_relation_data.get("chroot", "")
#         assert f"{chroot}/brokers/ids/0" in active_brokers
#         assert f"{chroot}/brokers/ids/1" not in active_brokers
#         assert f"{chroot}/brokers/ids/2" in active_brokers
