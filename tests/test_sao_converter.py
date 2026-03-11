"""
Unit tests for sao_converter.py

Run with:
    pytest tests/ -v
"""
import textwrap
from pathlib import Path

import pytest

from sao_converter import (
    cron_to_build_after,
    get_prod_env_ids,
    get_prod_jobs,
    get_project_id,
    inject_build_after,
    steps_to_dirs,
)


# ── cron_to_build_after ───────────────────────────────────────────────────────

class TestCronToBuildAfter:
    def test_every_n_hours(self):
        assert cron_to_build_after("0 */6 * * *") == {"count": 6, "period": "hour"}

    def test_every_2_hours(self):
        assert cron_to_build_after("0 */2 * * *") == {"count": 2, "period": "hour"}

    def test_every_1_hour_via_star(self):
        assert cron_to_build_after("0 * * * *") == {"count": 1, "period": "hour"}

    def test_comma_hours_even_gap(self):
        # 0, 6, 12, 18 → gaps are all 6 → count = 6
        assert cron_to_build_after("0 0,6,12,18 * * *") == {"count": 6, "period": "hour"}

    def test_comma_hours_uses_minimum_gap(self):
        # 0, 4, 12 → gaps are 4, 8 → minimum is 4
        assert cron_to_build_after("0 0,4,12 * * *") == {"count": 4, "period": "hour"}

    def test_single_hour_is_daily(self):
        assert cron_to_build_after("0 2 * * *") == {"count": 24, "period": "hour"}

    def test_bad_cron_falls_back_to_daily(self):
        assert cron_to_build_after("bad cron") == {"count": 24, "period": "hour"}

    def test_empty_string_falls_back_to_daily(self):
        assert cron_to_build_after("") == {"count": 24, "period": "hour"}

    def test_too_few_parts_falls_back(self):
        assert cron_to_build_after("0 * * *") == {"count": 24, "period": "hour"}


# ── steps_to_dirs ─────────────────────────────────────────────────────────────

class TestStepsToDirs:
    def test_build_with_wildcard_selector(self):
        assert steps_to_dirs(["dbt build -s staging.*"]) == ["staging"]

    def test_run_with_model_selector(self):
        assert steps_to_dirs(["dbt run -s marts.orders"]) == ["marts"]

    def test_long_select_flag(self):
        assert steps_to_dirs(["dbt build --select staging.*"]) == ["staging"]

    def test_seed_is_ignored(self):
        assert steps_to_dirs(["dbt seed"]) == []

    def test_test_is_ignored(self):
        assert steps_to_dirs(["dbt test"]) == []

    def test_source_freshness_is_ignored(self):
        assert steps_to_dirs(["dbt source freshness"]) == []

    def test_tag_selector_is_ignored(self):
        assert steps_to_dirs(["dbt build -s tag:daily"]) == []

    def test_source_selector_is_ignored(self):
        assert steps_to_dirs(["dbt build -s source:mydb"]) == []

    def test_no_selector_flag(self):
        assert steps_to_dirs(["dbt build"]) == []

    def test_deduplication_same_dir(self):
        steps = [
            "dbt run -s staging.stg_orders",
            "dbt run -s staging.stg_customers",
        ]
        assert steps_to_dirs(steps) == ["staging"]

    def test_multiple_steps_different_dirs(self):
        steps = [
            "dbt build -s staging.*",
            "dbt build -s marts.*",
        ]
        result = steps_to_dirs(steps)
        assert set(result) == {"staging", "marts"}

    def test_mixed_skipped_and_valid_steps(self):
        steps = [
            "dbt seed",
            "dbt build -s staging.*",
            "dbt test",
            "dbt build -s marts.*",
        ]
        result = steps_to_dirs(steps)
        assert set(result) == {"staging", "marts"}


# ── Shared fixture blocks for get_* tests ─────────────────────────────────────

SAMPLE_BLOCKS = [
    {
        "resource_type": "dbtcloud_project",
        "resource_name": "project_123",
        "fields": {"name": "My Project"},
    },
    {
        "resource_type": "dbtcloud_project",
        "resource_name": "project_456",
        "fields": {"name": "Other Project"},
    },
    {
        "resource_type": "dbtcloud_environment",
        "resource_name": "environment_10",
        "fields": {
            "project_id": 123,
            "deployment_type": "production",
            "name": "PROD",
        },
    },
    {
        "resource_type": "dbtcloud_environment",
        "resource_name": "environment_11",
        "fields": {
            "project_id": 123,
            "deployment_type": "development",
            "name": "DEV",
        },
    },
    {
        "resource_type": "dbtcloud_environment",
        "resource_name": "environment_20",
        "fields": {
            "project_id": 456,
            "deployment_type": "production",
            "name": "PROD (Other)",
        },
    },
    {
        "resource_type": "dbtcloud_job",
        "resource_name": "job_1001",
        "fields": {
            "name": "Nightly Build",
            "environment_id": 10,
            "schedule_cron": "0 */6 * * *",
            "execute_steps": ["dbt build -s staging.*"],
            "git_provider_webhook": False,
            "github_webhook": False,
            "on_merge": False,
        },
    },
    {
        "resource_type": "dbtcloud_job",
        "resource_name": "job_1002",
        "fields": {
            "name": "CI Job",
            "environment_id": 10,
            "schedule_cron": "0 * * * *",
            "execute_steps": ["dbt build -s marts.*"],
            "git_provider_webhook": True,
            "github_webhook": False,
            "on_merge": False,
        },
    },
]


# ── get_project_id ────────────────────────────────────────────────────────────

