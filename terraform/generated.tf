resource "dbtcloud_project" "terraform_managed_resource_70437463664450" {
  name = "John's Demo"
}

resource "dbtcloud_project" "terraform_managed_resource_70437463664888" {
  dbt_project_subdirectory = "jaffle_shop"
  name                     = "SAO Job Converter"
}

resource "dbtcloud_environment" "terraform_managed_resource_70437463668185" {
  connection_id              = 70437463659279
  dbt_version                = "latest"
  enable_model_query_history = false
  name                       = "Development"
  project_id                 = 70437463664450
  type                       = "development"
  use_custom_branch          = false
}

resource "dbtcloud_environment" "terraform_managed_resource_70437463668476" {
  connection_id              = 70437463659280
  dbt_version                = "latest"
  enable_model_query_history = false
  name                       = "Development"
  project_id                 = 70437463664888
  type                       = "development"
  use_custom_branch          = false
}

resource "dbtcloud_environment" "terraform_managed_resource_70437463668477" {
  connection_id              = 70437463659279
  credential_id              = 70437463673582
  dbt_version                = "latest"
  deployment_type            = "production"
  enable_model_query_history = false
  name                       = "Production"
  project_id                 = 70437463664888
  type                       = "deployment"
  use_custom_branch          = false
}

resource "dbtcloud_job" "terraform_managed_resource_70437463758847" {
  compare_changes_flags  = "--select state:modified"
  environment_id         = 70437463668477
  errors_on_lint_failure = true
  execute_steps          = ["dbt seed", "dbt build -s staging.*"]
  generate_docs          = false
  job_type               = "scheduled"
  name                   = "Incremental load - 6 hours"
  num_threads            = 4
  project_id             = 70437463664888
  run_compare_changes    = false
  run_generate_sources   = false
  run_lint               = false
  schedule_cron          = "10 */6 * * 1,2,3,4,5"
  schedule_type          = "custom_cron"
  target_name            = "default"
  timeout_seconds        = 0
  triggers = {
    git_provider_webhook = false
    github_webhook       = false
    on_merge             = false
    schedule             = true
  }
  triggers_on_draft_pr = false
}

resource "dbtcloud_job" "terraform_managed_resource_70437463758861" {
  compare_changes_flags  = "--select state:modified"
  environment_id         = 70437463668477
  errors_on_lint_failure = true
  execute_steps          = ["dbt build -s marts.*"]
  generate_docs          = false
  job_type               = "scheduled"
  name                   = "Incremental Load - Daily"
  num_threads            = 4
  project_id             = 70437463664888
  run_compare_changes    = false
  run_generate_sources   = false
  run_lint               = false
  schedule_cron          = "10 */12 * * 1,2,3,4,5"
  schedule_type          = "custom_cron"
  target_name            = "default"
  timeout_seconds        = 0
  triggers = {
    git_provider_webhook = false
    github_webhook       = false
    on_merge             = false
    schedule             = true
  }
  triggers_on_draft_pr = false
}

resource "dbtcloud_repository" "terraform_managed_resource_70437463660525" {
  git_clone_strategy        = "github_app"
  github_installation_id    = var.dbtcloud_repository_github_installation_id_267820
  project_id                = 70437463664450
  pull_request_url_template = "https://github.com/dbt-labs/sa-standard-shared-demo/compare/{{destination}}...{{source}}"
  remote_url                = "git://github.com/dbt-labs/sa-standard-shared-demo.git"
}

resource "dbtcloud_repository" "terraform_managed_resource_70437463660658" {
  git_clone_strategy        = "github_app"
  github_installation_id    = var.dbtcloud_repository_github_installation_id_56363999
  project_id                = 70437463664888
  pull_request_url_template = "https://github.com/johndamaro/job-sao-converter/compare/{{destination}}...{{source}}"
  remote_url                = "git://github.com/johndamaro/job-sao-converter.git"
}

# The variables defined for fields we couldn't retrieve

variable "dbtcloud_repository_github_installation_id_267820" {
  type        = number
  description = "The new GitHub installation ID for the existing installation ID 267820"
}

variable "dbtcloud_repository_github_installation_id_56363999" {
  type        = number
  description = "The new GitHub installation ID for the existing installation ID 56363999"
}

# Copy past the following lines in terraform.tfvars

# dbtcloud_repository_github_installation_id_267820 = ""
# dbtcloud_repository_github_installation_id_56363999 = ""


import {
  to = dbtcloud_project.terraform_managed_resource_70437463664450
  id = "70437463664450"
}

import {
  to = dbtcloud_project.terraform_managed_resource_70437463664888
  id = "70437463664888"
}

import {
  to = dbtcloud_environment.terraform_managed_resource_70437463668185
  id = "70437463664450:70437463668185"
}

import {
  to = dbtcloud_environment.terraform_managed_resource_70437463668476
  id = "70437463664888:70437463668476"
}

import {
  to = dbtcloud_environment.terraform_managed_resource_70437463668477
  id = "70437463664888:70437463668477"
}

import {
  to = dbtcloud_job.terraform_managed_resource_70437463758847
  id = "70437463758847"
}

import {
  to = dbtcloud_job.terraform_managed_resource_70437463758861
  id = "70437463758861"
}

import {
  to = dbtcloud_repository.terraform_managed_resource_70437463660525
  id = "70437463664450:70437463660525"
}

import {
  to = dbtcloud_repository.terraform_managed_resource_70437463660658
  id = "70437463664888:70437463660658"
}

