#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""COS integration tests for the Kafka bundle Terraform module."""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import requests
from jubilant import Juju
from tests.integration.terraform.helpers import (
    COS,
    COSAssertions,
    all_active_idle,
    get_app_list,
)

logger = logging.getLogger(__name__)

KAFKA = COSAssertions.APP


def test_cos_deployment_active(cos_deployer, cos_juju: Juju):
    """Test that all COS apps are active in the COS model."""
    status = cos_juju.status()
    for app in COS.APPS:
        assert app in status.apps, f"COS app '{app}' not found in model"
        assert (
            status.apps[app].app_status.current == "active"
        ), f"COS app '{app}' is not active: {status.apps[app].app_status.current}"


def test_kafka_with_cos_deployment_active(juju: Juju, kraft_mode, deploy_cluster_with_cos):
    """Test that all Kafka apps are active with COS integration."""
    app_list = get_app_list(kraft_mode)
    juju.wait(
        lambda status: all_active_idle(status, *app_list),
        delay=3,
        successes=20,
        timeout=3600,
    )
    status = juju.status()
    for app in app_list:
        assert status.apps[app].app_status.current == "active"


#  -- COS Integration Tests --


def test_grafana_dashboard(cos_juju: Juju):
    """Verify Grafana dashboard exists with expected panels."""
    result = cos_juju.run(unit=f"{COS.GRAFANA}/0", action="get-admin-password")
    grafana_url = result.results.get("url")
    admin_password = result.results.get("admin-password")

    auth = ("admin", admin_password)

    dashboards = requests.get(
        f"{grafana_url}/api/search?query={KAFKA}",
        auth=auth,
        verify=False,
    ).json()
    assert dashboards, "No Kafka dashboards found in Grafana"

    dashboard_titles = [d["title"] for d in dashboards]
    for expected_title in COSAssertions.DASHBOARDS:
        assert expected_title in dashboard_titles, f"Dashboard '{expected_title}' not found"

    match = [d for d in dashboards if d["title"] == COSAssertions.DASHBOARDS[0]]
    dashboard_uid = match[0]["uid"]
    details = requests.get(
        f"{grafana_url}/api/dashboards/uid/{dashboard_uid}",
        auth=auth,
        verify=False,
    ).json()

    panels = details["dashboard"]["panels"]
    assert (
        len(panels) == COSAssertions.PANELS_COUNT
    ), f"Expected {COSAssertions.PANELS_COUNT} panels, got {len(panels)}"

    panel_titles = [p.get("title") for p in panels]

    logger.info(f"{len([t for t in panel_titles if not t])} panels don't have a title.")

    for expected in COSAssertions.PANELS_TO_CHECK:
        assert expected in panel_titles, f"Panel '{expected}' not found"

    logger.info(f"{COSAssertions.DASHBOARDS[0]} dashboard has following panels:")
    for title in panel_titles:
        logger.info(f"|__ {title}")


def test_prometheus_metrics_and_alerts(cos_juju: Juju, kraft_mode):
    """Verify Prometheus has kafka metrics and alert rules."""
    logger.info("Sleeping 5 minutes for metrics to accumulate...")
    time.sleep(300)

    result = cos_juju.run(unit=f"{COS.TRAEFIK}/0", action="show-proxied-endpoints")
    proxied_endpoints = json.loads(result.results["proxied-endpoints"])
    prometheus_url = proxied_endpoints[f"{COS.PROMETHEUS}/0"]["url"]

    # Check metrics
    response = requests.get(
        f"{prometheus_url}/api/v1/label/__name__/values",
        verify=False,
    ).json()
    metrics = [m for m in response["data"] if KAFKA in m]
    assert metrics, f"No {KAFKA} metrics found in Prometheus"
    logger.info(f"{len(metrics)} kafka metrics found in Prometheus.")

    # Check alert rules
    response = requests.get(
        f"{prometheus_url}/api/v1/rules?type=alert",
        verify=False,
    ).json()
    match = [g for g in response["data"]["groups"] if KAFKA in g["name"].lower()]
    assert match, "No kafka alert rule groups found"

    kafka_alerts = [rule for g in match for rule in g["rules"]]
    expected_alerts = (
        COSAssertions.ALERTS_COUNT_SINGLE
        if kraft_mode == "single"
        else COSAssertions.ALERTS_COUNT_MULTI
    )
    assert (
        len(kafka_alerts) == expected_alerts
    ), f"Expected {expected_alerts} alerts, got {len(kafka_alerts)}"

    logger.info(f"{len(kafka_alerts)} alert rules are registered:")
    for rule in kafka_alerts:
        logger.info(f'|__ {rule["name"]}')


def test_loki_log_streams(cos_juju: Juju):
    """Verify Loki is receiving log streams from Kafka."""
    result = cos_juju.run(unit=f"{COS.TRAEFIK}/0", action="show-proxied-endpoints")
    proxied_endpoints = json.loads(result.results["proxied-endpoints"])
    loki_url = proxied_endpoints[f"{COS.LOKI}/0"]["url"]

    start_time = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = requests.get(
        f"{loki_url}/loki/api/v1/query_range",
        params={
            "query": '{juju_application="kafka-broker"} |= ``',
            "start": start_time,
        },
        headers={"Accept": "application/json"},
        verify=False,
    )
    results = response.json()["data"]["result"]

    assert len(results) > 0, "No log streams found for kafka-broker in Loki"

    for item in results:
        assert (
            len(item["values"]) > 0
        ), f"No log entries for stream {item['stream'].get('filename', 'unknown')}"

    logger.info(f"Found {len(results)} log streams for kafka-broker in Loki:")
    for item in results:
        logger.info(f'|__ Stream: {item["stream"].get("filename", item["stream"])}')
        for _, log in item["values"][:10]:
            logger.info(f"    |__ {log}")
