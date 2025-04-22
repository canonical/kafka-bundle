#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""The pytest fixtures to support cmd options for local running and CI/CD."""

import logging
import random
import string
from typing import Dict, Generator, Literal, Optional, cast

import jubilant
import pytest
from literals import (
    BUNDLE_BUILD,
    DATABASE_CHARM_NAME,
    INTEGRATOR_CHARM_NAME,
    KAFKA_CHARM_NAME,
    KAFKA_TEST_APP_CHARM_NAME,
    TLS_CHARM_NAME,
    ZOOKEEPER_CHARM_NAME,
)

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
        default=TLS_CHARM_NAME,
    )

    parser.addoption(
        "--integrator",
        action="store_true",
        help="set usage of credentials provided by the data-integrator.",
    )

    parser.addoption(
        "--database",
        action="store",
        help="name of pre-deployed mongoDB instance.",
        default=DATABASE_CHARM_NAME,
    )

    parser.addoption(
        "--bundle-file",
        action="store",
        help="name of the bundle zip when provided.",
        default=BUNDLE_BUILD,
    )

    parser.addoption(
        "--model",
        action="store",
        help="Juju model to use; if not provided, a new model "
        "will be created for each test which requires one",
        default=None,
    )

    parser.addoption(
        "--keep-models",
        action="store_true",
        default=False,
        help="keep temporarily-created models",
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

    integrator = metafunc.config.option.integrator
    if "integrator" in metafunc.fixturenames:
        metafunc.parametrize("integrator", [bool(integrator)], scope="module")

    database = metafunc.config.option.database
    if "database" in metafunc.fixturenames:
        metafunc.parametrize("database", [database], scope="module")

    bundle_file = metafunc.config.option.bundle_file
    if "bundle_file" in metafunc.fixturenames:
        metafunc.parametrize("bundle_file", [bundle_file], scope="module")


### - FIXTURES - ###


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Pytest fixture that wraps :meth:`jubilant.with_model`.

    This adds command line parameter ``--keep-models`` (see help for details).
    """
    model = request.config.getoption("--model")
    keep_models = cast(bool, request.config.getoption("--keep-models"))

    if model is None:
        with jubilant.temp_model(keep=keep_models) as juju:
            yield juju
            log = juju.debug_log(limit=1000)
    else:
        juju = jubilant.Juju(model=model)
        yield juju
        log = juju.debug_log(limit=1000)

    if request.session.testsfailed:
        print(log, end="")


@pytest.fixture(scope="module")
def deploy_cluster(juju, bundle_file):
    """Fixture for deploying Kafka+ZK clusters."""
    if not juju.model:  # avoids a multitude of linting errors
        raise RuntimeError("model not set")

    logger.info(f"Deploying Bundle with file {bundle_file}")
    juju.cli(*["deploy", "--trust", "-m", juju.model, f"./{bundle_file}"], include_model=False)


@pytest.fixture(scope="module")
def deploy_data_integrator(juju, kafka):
    """Factory fixture for deploying + tearing down client applications."""
    # tracks deployed app names for teardown later
    apps = []

    def _deploy_data_integrator(config: Dict[str, str]):
        """Deploys client with specified role and uuid."""
        if not juju.model:  # avoids a multitude of linting errors
            raise RuntimeError("model not set")

        # uuid to avoid name clashes for same applications
        key = "".join(random.choices(string.ascii_lowercase, k=4))
        generated_app_name = f"data-integrator-{key}"
        apps.append(generated_app_name)

        logger.info(f"{generated_app_name=} - {apps=}")
        juju.deploy(
            INTEGRATOR_CHARM_NAME,
            app=generated_app_name,
            num_units=1,
            channel="edge",
            config=config,
        )
        juju.wait(lambda status: status.apps[generated_app_name].is_blocked, timeout=3600)

        return generated_app_name

    logger.info(f"setting up data_integrator - current apps {apps}")
    yield _deploy_data_integrator

    logger.info(f"tearing down {apps}")
    for app in apps:
        logger.info(f"tearing down {app}")
        juju.remove_application(app)

    juju.wait(lambda status: status.apps[kafka].is_active, timeout=1800, delay=10)


@pytest.fixture(scope="function")
def deploy_test_app(juju: jubilant.Juju, kafka, certificates, database, tls):
    """Factory fixture for deploying + tearing down client applications."""
    # tracks deployed app names for teardown later
    apps = []

    def _deploy_test_app(
        role: Literal["producer", "consumer"],
        topic_name: str = "test-topic",
        consumer_group_prefix: Optional[str] = None,
        num_messages: int = 1500,
    ):
        """Deploys client with specified role and uuid."""
        if not juju.model:  # avoids a multitude of linting errors
            raise RuntimeError("model not set")

        # uuid to avoid name clashes for same applications
        key = "".join(random.choices(string.ascii_lowercase, k=4))
        generated_app_name = f"{role}-{key}"
        apps.append(generated_app_name)

        logger.info(f"{generated_app_name=} - {apps=}")

        config = {"role": role, "topic_name": topic_name, "num_messages": num_messages}

        if consumer_group_prefix:
            config["consumer_group_prefix"] = consumer_group_prefix

        # todo substitute with the published charm
        juju.deploy(
            KAFKA_TEST_APP_CHARM_NAME,
            app=generated_app_name,
            num_units=1,
            channel="edge",
            config=config,
        )
        juju.wait(lambda status: status.apps[generated_app_name].is_active, timeout=3600, delay=10)

        # Relate with TLS operator
        if tls:
            juju.integrate(generated_app_name, certificates)
            juju.wait(
                lambda status: jubilant.all_active(
                    status, apps=[generated_app_name, certificates]
                ),
                timeout=1800,
                delay=10,
            )

        # Relate with MongoDB
        juju.integrate(generated_app_name, database)
        juju.wait(
            lambda status: jubilant.all_active(status, apps=[generated_app_name, database]),
            timeout=1800,
            delay=10,
        )

        return generated_app_name

    logger.info(f"setting up test_app - current apps {apps}")

    yield _deploy_test_app

    logger.info(f"tearing down {apps}")
    # stop producers before consumers
    for app in sorted(apps, reverse=True):
        logger.info(f"tearing down {app}")
        status = juju.status()
        # check if application is in the
        if app in status.apps.keys():
            juju.remove_application(app)
            juju.wait(lambda status: status.apps[kafka].is_active, timeout=1800, delay=5)
        else:
            logger.info(f"App: {app} already removed!")

    juju.wait(lambda status: status.apps[kafka].is_active, timeout=1800, delay=10)


def pytest_configure():
    """Pytest configuration parameters."""
    pytest.remove_database = False
