#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# dbt Platform → Terraform Setup Script
# Generates Terraform HCL from your PROD dbt Platform instance.
#
# Required env vars (export before running, or you will be prompted):
#   DBT_CLOUD_ACCOUNT_ID  - Your dbt Platform account ID
#   DBT_CLOUD_TOKEN       - Your dbt Platform service account token
#   DBT_CLOUD_HOST_URL    - Your dbt Platform API host
#                           e.g. https://cloud.getdbt.com/api        (US multi-tenant)
#                                https://emea.dbt.com/api            (EMEA multi-tenant)
#                                https://YOUR_ORG.getdbt.com/api     (single-tenant)
#
# Dependencies installed automatically via Homebrew:
#   - Terraform             (hashicorp/tap/terraform)
#   - dbtcloud-terraforming (dbt-labs/dbt-cli/dbtcloud-terraforming)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/generated.tf"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── 1. Check for Homebrew ─────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  error "Homebrew is required but not installed. Visit https://brew.sh to install it."
fi

# ── 2. Install Terraform ──────────────────────────────────────────────────────
if command -v terraform &>/dev/null; then
  success "Terraform already installed: $(terraform version -json | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])')"
else
  info "Installing Terraform..."
  brew tap hashicorp/tap
  brew install hashicorp/tap/terraform
  success "Terraform installed."
fi

# ── 3. Install dbtcloud-terraforming ──────────────────────────────────────────
if command -v dbtcloud-terraforming &>/dev/null; then
  success "dbtcloud-terraforming already installed: $(dbtcloud-terraforming version 2>/dev/null || echo 'unknown version')"
else
  info "Installing dbtcloud-terraforming..."
  brew install dbt-labs/dbt-cli/dbtcloud-terraforming
  success "dbtcloud-terraforming installed."
fi

# ── 4. Collect credentials ────────────────────────────────────────────────────
if [[ -z "${DBT_CLOUD_ACCOUNT_ID:-}" ]]; then
  read -rp "Enter your dbt Platform Account ID: " DBT_CLOUD_ACCOUNT_ID
  [[ -z "$DBT_CLOUD_ACCOUNT_ID" ]] && error "DBT_CLOUD_ACCOUNT_ID cannot be empty."
  export DBT_CLOUD_ACCOUNT_ID
fi

if [[ -z "${DBT_CLOUD_TOKEN:-}" ]]; then
  read -rsp "Enter your dbt Platform Service Token (input hidden): " DBT_CLOUD_TOKEN
  echo
  [[ -z "$DBT_CLOUD_TOKEN" ]] && error "DBT_CLOUD_TOKEN cannot be empty."
  export DBT_CLOUD_TOKEN
fi

if [[ -z "${DBT_CLOUD_HOST_URL:-}" ]]; then
  echo    "  Common values:"
  echo    "    https://cloud.getdbt.com/api       (US multi-tenant)"
  echo    "    https://emea.dbt.com/api           (EMEA multi-tenant)"
  echo    "    https://YOUR_ORG.getdbt.com/api    (single-tenant)"
  read -rp "Enter your dbt Platform Host URL: " DBT_CLOUD_HOST_URL
  [[ -z "$DBT_CLOUD_HOST_URL" ]] && error "DBT_CLOUD_HOST_URL cannot be empty."
  export DBT_CLOUD_HOST_URL
fi
info "Using host URL: $DBT_CLOUD_HOST_URL"

success "Credentials set for account ID: $DBT_CLOUD_ACCOUNT_ID"

# ── 5. Terraform init ─────────────────────────────────────────────────────────
info "Initialising Terraform..."
(cd "$SCRIPT_DIR" && terraform init -upgrade -input=false)
success "Terraform initialised."

# ── 6. Generate HCL ──────────────────────────────────────────────────────────
RESOURCE_TYPES=(
  dbtcloud_project
  dbtcloud_environment
  dbtcloud_job
  dbtcloud_repository
  dbtcloud_connection
  dbtcloud_notification
)

RESOURCE_LIST=$(IFS=,; echo "${RESOURCE_TYPES[*]}")

info "Generating Terraform configuration from PROD instance..."
info "Resources: $RESOURCE_LIST"

dbtcloud-terraforming genimport \
  --resource-types "$RESOURCE_LIST" \
  --terraform-install-path "$SCRIPT_DIR" \
  > "$OUTPUT_FILE"

# ── 7. Done ───────────────────────────────────────────────────────────────────
echo
success "HCL written to: $OUTPUT_FILE"
warn "Next steps:"
echo "  1. Review $OUTPUT_FILE and remove any resources you don't need"
echo "  2. Run 'terraform plan' to validate the config"
echo "  3. Commit terraform/ to version control (excluding any .tfvars with secrets)"
echo
