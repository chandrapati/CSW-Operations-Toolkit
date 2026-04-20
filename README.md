# CSW POV Template

Reusable toolkit for Cisco Secure Workload (CSW / Tetration) Proof-of-Value engagements.
Clone this repository at the start of every new POV and follow the quick-start guide below.

The toolkit provides 14 scripts that cover the full POV lifecycle: **API validation → data collection → snapshot comparison → HTML reporting → vulnerability assessment**.

---

## Quick Start

```bash
# 1. Clone the template
git clone https://github.com/chandrapati/CSW_POV_Template.git MyCustomer_CSW_POV
cd MyCustomer_CSW_POV

# 2. Set up Python environment
python3 -m venv .venv && source .venv/bin/activate

# 3. Configure credentials
cp .env.example .env
# Edit .env with your cluster URL, API key, and API secret

# 4. Run the API test suite to validate connectivity
python3 api_test_suite.py

# 5. Take a cluster snapshot
python3 cluster_snapshot.py

# 6. Generate the HTML readout report
python3 generate_html_report.py

# 7. Open the report
open reports/readout-$(date +%Y-%m-%d).html
```

---

## Scripts Reference

### Core API Client

| Script | Purpose |
|---|---|
| `csw_api.py` | HMAC-authenticated API client. All other scripts import this module. Not run directly. |

### Data Collection

| Script | Purpose |
|---|---|
| `api_test_suite.py` | Tests all CSW API endpoint capabilities and generates a Markdown compatibility report. Run first on any new cluster. |
| `cluster_snapshot.py` | Captures full cluster state (agents, scopes, workspaces, policies, inventory, flows) → JSON snapshot + Markdown summary. |
| `download_conversations.py` | Downloads policy-matched conversation data from a workspace → JSON + CSV. |
| `download_flows.py` | Downloads filtered flow data via the flowsearch API → CSV. Configurable scope filters for segmentation analysis. |
| `download_policies.py` | Downloads all policies from all workspaces, generates Markdown + HTML policy reports. |
| `download_forensics.py` | Downloads forensics/alert data from the cluster → JSON + CSV + HTML report. |

### Reporting

| Script | Purpose |
|---|---|
| `generate_html_report.py` | Generates a self-contained HTML readout from a single JSON snapshot. |
| `generate_combined_report.py` | Generates a combined HTML report from two snapshots (baseline vs current) showing change delta. |
| `generate_flow_analysis.py` | Queries live flows from the cluster and generates a deep flow analysis HTML report (TLS, TCP perf, verdicts, scope pairs). |
| `generate_vuln_report.py` | Scans all workloads for CVEs and generates a vulnerability assessment HTML report + CSV export. |
| `generate_forensics_report.py` | Generates an HTML forensics report from collected alert data. |

### Advanced Analysis

| Script | Purpose |
|---|---|
| `query_long_lived_processes.py` | Identifies long-lived processes across the cluster via flow data analysis. |
| `cluster_delta.py` | Compares two snapshots and generates a Markdown change report (used by `generate_combined_report.py`). |

---

## Typical POV Workflow

```
Week 1 — Onboarding
  ├── api_test_suite.py          → Validate API access and capabilities
  ├── cluster_snapshot.py        → Baseline snapshot
  └── generate_html_report.py    → Initial readout for the customer

Week 2–4 — Analysis
  ├── download_policies.py       → Policy review and documentation
  ├── download_conversations.py  → Conversation analysis per workspace
  ├── download_flows.py          → Deep flow analysis for segmentation
  ├── generate_flow_analysis.py  → TLS, TCP performance, and verdict analysis
  └── generate_vuln_report.py    → Vulnerability assessment across all hosts

Ongoing — Progress Tracking
  ├── cluster_snapshot.py        → Take periodic snapshots
  ├── generate_combined_report.py → Show delta between baseline and current
  └── cluster_delta.py           → Markdown change summary
```

---

## Configuration

### Environment Variables (.env)

| Variable | Required | Description |
|---|---|---|
| `CSW_API_URL` | Yes | Cluster base URL (e.g. `https://customer.tetrationcloud.com`) |
| `CSW_API_KEY` | Yes | API key hex string from CSW UI |
| `CSW_API_SECRET` | Yes | API secret hex string (paired with key) |
| `CSW_VERIFY_SSL` | No | Set to `false` for self-signed certs (default: `true`) |
| `CSW_ROOT_SCOPE` | No | Root scope name (auto-detected by most scripts) |

### API Key Capabilities

Generate your API key in the CSW UI with these capabilities:

- `sensor_management` — Read sensors/agents
- `flow_inventory_query` — Flow search and inventory queries
- `app_policy_management` — Read workspaces, policies, and conversations
- `user_role_scope_management` — Read user/role data (optional)
- `external_integration` — Connectors and forensics (optional)

---

## Project Structure

```
CSW_POV_Template/
├── .env.example              # Credential template — copy to .env
├── .gitignore                # Excludes secrets, caches, large snapshots
├── README.md                 # This file
│
├── csw_api.py                # Core API client (imported by all scripts)
├── api_test_suite.py         # API capability validation
├── cluster_snapshot.py       # Full cluster snapshot
├── cluster_delta.py          # Snapshot comparison
│
├── download_conversations.py # Conversation export
├── download_flows.py         # Flow data export (scope-filtered)
├── download_policies.py      # Policy download + report
├── download_forensics.py     # Forensics/alert export
│
├── generate_html_report.py   # Single-snapshot HTML readout
├── generate_combined_report.py # Dual-snapshot delta HTML report
├── generate_flow_analysis.py # Live flow analysis HTML report
├── generate_vuln_report.py   # Vulnerability assessment HTML + CSV
├── generate_forensics_report.py # Forensics HTML report
├── query_long_lived_processes.py # Long-lived process analysis
│
├── reports/                  # Generated HTML reports (git-tracked)
└── snapshots/                # JSON snapshots and CSV exports
```

---

## Customization for Your POV

1. **Clone and rename** the repo for your customer: `MyCustomer_CSW_POV`
2. **Fill in `.env`** with the customer cluster credentials
3. **Update `download_flows.py`** defaults if doing segmentation analysis:
   - Set `DEFAULT_CONSUMER_SCOPE` and `DEFAULT_PROVIDER_SCOPE` to the customer's scope paths
4. **Run scripts** in the order shown in the workflow above
5. **Commit reports** to your customer-specific repo for tracking

---

## Requirements

- Python 3.8+
- No pip dependencies — uses only Python standard library (`urllib`, `json`, `csv`, `hashlib`, `hmac`)
- Network access to the CSW cluster
- API key with appropriate capabilities

---

## Security Notes

- **Never commit `.env` or `credentials.json`** — they are in `.gitignore`
- **API keys** should be scoped to read-only capabilities where possible
- **SSL verification** should be enabled in production (`CSW_VERIFY_SSL=true`)
- **Snapshot JSON** files may contain sensitive inventory data — commit selectively
