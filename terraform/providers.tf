terraform {
  required_providers {
    juju = {
      version = "~> 0.6.0"
      source  = "juju/juju"
    }
  }
}

provider "juju" {}
