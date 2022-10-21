# Kafka + Zookeeper Kubernetes Bundle

## A fast and fault-tolerant, real-time event streaming platform!

Manual, Day 2 operations for deploying and operating Apache Kafka, topic creation, client authentication, ACL management and more are all handled automatically using the [Juju Operator Lifecycle Manager](https://juju.is/docs/olm).

### Key Features
- SASL/SCRAM auth for Broker-Broker and Client-Broker authenticaion enabled by default.
- Access control management supported with user-provided ACL lists.
- Fault-tolerance, replication and high-availability out-of-the-box.
- Streamlined topic-creation through [Juju Actions](https://juju.is/docs/olm/working-with-actions) and [application relations](https://juju.is/docs/olm/relations)


Deployed with various components, these bundles support Kafka + Zookeeper with TLS support.  This includes encryption between nodes in the cluster as well as client communication.
