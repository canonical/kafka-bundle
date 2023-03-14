#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
async def test_deploy(ops_test: OpsTest, deploy_cluster):
    await asyncio.sleep(0)  # do nothing, await deploy_cluster


async def test_cluster_is_deployed_successfully(
    ops_test: OpsTest, kafka, zookeeper, tls, certificates
):
    assert ops_test.model.applications[kafka].status == "active"
    assert ops_test.model.applications[zookeeper].status == "active"

    if tls:
        assert ops_test.model.applications[certificates].status == "active"


async def test_clients_actually_set_up(ops_test: OpsTest, deploy_client):
    producer = await deploy_client(role="producer")
    consumer = await deploy_client(role="consumer")

    assert ops_test.model.applications[consumer].status == "active"
    assert ops_test.model.applications[producer].status == "active"


async def test_clients_actually_tear_down_after_test_exit(ops_test: OpsTest):
    assert "consumer" not in "".join(ops_test.model.applications.keys())
    assert "producer" not in "".join(ops_test.model.applications.keys())
