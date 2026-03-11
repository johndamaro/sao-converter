#!/usr/bin/env python3
"""
sao_converter.py

Reads terraform/generated.tf and converts PROD job schedules into
model-level build_after freshness configs in existing model YML files,
then validates with `dbt parse`.

Steps:
  1. Read terraform/generated.tf
  2. Identify PROD environment(s) for the SAO Job Converter project
  3. Find all jobs running in those environments; extract steps + cron
  4. Map dbt selectors (e.g. staging.*) to model directories
  5. Inject freshness.build_after into existing model YML files only
  6. Run dbt parse to validate
"""

import json
import re
import sys
import argparse
import shutil
import subprocess
from pathlib import Path

import hcl2
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

# ── Paths ─────────────────────────────────────────────────────────────────────
# TOOL_ROOT is where this script lives (the job-sao-converter repo).
# The dbt project being modified lives elsewhere — passed in via --dbt-project-dir.
TOOL_ROOT    = Path(__file__).parent
GENERATED_TF = TOOL_ROOT / "terraform" / "generated.tf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert PROD dbt Platform job schedules to model-level build_after configs.\n\n"
            "This tool reads terraform/generated.tf from the job-sao-converter directory\n"
            "and writes freshness configs into YML files in YOUR dbt project."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dbt-project-dir",
        type=Path,
        required=True,
        help="Path to YOUR dbt project directory (the one containing dbt_project.yml). "
             "Example: /Users/you/repos/my-dbt-project",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="dbt Platform project name to target (default: auto-detected from generated.tf — "
             "prompts if multiple projects are found).",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=None,
        help="Path to the models directory (default: <dbt-project-dir>/models).",
    )
    parser.add_argument(
        "--generated-tf",
        type=Path,
        default=GENERATED_TF,
        help=f"Path to generated.tf (default: {GENERATED_TF}).",
    )
    return parser.parse_args()

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE   = "\033[0;34m"
RED    = "\033[0;31m"
NC     = "\033[0m"

def info(msg):    print(f"{BLUE}[INFO]{NC}  {msg}")
def ok(msg):      print(f"{GREEN}[OK]{NC}    {msg}")
def warn(msg):    print(f"{YELLOW}[WARN]{NC}  {msg}")
def error(msg):   print(f"{RED}[ERROR]{NC} {msg}", file=sys.stderr)


# ── Step 1: TF Parser ─────────────────────────────────────────────────────────
def _extract_blocks(parsed: dict) -> list[dict]:
    """
    Extract resource blocks from a parsed python-hcl2 dict.

    python-hcl2 returns `resource` as a list of single-key dicts
    (one per block), e.g.:
        [{"dbtcloud_project": {"project_123": {"name": "..."}}}, ...]

    Returns a flat list of dicts: {resource_type, resource_name, fields}.
    """
    blocks = []
    for resource_block in parsed.get("resource", []):
        for resource_type, names in resource_block.items():
            for resource_name, fields in names.items():
                blocks.append(
                    {
                        "resource_type": resource_type,
                        "resource_name": resource_name,
                        "fields":        fields,
                    }
                )
    return blocks


def parse_tf_blocks(tf_path: Path) -> list[dict]:
    """Convenience wrapper: load an HCL file and return its resource blocks."""
    with open(tf_path) as f:
        return _extract_blocks(hcl2.load(f))


# ── Step 2: Find the SAO project ID ──────────────────────────────────────────
def get_project_id(blocks: list[dict], project_name: str) -> int | None:
    for block in blocks:
        if block["resource_type"] == "dbtcloud_project":
            if block["fields"].get("name") == project_name:
                m = re.search(r"(\d+)$", block["resource_name"])
                if m:
                    return int(m.group(1))
    return None


# ── Step 3: Find production environment IDs ───────────────────────────────────
def get_prod_env_ids(blocks: list[dict], project_id: int) -> set[int]:
    prod_ids = set()
    for block in blocks:
        if block["resource_type"] != "dbtcloud_environment":
            continue
        f = block["fields"]
        if (
            f.get("deployment_type") == "production"
            and f.get("project_id") == project_id
        ):
            m = re.search(r"(\d+)$", block["resource_name"])
            if m:
                prod_ids.add(int(m.group(1)))
    return prod_ids


