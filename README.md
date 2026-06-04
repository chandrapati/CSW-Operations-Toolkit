# CSW POV Template

Reusable toolkit for **Cisco Secure Workload (CSW / Tetration)** Proof-of-Value engagements.
Clone this repository at the start of every new POV and follow the quick-start guide below.

The toolkit provides **15 Python scripts** that cover the full POV lifecycle:

> **API validation → data collection → snapshot comparison → HTML reporting → vulnerability assessment → executive summary**

- No external dependencies (pure Python 3.8+ standard library)
- HMAC-SHA256 authenticated API client
- Shareable HTML reports with inline styling and graceful browser fallbacks
- Designed for both SaaS CSW clusters and on-prem Tetration appliances

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Configuration](#configuration)
4. [Script Reference](#script-reference)
5. [Typical POV Workflow](#typical-pov-workflow)
6. [Project Structure](#project-structure)
7. [Customization for Your POV](#customization-for-your-pov)
8. [Troubleshooting](#troubleshooting)
9. [Security Notes](#security-notes)

---

## Quick Start

```bash
# 1. Clone the template for a new engagement
git clone https://github.com/chandrapati/CSW_POV_Template.git csw-pov-engagement
cd csw-pov-engagement

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
| `CSW_API_URL` | yes | Cluster base URL, e.g. `https://your-cluster.tetrationcloud.com` (no trailing `/openapi`) |
| `CSW_API_KEY` | yes | API key identifier (hex string) |
| `CSW_API_SECRET` | yes | Paired secret (hex string) |
| `CSW_VERIFY_SSL` | no | `true` by default. Set to `false` for self-signed clusters or corporate TLS inspection |
| `CSW_ROOT_SCOPE` | no | Root scope name. Most scripts auto-detect, set it to short-circuit the lookup |

`.env` is git-ignored — it is never committed.

---

## Script Reference

All runnable tools are invoked with `python3 <script>.py [options]` and print `--help` when called with `-h`. The toolkit has **15 runnable tools** and **2 shared modules**.

### Shared modules and API helper

| File | What it can do | Highlights | Typical use |
|---|---|---|---|
| `csw_api.py` | Provides the common CSW OpenAPI client and can also run one-off API calls from the CLI. | Loads `.env`, signs requests with HMAC-SHA256, supports query parameters and JSON request bodies, returns parsed JSON with status/error details. | Use directly for ad-hoc API checks, or import from other scripts. |
| `csw_helpers.py` | Provides reusable helper functions for collection scripts. | Pagination generator, sensor enumeration, IP-to-sensor mapping, safe filename generation, response-shape normalization, CSV-safe field flattening, and shared agent-type constants. | Import from new scripts before duplicating pagination, sensor lookup, or filename logic. |

Direct API debugging examples:

```bash
python3 csw_api.py GET /openapi/v1/app_scopes
python3 csw_api.py GET /openapi/v1/sensors --limit 50 --offset 0
python3 csw_api.py POST /openapi/v1/inventory/search '{"filter":{"type":"eq","field":"os","value":"windows"}}'
python3 csw_helpers.py   # helper self-test; no API call required
```

### Runnable tools

| Script | What it can do | Highlights | Outputs |
|---|---|---|---|
| `api_test_suite.py` | Validates API reachability and API-key capability coverage across the major endpoint groups used by the toolkit. | Dynamically discovers the root scope, tests agent/scope/policy/flow/vulnerability-style access paths, supports `--quick` and `--category`, and writes pass/warn/fail notes for missing capabilities or unsupported endpoints. | Console report or Markdown via `--output reports/api-capabilities.md`. |
| `cluster_snapshot.py` | Captures a point-in-time cluster baseline. | Collects sensors, scopes, workspaces, policies, inventory, and recent flows; supports JSON-only, Markdown-only, alternate output directory, and `--skip-flows` when flow capability is unavailable. | `snapshots/snapshot-<date>.json` and `snapshots/snapshot-<date>.md`. |
| `cluster_delta.py` | Compares two cluster snapshots. | Auto-selects the two newest snapshots with `--latest`, highlights agent additions/removals, scope/workspace/policy changes, and inventory drift. | Markdown delta report to stdout or `--output reports/weekly-delta.md`. |
| `generate_html_report.py` | Turns one snapshot into a self-contained HTML readout. | Uses the newest snapshot by default, summarizes visibility/enforcement posture, scope tree, flows, and risky-port exposure without external CSS/JS dependencies. | `reports/readout-<date>.html` or a custom `--out` path. |
| `generate_combined_report.py` | Builds a baseline-vs-current HTML report. | Combines current snapshot posture with change deltas; can auto-pick newest two snapshots or accept explicit baseline/current files. | Combined HTML report via `--out`, or date-based default. |
| `download_conversations.py` | Exports ADM workspace conversations. | Resolves workspace name or accepts an application ID, selects latest or specified ADM version, paginates all conversation records, and summarizes protocols/top ports. | `snapshots/conversations-<workspace>-<date>.json`. |
| `download_flows.py` | Exports scope-filtered flow records for segmentation analysis. | Filters consumer-scope to provider-scope traffic, excludes NetFlow-only records by default for higher-fidelity process/policy context, supports lookback window, tag, and custom CSV path. | `snapshots/flows-<tag>-<date>.csv`. |
| `download_policies.py` | Downloads workspace policies and rolls them up with workload scope context. | Collects policies from every workspace, performs inventory lookups for policy scopes, highlights risky ports in reports, and supports Markdown/JSON-only mode with `--no-html`. | `snapshots/policies-<date>.json`, `reports/policy-workload-report-<date>.md`, and HTML. |
| `download_forensics.py` | Exports forensics configuration from the cluster. | Retrieves forensic profiles, rules, intents, and intent ordering; documents SaaS OpenAPI limits around raw forensic events; supports JSON and HTML outputs. | `snapshots/forensics-config-<date>.json` and `reports/forensics-config-<date>.html`. |
| `generate_flow_analysis.py` | Queries live flow data and produces a deeper flow-analysis report. | Analyzes verdicts, protocol mix, TCP latency/retransmission signals, TLS versions/ciphers, rejected flows, risky destination ports, scope pairs, host pairs, processes, and users. | `reports/flow-analysis-<date>.html`. |
| `generate_vuln_report.py` | Builds vulnerability exposure and package-inventory reports from CSW workload data. | Enumerates sensors, queries per-workload vulnerabilities and packages, aggregates severity/CVM fields where present, ranks top CVEs and most affected hosts, and can produce CSV-only output. | `reports/vuln-report-<date>.html` and `reports/vuln-report-<date>.csv`. |
| `generate_forensics_report.py` | Assesses forensics posture and MITRE ATT&CK coverage. | Uses forensics config and sensor telemetry to show what rules/profiles/intents exist, where forensics is enabled, and which ATT&CK tactics have limited coverage. | `reports/forensics-posture-<date>.html`. |
| `query_long_lived_processes.py` | Finds processes that repeatedly communicate over multiple days. | Queries flowsearch one day at a time, aggregates `(host, process)` persistence, categorizes common process types, flags sensitive ports, and can export raw JSON. | Console summary, `reports/long-lived-processes-<date>.html`, optional JSON. |
| `generate_executive_report.py` | Produces an executive summary from a live or saved snapshot plus optional companion reports. | Computes visibility/enforcement KPIs, blast-radius score, vulnerability exposure, forensics readiness, posture scorecards, prioritized recommendations, and methodology/source sections. | `reports/executive-summary-<date>.html` and `.md`, unless `--html-only` or `--md-only` is used. |
| `risky_port_audit.py` | Audits policy posture for risky ports without changing the cluster. | Read-only checks for broad risky-port allows, east-west risky-port exposure, ADM/draft risky-port candidates, and PCI CDE boundary crossings using configurable label fields. | `snapshots/risky-port-findings.json`, `snapshots/risky-port-audit.md`, and `reports/risky-port-audit-<date>.html`. |

### Example commands

```bash
# API validation
python3 api_test_suite.py --output reports/api-capabilities.md
python3 api_test_suite.py --quick
python3 api_test_suite.py --category agents flow vulnerabilities

# Snapshot and reporting
python3 cluster_snapshot.py
python3 cluster_snapshot.py --skip-flows
python3 generate_html_report.py --snapshot snapshots/snapshot-2026-04-07.json --out reports/kickoff-readout.html
python3 cluster_delta.py --latest --output reports/weekly-delta.md
python3 generate_combined_report.py --latest --out reports/monthly-review.html

# Data exports and analysis
python3 download_conversations.py --workspace "WorkspaceName"
python3 download_flows.py --consumer-scope "root:Internal:AppA" --provider-scope "root:Internal:LegacyDB"
python3 download_policies.py --out reports/policy-matrix.html
python3 download_forensics.py --out reports/forensics.html --json-out snapshots/forensics.json
python3 generate_flow_analysis.py --hours 72 --limit 5000 --out reports/flow-deepdive.html
python3 generate_vuln_report.py --out reports/vuln-kickoff.html
python3 generate_forensics_report.py --out reports/forensics-readout.html
python3 query_long_lived_processes.py --days 7 --min-days 5 --json
python3 risky_port_audit.py --use-cache --pci-field user_pci_scope --pci-value true

# Executive closeout
python3 generate_executive_report.py --snapshot snapshots/snapshot-2026-04-20.json --no-fetch-live --prepared-for "Engagement Stakeholders" --prepared-by "CSW POV Team"
python3 generate_executive_report.py --out-md reports/exec-summary.md --md-only
```

## Typical POV Workflow

```
Week 0 — Onboarding
  ├── cp .env.example .env           # fill in credentials
  ├── api_test_suite.py              # validate API access + capabilities
  └── cluster_snapshot.py            # baseline snapshot

Week 1 — Initial Readout
  ├── generate_html_report.py        # stakeholder readout from baseline snapshot
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

Closeout — Executive deliverable
  └── generate_executive_report.py            # one-page CISO summary
                                              # (HTML + Markdown, aggregates
                                              # vuln CSV, policies, flows)
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
├── csw_helpers.py            # Shared utilities (pagination, sensor map, slugging)
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
├── generate_executive_report.py # CISO-grade exec summary (HTML + Markdown)
├── query_long_lived_processes.py # Process persistence HTML + JSON
├── risky_port_audit.py          # Read-only risky-port policy audit
│
├── reports/                  # Generated HTML / Markdown reports (git-tracked)
│   └── .gitkeep
└── snapshots/                # JSON snapshots and CSV exports (partially git-ignored)
    └── .gitkeep
```

### Shared helpers (`csw_helpers.py`)

A small utilities module that consolidates patterns previously duplicated
across the suite. Existing scripts use it; new scripts should reach for
these helpers before reimplementing the same plumbing.

| Helper | What it replaces | Used by |
| --- | --- | --- |
| `paginate(method, path, body=, params=, batch_size=, max_pages=, sleep=)` | Three near-identical offset-cursor `while True` loops in `download_flows.py`, `download_conversations.py`, `query_long_lived_processes.py`. Yields `(page_number, results)` tuples so callers keep their own progress display. | `download_flows.py`, `download_conversations.py`, `query_long_lived_processes.py` |
| `fetch_all_sensors()` | Four copies of "GET `/sensors`, then handle `dict-with-results` vs bare-list response" (was in `generate_vuln_report.py`, `generate_forensics_report.py`, `cluster_snapshot.py`, `api_test_suite.py`). Auto-falls back to pagination if the cluster returns a continuation cursor. | `generate_vuln_report.py`, `generate_forensics_report.py` |
| `build_sensor_map(sensors=None)` | New. Returns `ip → {uuid, hostname, agent_type, platform}` for fast workload enrichment in any new report that needs to translate IPs into agents. | (available for new scripts) |
| `safe_filename(name, max_length=120)` | Ad-hoc `name.replace(":", "_").replace(" ", "_")` slugging (was in `download_conversations.py`). Handles full set of filesystem-unfriendly characters. | `download_conversations.py` |
| `extract_results(response)` | The `isinstance(data, list) / dict / "results" / "items"` shape-handling pattern that exists in many places. Always returns a list, never raises. | (foundation for `fetch_all_sensors`) |
| `flatten_record(record, fields, aliases)` | New. CSV-friendly projection that joins list fields with `; `, JSON-stringifies nested dicts, and reads through alias keys for irregular fields like `user_orchestrator_Workload Type`. | (available for new scripts) |
| `AGENT_TYPES` | Constants for `agent_type` strings (`ENFORCER`, `VISIBILITY`, `UNIVERSAL`, …) so consumers don't sprinkle string literals through their code. | (available for new scripts) |
| `KNOWN_FIELD_ALIASES` | Mapping for the known space-in-key irregularities that come back from CSW. Used by `flatten_record()`. | (available for new scripts) |

Self-test (no API needed):

```bash
python3 csw_helpers.py
```

> **Note on `cluster_snapshot.py`:** This script shells out to `csw_api.py`
> via `subprocess` rather than importing it. It already has its own local
> `safe_list()` helper and is intentionally left untouched — retrofitting it
> would require switching its integration model and isn't worth the churn.

---

## Customization for Your POV

1. **Clone and rename** for the engagement:
   ```bash
   git clone https://github.com/chandrapati/CSW_POV_Template.git csw-pov-engagement
   cd csw-pov-engagement
   rm -rf .git && git init                       # start a fresh history
   ```
2. **Fill in `.env`** with the CSW cluster URL / API key / secret.
3. **(Optional) Hard-code defaults** for scripts you will run repeatedly:
   - `download_flows.py` → set `DEFAULT_CONSUMER_SCOPE`, `DEFAULT_PROVIDER_SCOPE`, `DEFAULT_ROOT_SCOPE`
   - `download_policies.py` → adjust workspace keyword filters if you only want a subset
4. **Run the scripts** in the workflow order above.
5. **Commit reports** (but never `.env`) to the engagement repo for tracking.

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
- **Snapshot JSONs** (`snapshots/*.json`) may contain sensitive inventory data (internal IPs, hostnames, CVEs). Commit selectively or keep the directory git-ignored in engagement-specific clones.
- **Rotate the API key** if this template is ever pushed to a public repo with credentials still present — treat the key as compromised.
- **HMAC signatures** in `csw_api.py` follow Cisco's canonical format (`METHOD\nPATH\nCHECKSUM\nCONTENT-TYPE\nTIMESTAMP\n`) — do not modify the signing routine without consulting the CSW OpenAPI reference.

---

## License & Attribution

Reusable Cisco Secure Workload POV / PoC toolkit. Not a supported Cisco product.

---

## Related Cisco Secure Workload Resources

Other public repositories covering the full Cisco Secure Workload journey — from onboarding to compliance reporting:

| Repository | What It Covers | Best For |
|---|---|---|
| [**csw-splunk-integration**](https://github.com/chandrapati/csw-splunk-integration) | Step-by-step CSW → Splunk integration via Syslog connector and Cisco Security Cloud App | Security operations teams |
| [**CSW-User-Education**](https://github.com/chandrapati/CSW-User-Education) | Intro guide, curated video library, and customer onboarding runbook | Anyone new to CSW — great first stop |
| [**CSW-Agent-Installation-Guide**](https://github.com/chandrapati/CSW-Agent-Installation-Guide) | Host agent install across Linux, Windows, cloud, containers, and agentless environments | Operations and deployment teams |
| [**CSW-Policy-Lifecycle**](https://github.com/chandrapati/CSW-Policy-Lifecycle) | Full policy lifecycle: ADM discovery → Monitor → Simulate → Enforce + day-2 ops | SE/SA and customer engineering |
| [**CSW-Compliance-Mapping**](https://github.com/chandrapati/CSW-Compliance-Mapping) | Compliance reports for HIPAA, SOC 2, PCI DSS v4, NIST 800-53, ISO 27001, CISA ZTMM, FIPS 140 | CISO, GRC, and audit teams |
| [**csw\_blast\_radius\_demo**](https://github.com/chandrapati/csw_blast_radius_demo) | Hands-on demo showing blast radius reduction via microsegmentation | Demo and lab environments |
| [**CSW-ServiceNow-Connector-Guide**](https://github.com/chandrapati/CSW-ServiceNow-Connector-Guide) | ServiceNow CMDB connector (Inventory Enrichment): setup, label usage, operations, and limits — validated against CSW 4.0 docs | SE/SA and platform/CMDB teams |

> **Suggested path for a new customer:**
> CSW-User-Education → CSW-Agent-Installation-Guide → CSW-Policy-Lifecycle → csw-splunk-integration → CSW-Compliance-Mapping
