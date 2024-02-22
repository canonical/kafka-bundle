terraform {
  required_version = ">=1.7.3"

  required_providers {
    juju = {
      version = "~> 0.10.0"
      source  = "juju/juju"
    }
  }
}

provider "juju" {}
