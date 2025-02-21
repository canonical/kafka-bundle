#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from zipfile import ZipFile

import pytest
import requests
import yaml
from juju.model import Model
from pytest_operator.plugin import OpsTest
from requests.auth import HTTPBasicAuth
from tests.integration.bundle.cos_helpers import COS, COSAssertions
from tests.integration.bundle.kafka_helpers import (
    check_properties,
    check_user,
    get_kafka_users,
    get_zookeeper_connection,
    load_acls,
    ping_servers,
)
from tests.integration.bundle.literals import (
    APP_CHARM_PATH,
    KAFKA,
    TLS_CHARM_NAME,
    TLS_PORT,
    ZOOKEEPER,
)
from tests.integration.bundle.multi_cloud import OpsTestbed

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def usernames():
    return set()


@pytest.mark.abort_on_fail
async def test_verify_tls_flags_consistency(ops_test: OpsTest, bundle_file, tls):
    """Deploy the bundle."""
    with ZipFile(bundle_file) as fp:
        bundle_data = yaml.safe_load(fp.read("bundle.yaml"))

    applications = []

    bundle_tls = False
    for app in bundle_data["applications"]:
        applications.append(app)
        if TLS_CHARM_NAME in app:
            bundle_tls = True

    assert tls == bundle_tls


@pytest.mark.abort_on_fail
async def test_deploy_bundle_active(ops_test: OpsTest, bundle_file, tls):
    """Deploy the bundle."""
    logger.info(f"Deploying Bundle with file {bundle_file}")
    retcode, stdout, stderr = await ops_test.run(
        *["juju", "deploy", "--trust", "-m", ops_test.model_full_name, f"./{bundle_file}"]
    )
    assert retcode == 0, f"Deploy failed: {(stderr or stdout).strip()}"
    logger.info(stdout)

    with ZipFile(bundle_file) as fp:
        bundle = yaml.safe_load(fp.read("bundle.yaml"))

    async with ops_test.fast_forward(fast_interval="30s"):
        await ops_test.model.wait_for_idle(
            apps=list(bundle["applications"].keys()),
            idle_period=10,
            status="active",
            timeout=1800,
        )


@pytest.mark.abort_on_fail
async def test_active_zookeeper(ops_test: OpsTest):
    """Test the status the correct status of Zookeeper."""
    assert await ping_servers(ops_test, ZOOKEEPER)


