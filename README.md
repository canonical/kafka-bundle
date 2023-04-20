# Kafka Bundle

This repository contains the machine charm bundles for Kafka.

## Usage
The steps outlined below are based on the assumption that you are deploying the charm locally with the latest LTS of Ubuntu.  If you are using another version of Ubuntu or another operating system, the process may be different.

### Install and Configure Dependencies
```bash
# (required) installing lxd and juju
sudo snap install lxd --classic
sudo snap install juju --classic

# (optional) installing terraform
sudo snap install terraform
```

### Create a [Juju controller](https://juju.is/docs/olm/create-a-controller) on LXD
```bash
juju bootstrap localhost 
```

### Deploying a Charmed Kafka cluster
If looking for a simple Charmed Kafka cluster environment to experiment and develop with, there are multiple supported methods one can use.

##### Deploying using Terraform
```bash
cd terraform/dev
terraform init
terraform apply
```

##### Deploying using Juju
```bash
juju add-model dev && juju switch dev
juju deploy kafka-bundle
```

## Production Configuration
For certain workloads, you may wish to provision more storage. The supported production storage configuration is as follows:
- 12x 1TB storage volumes per Kafka broker
- 1x 10GB storage volume per ZooKeeper server

You can see example production-ready configurations here:
- [Terraform production `tfvars` configuration](https://github.com/canonical/kafka-bundle/blob/main/terraform/prod/prod.auto.tfvars)
    - NOTE - Currently does not support defining multiple storage volumes at deploy-time. These will need to be added manually with `juju add-storage kafka -n 11` for production
- [Juju Bundle production overlays](https://github.com/canonical/kafka-bundle/blob/main/overlays/production.yaml)