class TestGetProjectId:
    def test_finds_first_project(self):
        assert get_project_id(SAMPLE_BLOCKS, "My Project") == 123

    def test_finds_second_project(self):
        assert get_project_id(SAMPLE_BLOCKS, "Other Project") == 456

    def test_returns_none_for_missing_project(self):
        assert get_project_id(SAMPLE_BLOCKS, "Nonexistent") is None

    def test_empty_blocks_returns_none(self):
        assert get_project_id([], "My Project") is None


# ── get_prod_env_ids ──────────────────────────────────────────────────────────

class TestGetProdEnvIds:
    def test_finds_prod_env_for_project(self):
        assert get_prod_env_ids(SAMPLE_BLOCKS, 123) == {10}

    def test_finds_prod_env_for_other_project(self):
        assert get_prod_env_ids(SAMPLE_BLOCKS, 456) == {20}

    def test_dev_env_excluded(self):
        ids = get_prod_env_ids(SAMPLE_BLOCKS, 123)
        assert 11 not in ids  # environment_11 is development

    def test_no_matching_project_returns_empty_set(self):
        assert get_prod_env_ids(SAMPLE_BLOCKS, 999) == set()


# ── get_prod_jobs ─────────────────────────────────────────────────────────────

class TestGetProdJobs:
    def test_returns_scheduled_jobs_only(self):
        jobs = get_prod_jobs(SAMPLE_BLOCKS, {10})
        assert len(jobs) == 1
        assert jobs[0]["name"] == "Nightly Build"

    def test_excludes_git_provider_webhook_jobs(self):
        jobs = get_prod_jobs(SAMPLE_BLOCKS, {10})
        names = [j["name"] for j in jobs]
        assert "CI Job" not in names

    def test_no_matching_env_returns_empty_list(self):
        assert get_prod_jobs(SAMPLE_BLOCKS, {999}) == []

    def test_excludes_on_merge_jobs(self):
        blocks = [
            {
                "resource_type": "dbtcloud_job",
                "resource_name": "job_2000",
                "fields": {
                    "name": "Merge Job",
                    "environment_id": 10,
                    "schedule_cron": "0 * * * *",
                    "execute_steps": ["dbt build"],
                    "git_provider_webhook": False,
                    "github_webhook": False,
                    "on_merge": True,
                },
            }
        ]
        assert get_prod_jobs(blocks, {10}) == []

    def test_excludes_github_webhook_jobs(self):
        blocks = [
            {
                "resource_type": "dbtcloud_job",
                "resource_name": "job_3000",
                "fields": {
                    "name": "GitHub Webhook Job",
                    "environment_id": 10,
                    "schedule_cron": "0 * * * *",
                    "execute_steps": ["dbt build"],
                    "git_provider_webhook": False,
                    "github_webhook": True,
                    "on_merge": False,
                },
            }
        ]
        assert get_prod_jobs(blocks, {10}) == []


# ── inject_build_after ────────────────────────────────────────────────────────

class TestInjectBuildAfter:
    def test_injects_into_model_without_config(self, tmp_path):
        yml = tmp_path / "stg_orders.yml"
        yml.write_text(textwrap.dedent("""\
            models:
            - name: stg_orders
              description: Order staging model.
              columns:
              - name: order_id
                description: PK.
        """))
        result = inject_build_after(yml, {"count": 6, "period": "hour"})
        assert result is True
        content = yml.read_text()
        assert "build_after" in content
        assert "count: 6" in content
        assert "period: hour" in content
        assert "updates_on: all" in content

    def test_skips_file_without_models_key(self, tmp_path):
        yml = tmp_path / "__sources.yml"
        yml.write_text(textwrap.dedent("""\
            version: 2
            sources:
            - name: ecom
              tables:
              - name: raw_orders
        """))
        result = inject_build_after(yml, {"count": 6, "period": "hour"})
        assert result is False
        assert "build_after" not in yml.read_text()

    def test_skips_model_already_having_freshness(self, tmp_path):
        yml = tmp_path / "stg_customers.yml"
        yml.write_text(textwrap.dedent("""\
            models:
            - name: stg_customers
              config:
                freshness:
                  build_after:
                    count: 12
                    period: hour
                    updates_on: all
              description: Already configured.
        """))
        result = inject_build_after(yml, {"count": 6, "period": "hour"})
        assert result is False
        # Original count should be preserved
        assert "count: 12" in yml.read_text()

    def test_config_key_appears_immediately_after_name(self, tmp_path):
        yml = tmp_path / "stg_products.yml"
        yml.write_text(textwrap.dedent("""\
            models:
            - name: stg_products
              description: Products.
        """))
        inject_build_after(yml, {"count": 24, "period": "hour"})
        lines = yml.read_text().splitlines()
        name_idx   = next(i for i, l in enumerate(lines) if "name: stg_products" in l)
        config_idx = next(i for i, l in enumerate(lines) if "config:" in l)
        assert config_idx == name_idx + 1

    def test_merges_into_existing_config_block(self, tmp_path):
        yml = tmp_path / "orders.yml"
        yml.write_text(textwrap.dedent("""\
            models:
            - name: orders
              config:
                tags:
                - daily
              description: Orders mart.
        """))
        result = inject_build_after(yml, {"count": 12, "period": "hour"})
        assert result is True
        content = yml.read_text()
        assert "build_after" in content
        assert "tags" in content  # existing config key should survive

    def test_empty_file_returns_false(self, tmp_path):
        yml = tmp_path / "empty.yml"
        yml.write_text("")
        assert inject_build_after(yml, {"count": 6, "period": "hour"}) is False

    def test_updates_on_parameter_respected(self, tmp_path):
        yml = tmp_path / "stg_locations.yml"
        yml.write_text(textwrap.dedent("""\
            models:
            - name: stg_locations
              description: Locations.
        """))
        inject_build_after(yml, {"count": 6, "period": "hour"}, updates_on="any")
        assert "updates_on: any" in yml.read_text()
