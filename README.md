# Kafka Bundle

This repository contains both machine and k8s charm bundles for Kafka.

To deploy a bundle:

1) Create a [Juju controller](https://juju.is/docs/olm/create-a-controller)

2) Add a Juju model
```bash
juju add-model kafka
```
3) Deploy the bundle to the newly-created model
```bash
# The bundle must match the cloud type (i.e. kafka-k8s.yaml can only be deployed on K8s)
juju deploy ./path/to/bundle.yaml
```