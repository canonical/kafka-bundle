<!-- BEGIN_TF_DOCS -->

This repository contains the machine charm Terraform bundle for the Charmed Apache Kafka, available on [Charmhub](https://charmhub.io/kafka).

The Charmed Apache Kafka Terraform bundle can be used to deploy Apache Kafka brokers and KRaft controllers, Kafka Connect, Karapace Schema Registry, and Kafbat Kafka UI with minimal configuration overhead.

For a quick start, please refer to the `examples` folder which contains sample deployment scenarios.

## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >=1.7.3 |
| <a name="requirement_juju"></a> [juju](#requirement\_juju) | >=0.20.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_juju"></a> [juju](#provider\_juju) | 0.23.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_broker"></a> [broker](#module\_broker) | git::https://github.com/canonical/kafka-operator//terraform | main |
| <a name="module_connect"></a> [connect](#module\_connect) | git::https://github.com/canonical/kafka-connect-operator//terraform | main |
| <a name="module_controller"></a> [controller](#module\_controller) | git::https://github.com/canonical/kafka-operator//terraform | main |
| <a name="module_karapace"></a> [karapace](#module\_karapace) | git::https://github.com/canonical/karapace-operator//terraform | main |
| <a name="module_ui"></a> [ui](#module\_ui) | git::https://github.com/canonical/kafka-ui-operator//terraform | main |

## Resources

| Name | Type |
|------|------|
| [juju_application.connect_cos_agent](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_application.integrator](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_application.kafka_cos_agent](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_application.kraft_cos_agent](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_integration.connect_cos](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.integrator_kafka](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_connect](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_connect_tls](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_connect_ui](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_cos](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_karapace](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_kraft](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_tls](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_ui](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kafka_ui_tls](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.karapace_tls](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.karapace_ui](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.kraft_cos](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_broker"></a> [broker](#input\_broker) | Defines the Apache Kafka broker application configuration | <pre>object({<br/>    app_name    = optional(string, "kafka-broker")<br/>    channel     = optional(string, "4/edge")<br/>    config      = optional(map(string), {})<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number, null)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 3)<br/>    storage     = optional(map(string), {})<br/>  })</pre> | `{}` | no |
| <a name="input_connect"></a> [connect](#input\_connect) | Defines the Kafka Connect application configuration | <pre>object({<br/>    app_name    = optional(string, "kafka-connect")<br/>    channel     = optional(string, "latest/edge")<br/>    config      = optional(map(string), {})<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number, null)<br/>    base        = optional(string, "ubuntu@22.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_controller"></a> [controller](#input\_controller) | Defines the Apache Kafka KRaft controller application configuration | <pre>object({<br/>    app_name    = optional(string, "kafka-controller")<br/>    channel     = optional(string, "4/edge")<br/>    config      = optional(map(string), {})<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number, null)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 3)<br/>    storage     = optional(map(string), {})<br/>  })</pre> | `{}` | no |
| <a name="input_cos_offers"></a> [cos\_offers](#input\_cos\_offers) | COS offers for observability. | <pre>object({<br/>    dashboard = optional(string, null),<br/>    metrics   = optional(string, null),<br/>    logging   = optional(string, null),<br/>    tracing   = optional(string, null)<br/>  })</pre> | `{}` | no |
| <a name="input_integrator"></a> [integrator](#input\_integrator) | Defines the Integrator application configuration | <pre>object({<br/>    app_name = optional(string, "data-integrator")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      topic-name       = "__admin-user"<br/>      extra-user-roles = "admin"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number, null)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_karapace"></a> [karapace](#input\_karapace) | Defines the Karapace application configuration | <pre>object({<br/>    app_name    = optional(string, "karapace")<br/>    channel     = optional(string, "latest/edge")<br/>    config      = optional(map(string), {})<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number, null)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_model"></a> [model](#input\_model) | The name of the Juju Model to deploy to | `string` | n/a | yes |
| <a name="input_profile"></a> [profile](#input\_profile) | The deployment profile to use, either 'production' or 'testing' | `string` | `"testing"` | no |
| <a name="input_tls_offer"></a> [tls\_offer](#input\_tls\_offer) | TLS Provider endpoint to be used on Client relations. | `string` | `null` | no |
| <a name="input_ui"></a> [ui](#input\_ui) | Defines the Kafbat Kafka UI application configuration | <pre>object({<br/>    app_name    = optional(string, "kafka-ui")<br/>    channel     = optional(string, "latest/edge")<br/>    config      = optional(map(string), {})<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number, null)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_app_names"></a> [app\_names](#output\_app\_names) | Output of all deployed application names. |
| <a name="output_offers"></a> [offers](#output\_offers) | List of offers URLs. |
<!-- END_TF_DOCS -->