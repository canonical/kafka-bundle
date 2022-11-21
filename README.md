# Kafka Bundle

This repository contains both machine and k8s charm bundles for Kafka.

## Usage
Create a [Juju controller](https://juju.is/docs/olm/create-a-controller)

Add a Juju model for your deployment, for example:
```bash
juju add-model kafka
juju switch kafka
```
You can deploy the bundle from CharmHub to VM/machines:
```bash
juju deploy kafka-bundle --channel=edge
```
and similarly for Kubernetes:
```bash
juju deploy kafka-k8s-bundle --channel=edge
```

## Production Storage - VM ONLY
For certain workloads, you may wish to provision more storage. The supported production storage configuration is as follows:
- 12x 1TB storage volumes per Kafka broker
- 1x 10GB storage volume per ZooKeeper server

### Deploying production storage
To deploy the bundle with the supported production storage attached, you may do the following:
```bash
juju deploy ./releases/latest/machine/kafka/bundle.yaml --overlay ./overlays/production.yaml
```
