#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""The pytest fixtures to support cmd options for local running and CI/CD."""

import asyncio
import logging
import random
import string
from typing import Literal

import pytest
from literals import (
    CLIENT_CHARM_NAME,
    KAFKA_CHARM_NAME,
    TLS_APP_NAME,
    TLS_CHARM_NAME,
    TLS_REL_NAME,
    ZOOKEEPER_CHARM_NAME,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    """Defines pytest parsers."""
    parser.addoption("--tls", action="store_true", help="set tls for e2e tests")
    parser.addoption(
        "--kafka", action="store", help="name of pre-deployed kafka app", default=KAFKA_CHARM_NAME
    )
    parser.addoption(
        "--zookeeper",
        action="store",
        help="name of pre-deployed zookeeper app",
        default=ZOOKEEPER_CHARM_NAME,
    )
    parser.addoption(
        "--certificates",
        action="store",
        help="name of pre-deployed tls-certificates app",
        default=TLS_APP_NAME,
    )


def pytest_generate_tests(metafunc):
    """Processes pytest parsers."""
    tls = metafunc.config.option.tls
    if "tls" in metafunc.fixturenames:
        metafunc.parametrize("tls", [bool(tls)], scope="module")

    kafka = metafunc.config.option.kafka
    if "kafka" in metafunc.fixturenames:
        metafunc.parametrize("kafka", [kafka], scope="module")

    zookeeper = metafunc.config.option.zookeeper
    if "zookeeper" in metafunc.fixturenames:
        metafunc.parametrize("zookeeper", [zookeeper], scope="module")

    certificates = metafunc.config.option.certificates
    if "certificates" in metafunc.fixturenames:
        metafunc.parametrize("certificates", [certificates], scope="module")


### - FIXTURES - ###


@pytest.fixture(scope="module")
async def deploy_cluster(ops_test: OpsTest, tls):
    """Fixture for deploying Kafka+ZK clusters."""
    if not ops_test.model:  # avoids a multitude of linting errors
        raise RuntimeError("model not set")

    async def _deploy_non_tls_cluster():
        if not ops_test.model:  # avoids a multitude of linting errors
            raise RuntimeError("model not set")

        await asyncio.gather(
            ops_test.model.deploy(
                KAFKA_CHARM_NAME,
                application_name=KAFKA_CHARM_NAME,
                num_units=3,
                series="jammy",
                channel="edge",
            ),
            ops_test.model.deploy(
                ZOOKEEPER_CHARM_NAME,
                application_name=ZOOKEEPER_CHARM_NAME,
                num_units=3,
                series="jammy",
                channel="edge",
            ),
        )
        await ops_test.model.wait_for_idle(apps=[KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME])

        async with ops_test.fast_forward():
            await ops_test.model.add_relation(KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME)
            await ops_test.model.wait_for_idle(
                apps=[KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME],
                idle_period=10,
                status="active",
                timeout=300,
            )

    async def _deploy_tls_cluster():
        if not ops_test.model:  # avoids a multitude of linting errors
            raise RuntimeError("model not set")

        # start future for slow non-tls cluster deploy
        deploy_non_tls = asyncio.ensure_future(_deploy_non_tls_cluster())

        await ops_test.model.deploy(
            TLS_CHARM_NAME,
            application_name=TLS_APP_NAME,
            num_units=1,
            series="jammy",
            channel="beta",
            config={"generate-self-signed-certificates": "true", "ca-common-name": "Canonical"},
        )
        await ops_test.model.wait_for_idle(apps=[TLS_CHARM_NAME])

        # block until non-tls cluster completion
        await deploy_non_tls

        async with ops_test.fast_forward():
            await ops_test.model.add_relation(ZOOKEEPER_CHARM_NAME, TLS_CHARM_NAME)
            await ops_test.model.add_relation(f"{KAFKA_CHARM_NAME}:{TLS_REL_NAME}", TLS_CHARM_NAME)
            await ops_test.model.wait_for_idle(
                apps=[KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME],
                idle_period=30,
                status="active",
                timeout=1800,
            )

    if tls:  # grabbed from command-line args
        await _deploy_tls_cluster()
    else:
        await _deploy_non_tls_cluster()


@pytest.fixture(scope="function")
async def deploy_client(ops_test: OpsTest, kafka):
    """Factory fixture for deploying + tearing down client applications."""
    # tracks deployed app names for teardown later
    apps = []

    async def _deploy_client(role: Literal["producer", "consumer"]):
        """Deploys client with specified role and uuid."""
        if not ops_test.model:  # avoids a multitude of linting errors
            raise RuntimeError("model not set")

        # uuid to avoid name clashes for same applications
        key = "".join(random.choices(string.ascii_lowercase, k=4))
        generated_app_name = f"{role}-{key}"
        apps.append(generated_app_name)

        logger.info(f"{generated_app_name=} - {apps=}")
        await ops_test.model.deploy(
            CLIENT_CHARM_NAME,
            application_name=generated_app_name,
            num_units=1,
            series="jammy",
            channel="edge",
            config={"topic-name": "HOT-TOPIC", "extra-user-roles": role},
        )
        await ops_test.model.wait_for_idle(apps=[generated_app_name])

        await ops_test.model.add_relation(generated_app_name, kafka)
        await ops_test.model.wait_for_idle(
            apps=[generated_app_name, kafka], idle_period=30, status="active", timeout=1800
        )

        return generated_app_name

    logger.info(f"setting up client - current apps {apps}")
    yield _deploy_client

    logger.info(f"tearing down {apps}")
    for app in apps:
        logger.info(f"tearing down {app}")
        await ops_test.model.applications[app].remove()

    await ops_test.model.wait_for_idle(apps=[kafka], idle_period=30, status="active", timeout=1800)
