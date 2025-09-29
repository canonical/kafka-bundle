output "offers" {
  description = "List of offers URLs."
  value = merge(
    {
      kafka-client = module.broker.offers.kafka-client
    },
    {
      connect-client = var.connect.units > 0 ? module.connect[0].offers.connect-client : null
    },
    {
      karapace-client = var.karapace.units > 0 ? module.karapace[0].offers.karapace-client : null
    }
  )
}

output "app_names" {
  description = "Output of all deployed application names."
  value = {
    broker     = module.broker.app_name
    controller = local.controller_app_name,
    connect    = local.connect_app_name,
    karapace   = local.karapace_app_name,
    ui         = local.ui_app_name
  }
}