# ── Step 4: Extract PROD jobs ─────────────────────────────────────────────────
def get_prod_jobs(blocks: list[dict], prod_env_ids: set[int]) -> list[dict]:
    """
    Return scheduled PROD jobs only — excludes any job triggered by:
      - git_provider_webhook
      - github_webhook
      - on_merge
    These are event-driven and have no cron schedule to derive build_after from.
    """
    jobs = []
    for b in blocks:
        if b["resource_type"] != "dbtcloud_job":
            continue
        f = b["fields"]
        if f.get("environment_id") not in prod_env_ids:
            continue
        if f.get("git_provider_webhook") or f.get("github_webhook") or f.get("on_merge"):
            warn(f"  Skipping event-driven job '{f.get('name', 'unnamed')}' "
                 f"(git_provider_webhook={f.get('git_provider_webhook')}, "
                 f"github_webhook={f.get('github_webhook')}, "
                 f"on_merge={f.get('on_merge')})")
            continue
        jobs.append(f)
    return jobs


# ── Cron → build_after ────────────────────────────────────────────────────────
def cron_to_build_after(cron: str) -> dict:
    """
    Derive a build_after interval from a cron expression.

    Supported patterns:
      */N  in the hour field  → every N hours
      N,M  in the hour field  → smallest interval between hours
      *    in the hour field  → every hour
      single digit            → daily (every 24 hours)
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        return {"count": 24, "period": "hour"}

    _minute, hour, *_ = parts

    # */N  (every N hours)
    m = re.fullmatch(r"\*/(\d+)", hour)
    if m:
        return {"count": int(m.group(1)), "period": "hour"}

    # * (every hour)
    if hour == "*":
        return {"count": 1, "period": "hour"}

    # Comma-separated hours → use the smallest gap
    if "," in hour:
        hours = sorted(int(h) for h in hour.split(",") if h.isdigit())
        if len(hours) >= 2:
            gaps  = [hours[i + 1] - hours[i] for i in range(len(hours) - 1)]
            return {"count": min(gaps), "period": "hour"}

    # Single hour value → once per day
    return {"count": 24, "period": "hour"}


# ── dbt selector → model directories ─────────────────────────────────────────
def steps_to_dirs(steps: list[str]) -> list[str]:
    """
    Parse execute_steps and return unique model directory names.

    Recognised selectors:
      dbt build/run -s folder.*   → [folder]
      dbt build/run -s folder.model_name → [folder]

    Skipped:
      dbt seed / dbt test / dbt source freshness / tag: / source:
    """
    dirs = []
    selector_re = re.compile(r"(?:-s|--select)\s+(\S+)")

    for step in steps:
        # Skip non-model commands
        if re.match(r"dbt\s+(seed|test|source)", step.strip()):
            continue

        m = selector_re.search(step)
        if not m:
            continue

        pattern = m.group(1)

        # tag: / source: — not directory-based
        if pattern.startswith(("tag:", "source:")):
            continue

        # folder.*  or  folder.model
        folder_m = re.match(r"^([a-zA-Z_]+)\.", pattern)
        if folder_m:
            folder = folder_m.group(1)
            if folder not in dirs:
                dirs.append(folder)

    return dirs


# ── Step 5: Inject build_after into YML ───────────────────────────────────────
def inject_build_after(
    yml_path: Path,
    build_after: dict,
    updates_on: str = "all",
) -> bool:
    """
    Add freshness.build_after config to every model entry in a YML file.

    - Skips files with no `models:` key (e.g. __sources.yml).
    - Skips models that already have a freshness config.
    - Inserts `config:` immediately after the `name:` key to keep YML readable.
    - Returns True if the file was modified.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120

    with open(yml_path) as fh:
        data = yaml.load(fh)

    if not data or "models" not in data:
        return False

    modified = False

    for model in data["models"]:
        # Already configured — skip
        if "freshness" in model.get("config", {}):
            warn(f"    {model['name']}: already has freshness config — skipping.")
            continue

        # Build the nested config map
        ba_map = CommentedMap()
        ba_map["count"]      = build_after["count"]
        ba_map["period"]     = build_after["period"]
        ba_map["updates_on"] = updates_on

        fresh_map  = CommentedMap({"build_after": ba_map})
        config_map = CommentedMap({"freshness": fresh_map})

        if "config" in model:
            model["config"]["freshness"] = fresh_map
        else:
            # Rebuild the model map so `config` sits right after `name`
            reordered = CommentedMap()
            for key, val in model.items():
                reordered[key] = val
                if key == "name":
                    reordered["config"] = config_map
            model.clear()
            model.update(reordered)

        modified = True

    if modified:
        with open(yml_path, "w") as fh:
            yaml.dump(data, fh)

    return modified