@pytest.mark.abort_on_fail
async def test_deploy_app_charm_relate(ops_test: OpsTest, bundle_file, tls):
    """Deploy dummy app and relate with Kafka and TLS operator."""
    with ZipFile(bundle_file) as fp:
        bundle_data = yaml.safe_load(fp.read("bundle.yaml"))

    applications = list(bundle_data["applications"].keys())

    app_charm = await ops_test.build_charm(APP_CHARM_PATH)
    await ops_test.model.deploy(app_charm, application_name="app", num_units=1)
    if tls:
        await ops_test.model.add_relation("app", TLS_CHARM_NAME)
    await ops_test.model.wait_for_idle(
        apps=applications, timeout=2000, idle_period=30, status="active"
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
    zookeeper_usernames, zookeeper_uri = get_zookeeper_connection(
        unit_name=f"{KAFKA}/0", owner=ZOOKEEPER, model_full_name=ops_test.model_full_name
    )

    assert zookeeper_uri
    assert len(zookeeper_usernames) > 0

    usernames.update(get_kafka_users(f"{KAFKA}/0", ops_test.model_full_name))

    bootstrap_server = f"{ops_test.model.applications[KAFKA].units[0].public_address}:{TLS_PORT}"

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


#  -- COS Integration Tests --


@pytest.mark.abort_on_fail
async def test_deploy_charms(testbed: OpsTestbed, cos_lite: Model, test_model: Model):

    await asyncio.gather(
        test_model.deploy(COS.GRAFANA_AGENT, COS.GRAFANA_AGENT, channel="edge"),
    )

    await test_model.wait_for_idle(status="active", idle_period=60, timeout=1800)

    await test_model.consume(
        f"{testbed.microk8s_controller}:admin/{cos_lite.name}.{COS.PROMETHEUS_OFFER}"
    )
    await test_model.consume(
        f"{testbed.microk8s_controller}:admin/{cos_lite.name}.{COS.LOKI_OFFER}"
    )
    await test_model.consume(
        f"{testbed.microk8s_controller}:admin/{cos_lite.name}.{COS.GRAFANA_OFFER}"
    )

    await test_model.relate(COS.GRAFANA_AGENT, KAFKA)
    await test_model.relate(COS.GRAFANA_AGENT, COS.PROMETHEUS_OFFER)
    await test_model.relate(COS.GRAFANA_AGENT, COS.LOKI_OFFER)
    await test_model.relate(COS.GRAFANA_AGENT, COS.GRAFANA_OFFER)

    await test_model.wait_for_idle(idle_period=30, timeout=600, status="active")


@pytest.mark.abort_on_fail
async def test_grafana(cos_lite: Model):
    grafana_unit = cos_lite.applications[COS.GRAFANA].units[0]
    action = await grafana_unit.run_action("get-admin-password")
    response = await action.wait()

    grafana_url = response.results.get("url")
    admin_password = response.results.get("admin-password")

    auth = HTTPBasicAuth("admin", admin_password)
    dashboards = requests.get(f"{grafana_url}/api/search?query={KAFKA}", auth=auth).json()

    assert dashboards

    match = [dash for dash in dashboards if dash["title"] == COSAssertions.DASHBOARD_TITLE]

    assert match

    app_dashboard = match[0]
    dashboard_uid = app_dashboard["uid"]

    details = requests.get(f"{grafana_url}/api/dashboards/uid/{dashboard_uid}", auth=auth).json()

    panels = details["dashboard"]["panels"]

    assert len(panels) == COSAssertions.PANELS_COUNT

    panel_titles = [_panel.get("title") for _panel in panels]

    logger.warning(
        f"{len([i for i in panel_titles if not i])} panels don't have title which might be an issue."
    )
    logger.warning(
        f'{len([i for i in panel_titles if i and i.title() != i])} panels don\'t observe "Panel Title" format.'
    )

    for item in COSAssertions.PANELS_TO_CHECK:
        assert item in panel_titles

    logger.info(f"{COSAssertions.DASHBOARD_TITLE} dashboard has following panels:")
    for panel in panel_titles:
        logger.info(f"|__ {panel}")


@pytest.mark.abort_on_fail
async def test_metrics_and_alerts(cos_lite: Model):
    # wait a couple of minutes for metrics to show up
    logging.info("Sleeping for 5 min.")
    await asyncio.sleep(300)

    traefik_unit = cos_lite.applications[COS.TRAEFIK].units[0]
    action = await traefik_unit.run_action("show-proxied-endpoints")
    response = await action.wait()

    prometheus_url = json.loads(response.results["proxied-endpoints"])[f"{COS.PROMETHEUS}/0"][
        "url"
    ]

    # metrics

    response = requests.get(f"{prometheus_url}/api/v1/label/__name__/values").json()
    metrics = [i for i in response["data"] if KAFKA in i]

    assert metrics, f"No {KAFKA} metrics found!"
    logger.info(f'{len(metrics)} metrics found for "{KAFKA}" in prometheus.')

    # alerts

    response = requests.get(f"{prometheus_url}/api/v1/rules?type=alert").json()

    match = [group for group in response["data"]["groups"] if KAFKA in group["name"].lower()]

    assert match

    kafka_alerts = match[0]

    assert len(kafka_alerts["rules"]) == COSAssertions.ALERTS_COUNT

    logger.info("Following alert rules are registered:")
    for rule in kafka_alerts["rules"]:
        logger.info(f'|__ {rule["name"]}')


@pytest.mark.abort_on_fail
async def test_loki(cos_lite: Model):
    traefik_unit = cos_lite.applications[COS.TRAEFIK].units[0]
    action = await traefik_unit.run_action("show-proxied-endpoints")
    response = await action.wait()

    loki_url = json.loads(response.results["proxied-endpoints"])[f"{COS.LOKI}/0"]["url"]

    endpoint = f"{loki_url}/loki/api/v1/query_range"
    headers = {"Accept": "application/json"}

    start_time = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"query": f'{{juju_application="{KAFKA}"}} |= ``', "start": start_time}

    response = requests.get(endpoint, params=payload, headers=headers, verify=False)
    results = response.json()["data"]["result"]
    streams = [i["stream"]["filename"] for i in results]

    assert len(streams) >= len(COSAssertions.LOG_STREAMS)
    for _stream in COSAssertions.LOG_STREAMS:
        assert _stream in streams

    logger.info("Displaying some of the logs pushed to loki:")
    for item in results:
        # we should have some logs
        assert len(item["values"]) > 0, f'No log pushed for {item["stream"]["filename"]}'

        logger.info(f'Stream: {item["stream"]["filename"]}')
        for _, log in item["values"][:10]:
            logger.info(f"|__ {log}")
        logger.info("\n")
