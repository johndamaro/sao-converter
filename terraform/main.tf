terraform {
  required_providers {
    dbtcloud = {
      source  = "dbt-labs/dbtcloud"
      version = "~> 0.3"
    }
  }
}

# Credentials are read from environment variables:
#   DBT_CLOUD_ACCOUNT_ID
#   DBT_CLOUD_TOKEN
#   DBT_CLOUD_HOST_URL  (optional, defaults to https://cloud.getdbt.com/api)
provider "dbtcloud" {}
