#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from zipfile import ZipFile

import jubilant
import pytest
import requests
import yaml
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

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def usernames():
    return set()


def test_verify_tls_flags_consistency(bundle_file, tls):
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


def test_deploy_bundle_active(testbed, cos_lite, lxd_controller, bundle_file, cos_overlay, tls):
    """Deploy the bundle."""
    logger.info(
        f"Deploying Bundle with file {bundle_file} and following overlay(s): {cos_overlay}"
    )

    testbed.use_vm()
    testbed.juju_cli(
        *[
            "deploy",
            "--trust",
            "-m",
            testbed.model,
            f"./{bundle_file}",
            "--overlay",
            f"{cos_overlay}",
        ],
        json_output=False,
    )

    testbed.juju.wait(lambda status: jubilant.all_active(status), timeout=1800)

    print([testbed.juju.status().apps])


def test_active_zookeeper(testbed):
    """Test the status the correct status of Zookeeper."""
    zookeeper_hosts = [
        unit.public_address for unit in testbed.juju.status().apps[ZOOKEEPER].units.values()
    ]
    assert ping_servers(zookeeper_hosts)


def test_deploy_app_charm_relate(testbed, bundle_file, tls):
    """Deploy dummy app and relate with Kafka and TLS operator."""
    with ZipFile(bundle_file) as fp:
        bundle_data = yaml.safe_load(fp.read("bundle.yaml"))

    applications = list(bundle_data["applications"].keys())

    app_charm = testbed.build_charm(APP_CHARM_PATH)
    testbed.juju.deploy(app_charm, app="app", num_units=1)
    if tls:
        testbed.juju.integrate("app", TLS_CHARM_NAME)

    testbed.juju.wait(lambda status: jubilant.all_active(status, apps=applications), timeout=2000)
    testbed.juju.integrate(KAFKA, "app")

    testbed.juju.wait(lambda status: jubilant.all_active(status), timeout=1000)


def test_apps_up_and_running(testbed, usernames):
    """Test that all apps are up and running."""
    zookeeper_hosts = [
        unit.public_address for unit in testbed.juju.status().apps[ZOOKEEPER].units.values()
    ]
    assert ping_servers(zookeeper_hosts)

    for unit in testbed.juju.status().apps[ZOOKEEPER].units:
        assert "sslQuorum=true" in check_properties(model_full_name=testbed.model, unit=unit)

    # implicitly tests setting of kafka app data
    zookeeper_usernames, zookeeper_uri = get_zookeeper_connection(
        unit_name=f"{KAFKA}/0", owner=ZOOKEEPER, model_full_name=testbed.model
    )

    assert zookeeper_uri
    assert len(zookeeper_usernames) > 0

    usernames.update(get_kafka_users(f"{KAFKA}/0", testbed.model))

    kafka_unit = next(iter(testbed.juju.status().apps[KAFKA].units))
    bootstrap_server = (
        f"{testbed.juju.status().apps[KAFKA].units[kafka_unit].public_address}:{TLS_PORT}"
    )

    for username in usernames:
        check_user(
            username=username,
            bootstrap_server=bootstrap_server,
            model_full_name=testbed.model,
            unit_name=f"{KAFKA}/0",
        )

    for acl in load_acls(
        model_full_name=testbed.model,
        bootstrap_server=bootstrap_server,
        unit_name=f"{KAFKA}/0",
    ):
        assert acl.username in usernames
        assert acl.operation in ["CREATE", "READ", "WRITE", "DESCRIBE"]
        assert acl.resource_type in ["GROUP", "TOPIC"]
        if acl.resource_type == "TOPIC":
            assert acl.resource_name == "test-topic"

    assert ping_servers(zookeeper_hosts)


def test_run_action_produce_consume(testbed):
    """Test production and consumption of messages."""
    time.sleep(100)
    ran_action = testbed.juju.run("app/0", "produce-consume")
    assert ran_action.results.get("passed", "") == "true"


#  -- COS Integration Tests --


def test_grafana(testbed, cos_lite):
    """Checks Grafana dashboard is created with desired attributes."""
    testbed.use_k8s()
    grafana_unit = next(iter(testbed.juju.status().apps[COS.GRAFANA].units.keys()))
    action = testbed.juju.run(grafana_unit, "get-admin-password")

    grafana_url = action.results.get("url")
    admin_password = action.results.get("admin-password")

    print(grafana_url, admin_password)

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


def test_metrics_and_alerts(testbed, cos_lite):
    """Checks alert rules are submitted and metrics are being sent to prometheus."""
    # wait a couple of minutes for metrics to show up
    testbed.use_k8s()
    logging.info("Sleeping for 5 min.")
    time.sleep(300)

    traefik_unit = next(iter(testbed.juju.status().apps[COS.TRAEFIK].units))
    action = testbed.juju.run(traefik_unit, "show-proxied-endpoints")

    prometheus_url = json.loads(action.results["proxied-endpoints"])[f"{COS.PROMETHEUS}/0"]["url"]

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

    logger.info(f'{len(kafka_alerts["rules"])} alert rules are registered:')
    for rule in kafka_alerts["rules"]:
        logger.info(f'|__ {rule["name"]}')


def test_loki(testbed, cos_lite):
    """Checks log streams are being pushed to loki."""
    testbed.use_k8s()
    traefik_unit = next(iter(testbed.juju.status().apps[COS.TRAEFIK].units))
    action = testbed.juju.run(traefik_unit, "show-proxied-endpoints")

    loki_url = json.loads(action.results["proxied-endpoints"])[f"{COS.LOKI}/0"]["url"]

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
