# SAO Converter

Stop managing model freshness inside your job definitions. Let your models own it.

## The Problem

If you're running dbt Platform today, your deployment cadence lives inside your jobs — a cron schedule here, a selector there. Every time you need to change how often a model rebuilds, you're back in the UI editing a job. That knowledge is invisible to the models themselves, invisible to code review, and invisible to anyone new to the project.

**SAO Converter** reads your existing PROD job configuration directly from Terraform and writes the appropriate `build_after` freshness config into your model-level YML files — so your models know exactly how often they should rebuild, right alongside their tests and documentation.

---

## What It Does

1. Snapshots your PROD dbt Platform environment into Terraform HCL (`terraform/generated.tf`)
2. Reads each PROD job's schedule and the models it targets
3. Translates the cron cadence into a `build_after` freshness config
4. Injects that config into your existing model YML files — skipping any model that doesn't already have a YML
5. Runs `dbtf parse` to confirm everything is valid before you commit

---

## Prerequisites

| Requirement | Notes |
|---|---|
| macOS with [Homebrew](https://brew.sh) | The setup script uses Homebrew to install Terraform and dbtcloud-terraforming automatically |
| [Terraform](https://developer.hashicorp.com/terraform/install) | Installed automatically by `setup.sh` via `hashicorp/tap` |
| [dbtcloud-terraforming](https://github.com/dbt-labs/dbtcloud-terraforming) | Installed automatically by `setup.sh` via `dbt-labs/dbt-cli` — this is what generates `generated.tf` from your live dbt Platform account |
| Python 3.11+ | Comes with macOS; `ruamel.yaml` and `python-hcl2` are the only runtime dependencies — install them with `pip install ruamel.yaml python-hcl2` if needed |
| [dbt Fusion (`dbtf`)](https://docs.getdbt.com/docs/dbt-versions/dbt-fusion) | Required — used mid-run to resolve model selectors (`dbtf ls`) and validate YML at the end (`dbtf parse`). Must be on your `PATH`. |
| dbt Platform account ID | Found in your dbt Platform URL or Account Settings |
| dbt Platform service token | Create one at **Account Settings → Service Tokens** — Read access is sufficient |
| dbt Platform host URL | Required — see common values in Step 2 below |

---

## Setup & Usage

### Step 1 — Clone the repo

```bash
git clone https://github.com/johndamaro/sao-converter.git
cd sao-converter
```

### Step 2 — Set your credentials

Export your dbt Platform credentials before running the setup script. These are never written to disk.

```bash
export DBT_CLOUD_ACCOUNT_ID=your_account_id
export DBT_CLOUD_TOKEN=your_service_token
export DBT_CLOUD_HOST_URL=your_host_url
```

> **Where to find these:**
> - **Account ID** — dbt Platform → Account Settings → the ID in the URL
> - **Service Token** — dbt Platform → Account Settings → Service Tokens → create a new Read token
> - **Host URL** — pick the one that matches your deployment:
>
>   | Deployment | Host URL |
>   |---|---|
>   | US multi-tenant | `https://cloud.getdbt.com/api` |
>   | EMEA multi-tenant | `https://emea.dbt.com/api` |
>   | Cell-based (prefixed) | `https://PREFIX.us1.dbt.com/api` — e.g. `yz056.us1.dbt.com` |
>   | Single-tenant | `https://YOUR_ORG.getdbt.com/api` |

If you skip these exports, `setup.sh` will prompt you for each one interactively (token input is hidden).

### Step 3 — Generate your Terraform snapshot

This installs Terraform and `dbtcloud-terraforming` (if not already present), then pulls a snapshot of your PROD environment into `terraform/generated.tf`.

```bash
cd terraform/
./setup.sh
cd ..
```

### Step 4 — Run the converter

Point the script at your own dbt project using `--dbt-project-dir`. This is the repo where your model YML files live — not the `sao-converter` directory itself.

```bash
python3 sao_converter.py --dbt-project-dir /path/to/your/dbt/project
```

If your `generated.tf` contains multiple dbt Platform projects, you'll be prompted to pick one. To skip the prompt, pass the project name directly:

```bash
python3 sao_converter.py \
  --dbt-project-dir /path/to/your/dbt/project \
  --project-name "My Project"
```

> **Tip:** After running `pip install -e .`, you can use `sao-converter` as a shorthand instead of `python3 sao_converter.py`.

**Flags:**

| Flag | Required | Description |
|---|---|---|
| `--dbt-project-dir` | ✅ Yes | Path to your dbt project directory (the one containing `dbt_project.yml`) |
| `--project-name` | No | dbt Platform project name to target — prompted if multiple are found |
| `--generated-tf` | No | Path to `generated.tf` if it lives somewhere other than `terraform/generated.tf` |

### Step 5 — Review and commit

Check the updated YML files to make sure the `build_after` values look right for your team, then commit:

```bash
git diff
git add jaffle_shop/models/
git commit -m "Add SAO build_after freshness configs from PROD job schedules"
```

---

## What Gets Written

For each model with an existing YML file, the converter adds a `config` block immediately after the model `name`:

```yaml
models:
  - name: stg_orders
    config:
      freshness:
        build_after:
          count: 6
          period: hour
          updates_on: all
    description: ...
```

- `count` and `period` are derived from the job's cron schedule
- `updates_on: all` means the model only rebuilds when all upstream sources have new data — the most cost-efficient default
- Models without a YML file are left untouched
- Running the script more than once is safe — models that already have a freshness config are skipped

---

## Development

To run the unit tests, install the package in editable mode with dev dependencies:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Feedback

This tool is a work in progress and we'd love to hear how it's working for you.

- **Something broken?** Open an issue at [github.com/johndamaro/sao-converter/issues](https://github.com/johndamaro/sao-converter/issues)
- **Works great?** Leave a ⭐ on the repo — it helps others find it
- **Have ideas?** PRs are very welcome, especially for additional selector patterns or adapter-specific freshness handling