# ── Step 6: dbt parse ─────────────────────────────────────────────────────────
def resolve_dbtf() -> list[str]:
    """
    Resolve the `dbtf` command to an actual executable path.

    `dbtf` is often a shell alias rather than a standalone binary, so
    subprocess can't find it directly. We try (in order):
      1. A binary named `dbtf` already on PATH
      2. The path that the shell alias points to (via `type -a dbtf`)
      3. A known common install location (~/.local/bin/dbt)
    """
    # 1. Direct binary
    if shutil.which("dbtf"):
        return ["dbtf"]

    # 2. Ask the shell to resolve the alias
    for shell in ["/bin/zsh", "/bin/bash"]:
        if not Path(shell).exists():
            continue
        try:
            r = subprocess.run(
                [shell, "-ic", "type -a dbtf"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                # "dbtf is /path/to/dbt"  or  "dbtf is aliased to /path/to/dbt"
                m = re.search(r"(/[^\s]+dbt[^\s]*)", line)
                if m:
                    candidate = Path(m.group(1))
                    if candidate.exists():
                        return [str(candidate)]
        except Exception:
            pass

    # 3. Common fallback location
    fallback = Path.home() / ".local" / "bin" / "dbt"
    if fallback.exists():
        warn(f"dbtf not found as binary; falling back to {fallback}")
        return [str(fallback)]

    # Give up — will fail with a clear FileNotFoundError
    return ["dbtf"]


def run_dbt_parse(dbt_project_dir: Path) -> bool:
    info("Running dbtf parse to validate YML files...")
    cmd = resolve_dbtf() + ["parse"]
    info(f"Resolved command: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=dbt_project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        ok("dbtf parse succeeded — all YML files are valid.")
    else:
        error("dbtf parse failed. Output below:")
        print(result.stdout)
        print(result.stderr)
    return result.returncode == 0


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # ── Resolve paths ──────────────────────────────────────────────────────────
    generated_tf    = args.generated_tf
    dbt_project_dir = args.dbt_project_dir.resolve()
    models_dir      = (args.models_dir or dbt_project_dir / "models").resolve()

    if not dbt_project_dir.exists():
        error(f"--dbt-project-dir not found: {dbt_project_dir}")
        sys.exit(1)
    if not (dbt_project_dir / "dbt_project.yml").exists():
        error(f"No dbt_project.yml found in {dbt_project_dir}. "
              "Make sure --dbt-project-dir points to the root of your dbt project.")
        sys.exit(1)
    if not models_dir.exists():
        error(f"Models directory not found: {models_dir}. "
              "Pass --models-dir explicitly if your project uses a non-standard layout.")
        sys.exit(1)

    # ── 1. Read & parse generated.tf → JSON + blocks ──────────────────────────
    print(f"\n{'─'*60}")
    info(f"Reading {generated_tf}")
    with open(generated_tf) as f:
        tf_parsed = hcl2.load(f)

    generated_json = generated_tf.with_suffix(".json")
    generated_json.write_text(json.dumps(tf_parsed, indent=2))
    ok(f"Written JSON: {generated_json}")

    blocks = _extract_blocks(tf_parsed)
    ok(f"Parsed {len(blocks)} resource blocks.")

    # ── 2. Locate the target project ──────────────────────────────────────────
    print(f"\n{'─'*60}")
    if args.project_name:
        project_name = args.project_name
        info(f"Looking for project: '{project_name}'")
        project_id = get_project_id(blocks, project_name)
        if not project_id:
            error(f"Could not find project '{project_name}' in generated.tf. Aborting.")
            sys.exit(1)
    else:
        # Auto-detect: list all projects and let the user pick if there's more than one
        project_blocks = [b for b in blocks if b["resource_type"] == "dbtcloud_project"]
        if not project_blocks:
            error("No dbtcloud_project resources found in generated.tf. Aborting.")
            sys.exit(1)
        if len(project_blocks) == 1:
            project_name = project_blocks[0]["fields"].get("name", "unknown")
            project_id   = int(re.search(r"(\d+)$", project_blocks[0]["resource_name"]).group(1))
            info(f"Auto-detected project: '{project_name}' (ID: {project_id})")
        else:
            print("\nMultiple projects found in generated.tf. Pick one:")
            for i, b in enumerate(project_blocks):
                pid  = re.search(r"(\d+)$", b["resource_name"]).group(1)
                name = b["fields"].get("name", "unknown")
                print(f"  [{i + 1}] {name} (ID: {pid})")
            choice = input("\nEnter number: ").strip()
            chosen       = project_blocks[int(choice) - 1]
            project_name = chosen["fields"].get("name", "unknown")
            project_id   = int(re.search(r"(\d+)$", chosen["resource_name"]).group(1))

    ok(f"Project: '{project_name}' (ID: {project_id})")
    info(f"dbt project dir : {dbt_project_dir}")
    info(f"Models dir      : {models_dir}")

    # ── 3. Find production environments ───────────────────────────────────────
    prod_env_ids = get_prod_env_ids(blocks, project_id)
    if not prod_env_ids:
        error("No production environments found. Aborting.")
        sys.exit(1)
    ok(f"Production environment ID(s): {prod_env_ids}")

    # ── 4. Extract PROD jobs ───────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    info("Extracting PROD jobs...")
    prod_jobs = get_prod_jobs(blocks, prod_env_ids)
    if not prod_jobs:
        error("No PROD jobs found. Aborting.")
        sys.exit(1)
    ok(f"Found {len(prod_jobs)} PROD job(s).")

    job_mappings = []
    for job in prod_jobs:
        name        = job.get("name", "unnamed")
        cron        = job.get("schedule_cron", "")
        steps       = job.get("execute_steps", [])
        build_after = cron_to_build_after(cron)
        dirs        = steps_to_dirs(steps)

        print()
        info(f"Job: '{name}'")
        print(f"         Cron     : {cron}")
        print(f"         Steps    : {steps}")
        print(f"         Dirs     : {dirs}")
        print(f"         build_after → every {build_after['count']} {build_after['period']}(s), updates_on: all")

        if dirs:
            job_mappings.append({"name": name, "dirs": dirs, "build_after": build_after})

    # ── 5. Inject build_after into model YMLs ─────────────────────────────────
    print(f"\n{'─'*60}")
    info("Injecting freshness.build_after into model YML files...")
    total_updated = 0

    for mapping in job_mappings:
        print()
        info(f"Job: '{mapping['name']}'")
        for folder in mapping["dirs"]:
            folder_path = models_dir / folder
            if not folder_path.exists():
                warn(f"  Directory models/{folder}/ not found — skipping.")
                continue

            yml_files = [
                p for p in folder_path.glob("*.yml")
                if not p.name.startswith("__")
            ]

            if not yml_files:
                warn(f"  No model YML files in models/{folder}/ — skipping.")
                continue

            for yml_path in sorted(yml_files):
                label   = yml_path.relative_to(dbt_project_dir)
                updated = inject_build_after(yml_path, mapping["build_after"])
                if updated:
                    ok(f"  Updated: {label}")
                    total_updated += 1
                else:
                    info(f"  No changes: {label}")

    print()
    ok(f"Done — {total_updated} file(s) updated.")

    # ── 6. dbt parse ──────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    success = run_dbt_parse(dbt_project_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
