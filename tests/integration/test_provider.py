#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import time
import yaml

import pytest
from pytest_operator.plugin import OpsTest
from pathlib import Path

from tests.integration.kafka_helpers import (
    check_user,
    get_zookeeper_connection,
    load_acls,
)

logger = logging.getLogger(__name__)


def units_deployed(model, bundle_data):
    for app_name, app in model.applications.items():
        try:
            if len(app.units) != bundle_data["applications"][app_name]["num_units"]:
                return False
        except KeyError:
            print(f"Skipping {app_name}. Not found in bundle...")
    return True


@pytest.fixture(scope="module")
def usernames():
    return set()


@pytest.mark.abort_on_fail
async def test_deploy_bundle_active(ops_test: OpsTest, usernames, bundle):
    bundle_data = yaml.safe_load(Path(bundle).read_text())
    applications = []

    for app in bundle_data["applications"]:
        applications.append(app)

    charm = await ops_test.deploy_bundle(bundle=bundle, build=False)
    time.sleep(20)
    await ops_test.model.block_until(lambda: (units_deployed(ops_test.model, bundle_data)))
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})
    await ops_test.model.wait_for_idle(apps=applications, status="active", timeout=1000)

    for app in applications:
        assert ops_test.model.applications[app].status == "active"

    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_deploy_app_charm_relate(ops_test: OpsTest, usernames, bundle):
    bundle_data = yaml.safe_load(Path(bundle).read_text())
    applications = []

    for app in bundle_data["applications"]:
        applications.append(app)

    app_charm = await ops_test.build_charm("tests/integration/app-charm")
    await ops_test.model.deploy(app_charm, application_name="app", num_units=1)
    await ops_test.model.add_relation("kafka", "app")
    time.sleep(20)
    await ops_test.model.block_until(lambda: (units_deployed(ops_test.model, bundle_data)))
    await ops_test.model.wait_for_idle(apps=applications + ["app"], status="active", timeout=1000)

    for app in applications + ["app"]:
        assert ops_test.model.applications[app].status == "active"

    # implicitly tests setting of kafka app data
    returned_usernames, zookeeper_uri = get_zookeeper_connection(
        unit_name="kafka/0", model_full_name=ops_test.model_full_name
    )
    usernames.update(returned_usernames)

    for username in usernames:
        check_user(
            username=username,
            zookeeper_uri=zookeeper_uri,
            model_full_name=ops_test.model_full_name,
        )

    for acl in load_acls(model_full_name=ops_test.model_full_name, zookeeper_uri=zookeeper_uri):
        assert acl.username in usernames
        assert acl.operation in ["CREATE", "READ", "WRITE", "DESCRIBE"]
        assert acl.resource_type in ["GROUP", "TOPIC"]
        if acl.resource_type == "TOPIC":
            assert acl.resource_name == "test-topic"


@pytest.mark.abort_on_fail
async def test_run_action_produce(ops_test: OpsTest, usernames):
    action = await ops_test.model.units.get("app/0").run_action("produce")
    await action.wait()
    breakpoint()
    try:
        assert action["results"]["result"] == "sent"
    except KeyError:
        assert False


@pytest.mark.abort_on_fail
async def test_run_action_consume(ops_test: OpsTest, usernames):
    action = await ops_test.model.units.get("app/0").run_action("consume")
    await action.wait()
    try:
        assert action["results"]["result"] == "pass"
    except KeyError:
        assert False
