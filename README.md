# CSW POV Template

Reusable toolkit for **Cisco Secure Workload (CSW / Tetration)** Proof-of-Value engagements.
Clone this repository at the start of every new POV and follow the quick-start guide below.

The toolkit provides **14 Python scripts** that cover the full POV lifecycle:

> **API validation → data collection → snapshot comparison → HTML reporting → vulnerability assessment**

- No external dependencies (pure Python 3.8+ standard library)
- HMAC-SHA256 authenticated API client
- Self-contained, shareable HTML reports (no external CSS/JS)
- Works with both SaaS CSW clusters and on-prem Tetration appliances

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Configuration](#configuration)
4. [Script Reference](#script-reference)
5. [Typical POV Workflow](#typical-pov-workflow)
6. [Project Structure](#project-structure)
7. [Customisation for Your POV](#customisation-for-your-pov)
8. [Troubleshooting](#troubleshooting)
9. [Security Notes](#security-notes)

---

## Quick Start

```bash
# 1. Clone the template for a specific customer
git clone https://github.com/chandrapati/CSW_POV_Template.git MyCustomer_CSW_POV
cd MyCustomer_CSW_POV

# 2. (Recommended) isolated Python environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Configure credentials
cp .env.example .env
# Open .env in your editor and fill in CSW_API_URL / KEY / SECRET

# 4. Validate API connectivity and capabilities
python3 api_test_suite.py --output reports/api-capabilities.md

# 5. Take a baseline cluster snapshot
python3 cluster_snapshot.py

# 6. Generate the HTML readout report from that snapshot
python3 generate_html_report.py

# 7. Open the report
open reports/readout-$(date +%Y-%m-%d).html      # macOS
xdg-open reports/readout-$(date +%Y-%m-%d).html  # Linux
```

---

## Prerequisites

| Item | Version / Notes |
|---|---|
| Python | 3.8 or newer |
| pip packages | **None** — uses only stdlib (`urllib`, `json`, `csv`, `hashlib`, `hmac`, `argparse`) |
| Network access | Outbound HTTPS to the CSW cluster (typically `*.tetrationcloud.com`) |
| CSW API key | Generated in the CSW UI with appropriate capabilities (see below) |

### API Key Capabilities

In the CSW UI go to **Settings → API Keys → Create API Key** and enable:

| Capability | Required For |
|---|---|
| `sensor_management` | Agents/workloads (`cluster_snapshot`, `generate_vuln_report`) |
| `flow_inventory_query` | Flow search and inventory (`download_flows`, `generate_flow_analysis`, `query_long_lived_processes`) |
| `app_policy_management` | Workspaces, policies, conversations (`download_policies`, `download_conversations`, `generate_combined_report`) |
| `user_role_scope_management` | Scope / user lookups (most scripts) |
| `external_integration` | Forensics + connector data (`download_forensics`, `generate_forensics_report`) |

> **Tip:** Enable all five for a POV and restrict later once you know what you actually use.

---

## Configuration

### `.env` file

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `CSW_API_URL` | yes | Cluster base URL, e.g. `https://customer.tetrationcloud.com` (no trailing `/openapi`) |
| `CSW_API_KEY` | yes | API key identifier (hex string) |
| `CSW_API_SECRET` | yes | Paired secret (hex string) |
| `CSW_VERIFY_SSL` | no | `true` by default. Set to `false` for self-signed clusters or corporate TLS inspection |
| `CSW_ROOT_SCOPE` | no | Root scope name. Most scripts auto-detect, set it to short-circuit the lookup |

`.env` is git-ignored — it is never committed.

---

## Script Reference

All scripts are invoked directly via `python3 <script>.py [options]` and print `--help` when called with `-h`.

### Core client (not run directly)

| Script | Purpose |
|---|---|
| `csw_api.py` | HMAC-SHA256 authenticated API client. Loads `.env`, signs every request, handles pagination. All other scripts `import csw_api` from this module. |

Direct CLI usage example (for ad-hoc API debugging):

```bash
python3 csw_api.py GET /openapi/v1/app_scopes
python3 csw_api.py GET /openapi/v1/sensors --limit 50 --offset 0
python3 csw_api.py POST /openapi/v1/inventory/search '{"filter":{"type":"eq","field":"os","value":"windows"}}'
```

### 1. `api_test_suite.py` — validate API access

Probes every major API endpoint and writes a Markdown compatibility matrix.

```bash
python3 api_test_suite.py                                   # console output
python3 api_test_suite.py --output reports/api-capabilities.md
python3 api_test_suite.py --quick                           # skip slow tests
python3 api_test_suite.py --category agents flow vulnerabilities
```

**Output:** `reports/api-capabilities.md` — checklist of every endpoint with status ✅ / ❌ and hints for missing capabilities.

### 2. `cluster_snapshot.py` — full cluster state capture

Captures agents, scopes, workspaces, policies, inventory, and recent flows → JSON snapshot + Markdown summary.

```bash
python3 cluster_snapshot.py                      # full snapshot
python3 cluster_snapshot.py --skip-flows         # skip flowsearch if capability is missing
python3 cluster_snapshot.py --json-only          # JSON only, no Markdown
python3 cluster_snapshot.py --output-dir /tmp/   # alternate directory
```

**Outputs:**
- `snapshots/snapshot-<YYYY-MM-DD>.json` — full machine-readable snapshot
- `snapshots/snapshot-<YYYY-MM-DD>.md` — human-readable summary

### 3. `generate_html_report.py` — single-snapshot HTML readout

Turns a snapshot JSON into a polished customer-facing HTML readout with tables, charts, and risky-port heatmap.

```bash
python3 generate_html_report.py                                          # newest snapshot
python3 generate_html_report.py --snapshot snapshots/snapshot-2026-04-07.json
python3 generate_html_report.py --out reports/kickoff-readout.html
```

**Output:** `reports/readout-<YYYY-MM-DD>.html` (self-contained, no external assets).

### 4. `cluster_delta.py` — compare two snapshots

Markdown change log between a baseline and a current snapshot (agents added/removed, new scopes, policy changes, inventory drift).

```bash
python3 cluster_delta.py --latest                                            # auto-pick two newest
python3 cluster_delta.py snapshots/baseline.json snapshots/current.json
python3 cluster_delta.py --latest --output reports/weekly-delta.md
```

### 5. `generate_combined_report.py` — baseline vs current HTML

Combines the full readout + delta into a single HTML report.

```bash
python3 generate_combined_report.py --latest
python3 generate_combined_report.py --baseline snapshots/week1.json --current snapshots/week4.json
python3 generate_combined_report.py --latest --out reports/monthly-review.html
```

### 6. `download_conversations.py` — workspace conversations

Policy-matched conversations for a workspace (ADM output). Paginates through all records.

```bash
python3 download_conversations.py --workspace "MyWorkspace"
python3 download_conversations.py --app-id <workspace_id>      # direct ID lookup
python3 download_conversations.py --workspace "X" --version 3  # specific ADM version
python3 download_conversations.py --workspace "X" --out snapshots/x-convos.json
```

**Output:** `snapshots/conversations-<workspace>-<date>.json` + console summary (protocols, top ports).

### 7. `download_flows.py` — scope-filtered flow export

Downloads raw flows from the `flowsearch` API with a consumer-scope × provider-scope filter, ideal for segmentation analysis.

```bash
# Typical segmentation analysis
python3 download_flows.py \
  --consumer-scope "root:Internal:AppA" \
  --provider-scope "root:Internal:LegacyDB"

python3 download_flows.py --hours 48                         # 48-hour window
python3 download_flows.py --include-netflow                  # include NetFlow-sourced flows
python3 download_flows.py --tag "segmentation-1" --out snapshots/custom.csv
```

> Edit `DEFAULT_CONSUMER_SCOPE` / `DEFAULT_PROVIDER_SCOPE` at the top of the script to persist the defaults for a given POV.

**Output:** `snapshots/flows-<tag>-<date>.csv` (41 columns — 5-tuple, scope, policy verdicts, process, TLS, latency, threat fields).

### 8. `download_policies.py` — policies + workload roll-up

Downloads every policy from every workspace and builds a Markdown + HTML policy report.

```bash
python3 download_policies.py
python3 download_policies.py --no-html                       # Markdown + JSON only
python3 download_policies.py --out reports/policy-matrix.html
```

**Outputs:**
- `snapshots/policies-<date>.json`
- `reports/policy-workload-report-<date>.md`
- `reports/policy-workload-report-<date>.html`

### 9. `download_forensics.py` — forensics configuration

Exports forensics rule configuration and recent alerts.

```bash
python3 download_forensics.py
python3 download_forensics.py --no-html
python3 download_forensics.py --out reports/forensics.html --json-out snapshots/forensics.json
```

### 10. `generate_flow_analysis.py` — deep live flow analysis

Queries live flow data and renders a deep analysis across 10 dimensions: verdicts, protocols, TCP performance, TLS security, scope pairs, processes, users, etc.

```bash
python3 generate_flow_analysis.py                            # last 24h, up to 2000 flows
python3 generate_flow_analysis.py --hours 72 --limit 5000
python3 generate_flow_analysis.py --out reports/flow-deepdive.html
```

**Output:** `reports/flow-analysis-<date>.html`.

### 11. `generate_vuln_report.py` — vulnerability assessment

Scans every workload for CVEs and installed packages using the `/workload/{uuid}/vulnerabilities` and `/packages` endpoints. Produces both HTML and CSV.

```bash
python3 generate_vuln_report.py                              # full scan + HTML
python3 generate_vuln_report.py --csv-only                   # CSV only (faster turnaround)
python3 generate_vuln_report.py --out reports/vuln-kickoff.html
```

**Outputs:**
- `reports/vuln-report-<date>.html` — severity breakdown, top CVEs, most-vulnerable hosts, Cisco CVM intelligence
- `reports/vuln-report-<date>.csv` — one row per (host, CVE) for pivoting in Excel

### 12. `generate_forensics_report.py` — forensics posture

Generates a forensics posture assessment from previously downloaded forensics data.

```bash
python3 generate_forensics_report.py
python3 generate_forensics_report.py --out reports/forensics-readout.html
```

### 13. `query_long_lived_processes.py` — process persistence analysis

Identifies processes that persist across multiple days of flow data (candidates for allow-lists or anomaly investigation).

```bash
python3 query_long_lived_processes.py                          # last 3 days
python3 query_long_lived_processes.py --days 7 --min-days 5    # must appear ≥5 of 7 days
python3 query_long_lived_processes.py --limit 5000 --json      # also export raw JSON
python3 query_long_lived_processes.py --no-html                # console-only
```

**Output:** `reports/long-lived-processes-<date>.html` + optional JSON export.

---

## Typical POV Workflow

```
Week 0 — Onboarding
  ├── cp .env.example .env           # fill in credentials
  ├── api_test_suite.py              # validate API access + capabilities
  └── cluster_snapshot.py            # baseline snapshot

Week 1 — Initial Readout
  ├── generate_html_report.py        # customer readout from baseline snapshot
  ├── download_policies.py           # policy inventory + markdown/HTML report
  └── generate_vuln_report.py        # baseline vulnerability posture

Week 2–3 — Deep Analysis
  ├── download_conversations.py      # per-workspace conversation export
  ├── download_flows.py              # scope-pair segmentation flows
  ├── generate_flow_analysis.py      # TLS, TCP, verdict, scope-pair deep dive
  └── query_long_lived_processes.py  # allow-list candidates

Week 4+ — Progress / Delta
  ├── cluster_snapshot.py            # new snapshot
  ├── cluster_delta.py --latest      # markdown change summary
  └── generate_combined_report.py --latest   # baseline vs current HTML
```

---

## Project Structure

```
CSW_POV_Template/
├── .env.example              # Credential template — copy to .env
├── .gitignore                # Excludes secrets, caches, large snapshots
├── README.md                 # This file
│
├── csw_api.py                # Core HMAC API client (imported by all scripts)
│
├── api_test_suite.py         # API capability validation
├── cluster_snapshot.py       # Full cluster snapshot
├── cluster_delta.py          # Snapshot diff (Markdown)
│
├── download_conversations.py # Conversation export per workspace
├── download_flows.py         # Scope-filtered flow export (CSV)
├── download_policies.py      # Policy download + Markdown/HTML report
├── download_forensics.py     # Forensics config + alert export
│
├── generate_html_report.py      # Single-snapshot HTML readout
├── generate_combined_report.py  # Baseline vs current HTML
├── generate_flow_analysis.py    # Live deep flow analysis HTML
├── generate_vuln_report.py      # Vulnerability HTML + CSV
├── generate_forensics_report.py # Forensics posture HTML
├── query_long_lived_processes.py # Process persistence HTML + JSON
│
├── reports/                  # Generated HTML / Markdown reports (git-tracked)
│   └── .gitkeep
└── snapshots/                # JSON snapshots and CSV exports (partially git-ignored)
    └── .gitkeep
```

---

## Customisation for Your POV

1. **Clone and rename** for the customer:
   ```bash
   git clone https://github.com/chandrapati/CSW_POV_Template.git MyCustomer_CSW_POV
   cd MyCustomer_CSW_POV
   rm -rf .git && git init                       # start a fresh history
   ```
2. **Fill in `.env`** with the customer's cluster URL / API key / secret.
3. **(Optional) Hard-code defaults** for scripts you will run repeatedly:
   - `download_flows.py` → set `DEFAULT_CONSUMER_SCOPE`, `DEFAULT_PROVIDER_SCOPE`, `DEFAULT_ROOT_SCOPE`
   - `download_policies.py` → adjust workspace keyword filters if you only want a subset
4. **Run the scripts** in the workflow order above.
5. **Commit reports** (but never `.env`) to your customer-specific repo for tracking.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Missing environment variables` | `.env` not found or incomplete | `cp .env.example .env`; confirm `CSW_API_URL`, `CSW_API_KEY`, `CSW_API_SECRET` are all set |
| `HTTP 401 / 403` | API key lacks capability for the endpoint | Re-create key in CSW UI with missing capability (see table above) |
| `certificate verify failed` | Corporate TLS inspection or self-signed cluster cert | Set `CSW_VERIFY_SSL=false` in `.env` (or install the root CA into the system trust store) |
| `Found 0 sensors` | Sensors endpoint returned list vs dict (cluster-specific) | Re-run; `generate_vuln_report.py` handles both. If still empty, test via `python3 csw_api.py GET /openapi/v1/sensors` |
| Pagination hangs on large exports | High cardinality + conservative rate-limit | Interrupt with `Ctrl-C`; reduce `--limit` or add `--hours` window |
| `ValueError: scope not found` | Scope string must match exactly (case-sensitive) | Run `python3 csw_api.py GET /openapi/v1/app_scopes` and copy the exact `name` field |

---

## Security Notes

- **Never commit `.env`, `credentials.json`, or any file containing API keys.** `.gitignore` excludes them by default — do not remove those rules.
- **Scope API keys narrowly.** Use read-only capabilities for POV work. Re-generate keys at the end of every engagement.
- **Keep `CSW_VERIFY_SSL=true`** in production. Only disable it when dealing with an internal CA that cannot be installed locally.
- **Snapshot JSONs** (`snapshots/*.json`) may contain sensitive inventory data (internal IPs, hostnames, CVEs). Commit selectively or keep the directory git-ignored in customer-specific clones.
- **Rotate the API key** if this template is ever pushed to a public repo with credentials still present — treat the key as compromised.
- **HMAC signatures** in `csw_api.py` follow Cisco's canonical format (`METHOD\nPATH\nCHECKSUM\nCONTENT-TYPE\nTIMESTAMP\n`) — do not modify the signing routine without consulting the CSW OpenAPI reference.

---

## License & Attribution

Internal Cisco TME toolkit. Intended for POV / PoC engagements only — not a supported Cisco product.
