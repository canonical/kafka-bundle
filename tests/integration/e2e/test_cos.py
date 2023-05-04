# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Metrics and logs from a machine charm are ingested over juju-info/cos_agent by COS Lite."""

import asyncio
import logging
import subprocess
import time

import pytest
from tests.integration.e2e.literals import (
    GRAFANA_AGENT_CHARM_NAME,
    KAFKA_CHARM_NAME,
    ZOOKEEPER_CHARM_NAME,
)

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_setup_models(lxd_setup, k8s_setup):
    _, k8s_mdl = k8s_setup
    _, lxd_mdl = lxd_setup
    await lxd_mdl.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})
    await k8s_mdl.set_config({"logging-config": "<root>=WARNING; unit=DEBUG"})


@pytest.mark.abort_on_fail
async def test_deploy_cos(k8s_setup):
    # Use CLI to deploy bundle until https://github.com/juju/python-libjuju/issues/816 is fixed.
    # await k8s_mdl.deploy(str(rendered_bundle), trust=True)
    k8s_ctl, k8s_mdl = k8s_setup
    cmd = [
        "juju",
        "deploy",
        "--trust",
        "-m",
        f"{k8s_ctl.controller_name}:{k8s_mdl.name}",
        "cos-lite",
        "--overlay",
        "./tests/integration/e2e/overlays/offers-overlay.yaml",
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.output.decode())
        raise

    time.sleep(60)
    await k8s_mdl.wait_for_idle(
        apps=["loki", "grafana", "prometheus", "catalogue", "traefik", "alertmanager"],
        idle_period=60,
        timeout=3600,
        raise_on_error=False,
    )
    for _, app in k8s_mdl.applications:
        assert app.status == "active"


@pytest.mark.abort_on_fail
async def test_deploy_machine_charms(lxd_setup):
    _, lxd_mdl = lxd_setup
    await asyncio.gather(
        lxd_mdl.deploy(
            ZOOKEEPER_CHARM_NAME,
            channel="edge",
            application_name=ZOOKEEPER_CHARM_NAME,
            num_units=1,
            series="jammy",
        ),
        lxd_mdl.deploy(
            KAFKA_CHARM_NAME,
            channel="edge",
            application_name=KAFKA_CHARM_NAME,
            num_units=1,
            series="jammy",
        ),
        lxd_mdl.deploy(
            GRAFANA_AGENT_CHARM_NAME,
            channel="edge",
            application_name=GRAFANA_AGENT_CHARM_NAME,
            num_units=0,
            series="jammy",
        ),
    )
    await lxd_mdl.wait_for_idle(
        apps=[KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME], idle_period=30, timeout=3600
    )
    assert lxd_mdl.applications[KAFKA_CHARM_NAME].status == "blocked"
    assert lxd_mdl.applications[ZOOKEEPER_CHARM_NAME].status == "active"

    await asyncio.gather(
        lxd_mdl.add_relation(KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME),
        lxd_mdl.wait_for_idle(apps=[KAFKA_CHARM_NAME, ZOOKEEPER_CHARM_NAME], idle_period=30),
    )
    assert lxd_mdl.applications[KAFKA_CHARM_NAME].status == "active"
    assert lxd_mdl.applications[ZOOKEEPER_CHARM_NAME].status == "active"

    await asyncio.gather(
        lxd_mdl.add_relation("kafka:cos-agent", GRAFANA_AGENT_CHARM_NAME),
        lxd_mdl.add_relation("zookeeper:cos-agent", GRAFANA_AGENT_CHARM_NAME),
        lxd_mdl.block_until(lambda: len(lxd_mdl.applications[GRAFANA_AGENT_CHARM_NAME].units) > 0),
    )


@pytest.mark.abort_on_fail
async def test_integration(k8s_setup, lxd_setup):
    k8s_ctl, k8s_mdl = k8s_setup
    _, lxd_mdl = lxd_setup
    # The consumed endpoint names must match offers-overlay.yaml.
    await asyncio.gather(
        lxd_mdl.consume(
            f"admin/{k8s_mdl.name}.prometheus-receive-remote-write",
            application_alias="prometheus",
            controller_name=k8s_ctl.controller_name,  # same as os.environ["K8S_CONTROLLER"]
        ),
        lxd_mdl.consume(
            f"admin/{k8s_mdl.name}.loki-logging",
            application_alias="loki",
            controller_name=k8s_ctl.controller_name,  # same as os.environ["K8S_CONTROLLER"]
        ),
        lxd_mdl.consume(
            f"admin/{k8s_mdl.name}.grafana-dashboards",
            application_alias="grafana",
            controller_name=k8s_ctl.controller_name,  # same as os.environ["K8S_CONTROLLER"]
        ),
    )

    await asyncio.gather(
        lxd_mdl.add_relation(GRAFANA_AGENT_CHARM_NAME, "prometheus"),
        lxd_mdl.add_relation(GRAFANA_AGENT_CHARM_NAME, "loki"),
        lxd_mdl.add_relation(GRAFANA_AGENT_CHARM_NAME, "grafana"),
    )

    # `idle_period` needs to be greater than the scrape interval to make sure metrics ingested.
    await asyncio.gather(
        lxd_mdl.wait_for_idle(
            status="active", timeout=7200, idle_period=180, raise_on_error=False
        ),
        k8s_mdl.wait_for_idle(
            status="active", timeout=7200, idle_period=180, raise_on_error=False
        ),
    )


