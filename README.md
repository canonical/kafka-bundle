# Kafka Bundle

This repository contains the machine charm bundles for Kafka.

## Usage
The steps outlined below are based on the assumption that you are deploying the charm locally with the latest LTS of Ubuntu.  If you are using another version of Ubuntu or another operating system, the process may be different.

### Install and Configure Dependencies
```bash
sudo snap install lxd --classic
sudo snap install juju --classic
```

### Create a [Juju controller](https://juju.is/docs/olm/create-a-controller)
```bash
juju bootstrap localhost 
```

### Create a Model in Juju
```bash
juju add-model kafka
juju switch kafka
```
###Deploy the Bundle
```bash
juju deploy kafka-bundle --channel=edge

## Production Storage
For certain workloads, you may wish to provision more storage. The supported production storage configuration is as follows:
- 12x 1TB storage volumes per Kafka broker
- 1x 10GB storage volume per ZooKeeper server

### Deploying production storage
To deploy the bundle with the supported production storage attached, you may do the following:
```bash
juju deploy kafka-bundle --overlay ./overlays/production.yaml
```
