#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


class COS:
    TRAEFIK = "traefik"
    GRAFANA = "grafana"
    LOKI = "loki"
    PROMETHEUS = "prometheus"
    GRAFANA_AGENT = "grafana-agent"
    PROMETHEUS_OFFER = "prometheus-receive-remote-write"
    LOKI_OFFER = "loki-logging"
    GRAFANA_OFFER = "grafana-dashboards"


class COSAssertions:
    APP = "kafka"
    DASHBOARD_TITLE = "Kafka Metrics"
    PANELS_COUNT = 44
    PANELS_TO_CHECK = (
        "JVM",
        "Brokers Online",
        "Active Controllers",
        "Total of Topics",
    )
    ALERTS_COUNT = 24
    LOG_STREAMS = (
        # "/var/snap/charmed-kafka/common/var/log/kafka/kafkaServer-gc.log",
        "/var/snap/charmed-kafka/common/var/log/kafka/server.log",
    )


def deploy_cos_script(controller: str, model_name: str = "cos", channel: str = "edge"):
    """Generates a script to deploy COS lite bundle."""
    return f"""
        # deploy COS-Lite
        juju switch {controller}
        juju add-model {model_name}
        juju switch {model_name}

        curl -L https://raw.githubusercontent.com/canonical/cos-lite-bundle/main/overlays/offers-overlay.yaml -O
        curl -L https://raw.githubusercontent.com/canonical/cos-lite-bundle/main/overlays/storage-small-overlay.yaml -O

        juju deploy cos-lite --channel {channel} --trust --overlay ./offers-overlay.yaml --overlay ./storage-small-overlay.yaml

        rm ./offers-overlay.yaml ./storage-small-overlay.yaml
    """
