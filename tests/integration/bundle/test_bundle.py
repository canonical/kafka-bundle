#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tests.integration.bundle.kafka_helpers import (
    check_properties,
    check_user,
    get_zookeeper_connection,
    load_acls,
    ping_servers,
)
from tests.integration.bundle.literals import APP_CHARM_PATH, BUNDLE_PATH, KAFKA, ZOOKEEPER

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def usernames():
    return set()


@pytest.mark.abort_on_fail
async def test_deploy_bundle_active(ops_test: OpsTest):
    """Deploy the bundle."""
    bundle_data = yaml.safe_load(Path(BUNDLE_PATH).read_text())
    applications = []

    for app in bundle_data["applications"]:
        applications.append(app)

    retcode, stdout, stderr = await ops_test.run(
        *["juju", "deploy", "--trust", "-m", ops_test.model_full_name, f"./{BUNDLE_PATH}"]
    )
    assert retcode == 0, f"Deploy failed: {(stderr or stdout).strip()}"
    logger.info(stdout)
    await ops_test.model.wait_for_idle(timeout=1200, idle_period=30, status="active")
    for app in applications:
        assert ops_test.model.applications[app].status == "active"


@pytest.mark.abort_on_fail
async def test_active_zookeeper(ops_test: OpsTest):
    """Test the status the correct status of Zookeeper."""
    assert await ping_servers(ops_test, ZOOKEEPER)


@pytest.mark.abort_on_fail
async def test_deploy_app_charm_relate(ops_test: OpsTest):
    """Deploy dummy app and relate with Kafka and TLS operator."""
    bundle_data = yaml.safe_load(Path(BUNDLE_PATH).read_text())
    applications = []

    tls = False
    for app in bundle_data["applications"]:
        applications.append(app)
        if "tls-certificates-operator" in app:
            tls = True

    app_charm = await ops_test.build_charm(APP_CHARM_PATH)
    await ops_test.model.deploy(app_charm, application_name="app", num_units=1)
    if tls:
        await ops_test.model.add_relation("app", "tls-certificates-operator")
    await ops_test.model.wait_for_idle(
        apps=applications, timeout=1200, idle_period=30, status="active"
    )
    await ops_test.model.add_relation(KAFKA, "app")
    await ops_test.model.wait_for_idle(
        apps=applications + ["app"], status="active", timeout=1000, idle_period=30
    )

    for app in applications + ["app"]:
        assert ops_test.model.applications[app].status == "active"


@pytest.mark.abort_on_fail
async def test_apps_up_and_running(ops_test: OpsTest, usernames):
    """Test that all apps are up and running."""
    assert await ping_servers(ops_test, ZOOKEEPER)

    for unit in ops_test.model.applications[ZOOKEEPER].units:
        assert "sslQuorum=true" in check_properties(
            model_full_name=ops_test.model_full_name, unit=unit.name
        )

    # implicitly tests setting of kafka app data
    returned_usernames, zookeeper_uri = get_zookeeper_connection(
        unit_name=f"{KAFKA}/0", model_full_name=ops_test.model_full_name
    )
    usernames.update(returned_usernames)

    bootstrap_server = f"{ops_test.model.applications[KAFKA].units[0].public_address}:9093"

    for username in usernames:
        check_user(
            username=username,
            bootstrap_server=bootstrap_server,
            model_full_name=ops_test.model_full_name,
            unit_name=f"{KAFKA}/0",
        )

    for acl in load_acls(
        model_full_name=ops_test.model_full_name,
        bootstrap_server=bootstrap_server,
        unit_name=f"{KAFKA}/0",
    ):
        assert acl.username in usernames
        assert acl.operation in ["CREATE", "READ", "WRITE", "DESCRIBE"]
        assert acl.resource_type in ["GROUP", "TOPIC"]
        if acl.resource_type == "TOPIC":
            assert acl.resource_name == "test-topic"
    assert await ping_servers(ops_test, ZOOKEEPER)


@pytest.mark.abort_on_fail
async def test_run_action_produce_consume(ops_test: OpsTest):
    """Test production and consumption of messages."""
    action = await ops_test.model.units.get("app/0").run_action("produce-consume")
    ran_action = await action.wait()
    assert ran_action.results.get("passed", "") == "true"