async def test_metrics(k8s_setup):
    """Make sure machine charm metrics reach Prometheus."""
    k8s_ctl, k8s_mdl = k8s_setup

    # Get the values of all `juju_unit` labels in prometheus
    # Output looks like this:
    # {"status":"success","data":[
    #  "agent/0","agent/1","agent/10","agent/11","agent/2","agent/3","agent/8","agent/9",
    #  "alertmanager/0","grafana/0",
    #  "principal-cos-agent/2","principal-cos-agent/3",
    #  "principal-juju-info/0","principal-juju-info/1",
    #  "prometheus-k8s","traefik/0"
    # ]}
    cmd = [
        "juju",
        "ssh",
        "-m",
        f"{k8s_ctl.controller_name}:{k8s_mdl.name}",
        "prometheus/0",
        "curl",
        f"localhost:9090/{k8s_mdl.name}-prometheus-0/api/v1/label/juju_unit/values",
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.stdout.decode())
        raise
    output = result.stdout.decode().strip()
    logger.info("Label values: %s", output)
    assert output.count(KAFKA_CHARM_NAME) == 1
    assert output.count(ZOOKEEPER_CHARM_NAME) == 1
    assert output.count(GRAFANA_AGENT_CHARM_NAME) >= 2


async def test_logs(k8s_setup):
    """Make sure machine charm logs reach Loki."""
    k8s_ctl, k8s_mdl = k8s_setup
    # Get the values of all `juju_unit` labels in loki
    # Loki uses strip_prefix, so we do need to use the ingress path
    # Output looks like this:
    # {"status":"success","data":[
    #  "principal-cos-agent/2","principal-cos-agent/3",
    #  "principal-juju-info/0","principal-juju-info/1"
    # ]}
    cmd = [
        "juju",
        "ssh",
        "-m",
        f"{k8s_ctl.controller_name}:{k8s_mdl.name}",
        "loki/0",
        "curl",
        "localhost:3100/loki/api/v1/label/juju_unit/values",
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.stdout.decode())
        raise

    output = result.stdout.decode().strip()
    logger.info("Label values: %s", output)
    assert output.count(KAFKA_CHARM_NAME) == 1
    assert output.count(ZOOKEEPER_CHARM_NAME) == 1


async def test_dashboards(k8s_setup):
    k8s_ctl, k8s_mdl = k8s_setup
    # Get grafana admin password
    action = await k8s_mdl.applications["grafana"].units[0].run_action("get-admin-password")
    action = await action.wait()
    password = action.results["admin-password"]

    # Get all dashboards
    # Grafana uses strip_prefix, so we do need to use the ingress path
    # Output looks like this:
    # [
    #  {"id":6,"uid":"exunkijMk","title":"Grafana Agent Node Exporter Quickstart",
    #   "uri":"db/grafana-agent-node-exporter-quickstart",
    #   "url":"/cos-grafana/d/exunkijMk/grafana-agent-node-exporter-quickstart","slug":"",
    #   "type":"dash-db","tags":[],"isStarred":false,"sortMeta":0},
    #  {"id":4,"uid":"rYdddlPWk","title":"System Resources","uri":"db/system-resources",
    #   "url":"/cos-grafana/d/rYdddlPWk/system-resources","slug":"","type":"dash-db",
    #   "tags":["linux"],"isStarred":false,"sortMeta":0},
    #  {"id":5,"uid":"SDE76m7Zzz","title":"ZooKeeper by Prometheus",
    #   "uri":"db/zookeeper-by-prometheus",
    #   "url":"/cos-grafana/d/SDE76m7Zzz/zookeeper-by-prometheus","slug":"","type":"dash-db",
    #   "tags":["v4"],"isStarred":false,"sortMeta":0}
    # ]
    cmd = [
        "juju",
        "ssh",
        "-m",
        f"{k8s_ctl.controller_name}:{k8s_mdl.name}",
        "grafana/0",
        "curl",
        "--user",
        f"admin:{password}",
        "localhost:3000/api/search",
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.stdout.decode())
        raise

    output = result.stdout.decode().strip()
    assert "kafka" in output
    assert "zookeeper" in output
    assert "grafana-agent-node-exporter" in output


async def test_destroy(ops_test, lxd_setup, k8s_setup):
    _, lxd_mdl = lxd_setup
    _, k8s_mdl = k8s_setup

    if ops_test.keep_model:
        return

    # First, must remove the machine charms and saas, otherwise:
    # ERROR cannot destroy application "grafana": application is used by 3 consumers
    # Do not `block_until_done=True` because of the juju bug where teardown never completes.
    await asyncio.gather(
        lxd_mdl.remove_application(GRAFANA_AGENT_CHARM_NAME),
        lxd_mdl.remove_application(KAFKA_CHARM_NAME),
        lxd_mdl.remove_application(ZOOKEEPER_CHARM_NAME),
    )
    await asyncio.gather(
        lxd_mdl.remove_saas("prometheus"),
        lxd_mdl.remove_saas("loki"),
        lxd_mdl.remove_saas("grafana"),
    )
    # Give it some time to settle, since we cannot block until complete.
    await asyncio.sleep(60)

    # Now remove traefik politely to avoid IP binding issues in the next test
    await k8s_mdl.remove_application("traefik")
    # Give it some time to settle, since we cannot block until complete.
    await asyncio.sleep(60)

    # The rest can be forcefully removed by pytest-operator.
