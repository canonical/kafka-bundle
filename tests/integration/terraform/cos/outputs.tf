# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "offers" {
  description = "COS offer URLs for cross-model integration with Kafka."
  value = {
    grafana_dashboards = module.cos-lite.offers.grafana_dashboards
    prometheus_metrics = module.cos-lite.offers.prometheus_metrics_endpoint
    loki_logging       = module.cos-lite.offers.loki_logging
  }
}
