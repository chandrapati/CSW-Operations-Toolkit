#!/usr/bin/env python3
"""
download_flows.py — Download filtered flow data from the CSW cluster
--------------------------------------------------------------------
Queries the CSW flowsearch API with a configurable scope-based filter
and downloads all matching flows to CSV.

Default filter (segmentation use-case):
  - Flows where EITHER consumer OR provider is in the consumer scope
  - AND EITHER consumer OR provider is in the provider scope
  - EXCLUDING flows sourced from NetFlow collectors

Configure default scopes via --consumer-scope and --provider-scope,
or set them in the DEFAULT_CONSUMER_SCOPE / DEFAULT_PROVIDER_SCOPE
constants below for your POV.

Usage:
    python3 download_flows.py --consumer-scope "root:Internal:ScopeA" --provider-scope "root:Internal:ScopeB"
    python3 download_flows.py --hours 48
    python3 download_flows.py --include-netflow

Output:
    snapshots/flows-<tag>-<date>.csv
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csw_api

csw_api._load_dotenv()

DATE_TAG = datetime.now().strftime("%Y-%m-%d")
BATCH_SIZE = 100

# ┌─────────────────────────────────────────────────────────────┐
# │  CUSTOMIZE FOR YOUR POV                                    │
# │  Set the two scope paths that define the segmentation      │
# │  boundary you want to analyse. Use the full colon-         │
# │  separated scope path from the CSW UI.                     │
# └─────────────────────────────────────────────────────────────┘
DEFAULT_CONSUMER_SCOPE = ""   # e.g. "root-scope:Internal:SegmentationEnvironment:ScopeA"
DEFAULT_PROVIDER_SCOPE = ""   # e.g. "root-scope:Internal:LEGACY_Scope"
DEFAULT_ROOT_SCOPE = ""       # e.g. "root-scope" — auto-detected if left empty

# CSV columns to export — covers network 5-tuple, scope membership,
# traffic volume, policy verdicts, process visibility, TLS metadata,
# latency, threat indicators, and user-defined annotations.
CSV_FIELDS = [
    "timestamp", "start_timestamp",
    "src_address", "src_hostname", "src_port", "src_scope_name",
    "dst_address", "dst_hostname", "dst_port", "dst_scope_name",
    "proto", "service_name",
    "fwd_bytes", "fwd_pkts", "rev_bytes", "rev_pkts",
    "fwd_policy_permitted", "fwd_policy_rejected", "fwd_policy_escaped",
    "src_process_name", "dst_process_name",
    "fwd_process_string", "rev_process_string",
    "src_is_internal", "dst_is_internal",
    "dst_domain_names", "dst_country",
    "tls_version", "tls_cipher",
    "fwd_tcp_handshake_usec", "total_network_latency_usec",
    "is_malicious_flow", "consumer_malicious", "provider_malicious",
    "consumer_sensor_type", "provider_sensor_type",
    "src_logged_in_user", "dst_logged_in_user",
    "user_src_NETFLOW_IDENTIFIED", "user_dst_NETFLOW_IDENTIFIED",
]


def build_scope_filter(consumer_scope, provider_scope, include_netflow=False):
    """Build a nested CSW flowsearch filter from scope names.

    The CSW flow data stores scope membership as arrays (each endpoint
    belongs to multiple scopes in the hierarchy).  The "contains" filter
    type checks whether the specified value appears anywhere in the array.

    Returns a dict suitable for the "filter" field of the flowsearch body.
    """
    filters = [
        # Clause 1: at least one endpoint must be in the consumer scope
        {
            "type": "or",
            "filters": [
                {"type": "contains", "field": "src_scope_name",
                 "value": consumer_scope},
                {"type": "contains", "field": "dst_scope_name",
                 "value": consumer_scope},
            ],
        },
        # Clause 2: at least one endpoint must be in the provider scope
        {
            "type": "or",
            "filters": [
                {"type": "contains", "field": "src_scope_name",
                 "value": provider_scope},
                {"type": "contains", "field": "dst_scope_name",
                 "value": provider_scope},
            ],
        },
    ]

    if not include_netflow:
        # Clause 3: exclude flows that were identified via NetFlow
        # (only keep agent-collected flows for higher fidelity)
        filters.append({
            "type": "not",
            "filter": {
                "type": "or",
                "filters": [
                    {"type": "eq", "field": "user_src_NETFLOW_IDENTIFIED",
                     "value": "TRUE"},
                    {"type": "eq", "field": "user_dst_NETFLOW_IDENTIFIED",
                     "value": "TRUE"},
                ],
            },
        })

    return {"type": "and", "filters": filters}


def download_flows(flow_filter, root_scope, t0, t1):
    """Paginate through the flowsearch API and collect all matching flows.

    The CSW API returns at most BATCH_SIZE flows per call and provides an
    opaque "offset" token for cursor-based pagination.  We loop until
    either fewer than BATCH_SIZE results are returned (last page) or the
    offset token is absent.
    """
    all_flows = []
    offset = ""
    page = 0

    while True:
        page += 1
        body = {
            "t0": t0,
            "t1": t1,
            "filter": flow_filter,
            "scopeName": root_scope,
            "limit": BATCH_SIZE,
        }
        if offset:
            body["offset"] = offset

        r = csw_api.make_request("POST", "/openapi/v1/flowsearch", body=body)
        status = r.get("status")

        if status != 200:
            print(f"\n  API error on page {page}: HTTP {status}")
            err = r.get("data", {})
            if isinstance(err, dict):
                print(f"      {err.get('error', err)}")
            break

        data = r.get("data", {})
        if not isinstance(data, dict):
            break

        results = data.get("results", [])
        all_flows.extend(results)
        print(
            f"\r  Page {page}: +{len(results)} flows "
            f"(total: {len(all_flows):,})",
            end="", flush=True,
        )

        if len(results) < BATCH_SIZE:
            break

        offset = data.get("offset", "")
        if not offset:
            break

        time.sleep(0.2)

    print()
    return all_flows


def write_csv(flows, csv_path):
    """Write flow records to a CSV file.

    Array-valued fields (scope names, domain names) are joined with
    semicolons so the CSV remains one-row-per-flow.
    """
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=CSV_FIELDS, extrasaction="ignore",
        )
        writer.writeheader()
        for fl in flows:
            row = dict(fl)
            for key in ("dst_domain_names", "src_domain_names",
                        "src_scope_name", "dst_scope_name"):
                val = row.get(key)
                if isinstance(val, list):
                    row[key] = "; ".join(str(x) for x in val)
            writer.writerow(row)


def print_stats(flows):
    """Print a quick statistical summary of the downloaded flow data."""
    protos = {}
    ports = {}
    permitted = rejected = escaped = 0

    for fl in flows:
        p = fl.get("proto", "?")
        protos[p] = protos.get(p, 0) + 1

        port = str(fl.get("dst_port", "?"))
        ports[port] = ports.get(port, 0) + 1

        if fl.get("fwd_policy_permitted"):
            permitted += 1
        if fl.get("fwd_policy_rejected"):
            rejected += 1
        if fl.get("fwd_policy_escaped"):
            escaped += 1

    top_ports = sorted(ports.items(), key=lambda x: -x[1])[:10]

    print(f"\n  Quick stats:")
    print(f"      Protocols: "
          f"{dict(sorted(protos.items(), key=lambda x: -x[1]))}")
    print(f"      Top 10 ports: {dict(top_ports)}")
    print(f"      Permitted: {permitted:,} | "
          f"Rejected: {rejected:,} | Escaped: {escaped:,}")


def main():
    parser = argparse.ArgumentParser(
        description="Download filtered flow data from the CSW cluster.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 download_flows.py
  python3 download_flows.py --hours 48
  python3 download_flows.py --consumer-scope "root:Internal:ScopeA" --provider-scope "root:Internal:ScopeB"
  python3 download_flows.py --include-netflow --tag "all-sources"
        """,
    )
    parser.add_argument(
        "--consumer-scope",
        default=DEFAULT_CONSUMER_SCOPE,
        help="Scope name for the consumer/source side "
             f"(default: {DEFAULT_CONSUMER_SCOPE})",
    )
    parser.add_argument(
        "--provider-scope",
        default=DEFAULT_PROVIDER_SCOPE,
        help="Scope name for the provider/destination side "
             f"(default: {DEFAULT_PROVIDER_SCOPE})",
    )
    parser.add_argument(
        "--root-scope",
        default=DEFAULT_ROOT_SCOPE,
        help="Root scope for the flowsearch query "
             f"(default: {DEFAULT_ROOT_SCOPE})",
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Number of hours to look back (default: 24)",
    )
    parser.add_argument(
        "--include-netflow", action="store_true",
        help="Include NetFlow-sourced flows (excluded by default)",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Custom tag for the output filename "
             "(default: derived from scope names)",
    )
    parser.add_argument(
        "--out", "-o",
        default=None,
        help="Full output CSV path (overrides --tag)",
    )
    args = parser.parse_args()

    os.makedirs("snapshots", exist_ok=True)

    # Time window — epoch seconds required by the CSW API
    t1 = int(time.time())
    t0 = t1 - (args.hours * 3600)

    # Derive a short label for the consumer scope
    consumer_short = args.consumer_scope.split(":")[-1]
    provider_short = args.provider_scope.split(":")[-1]
    file_tag = args.tag or f"{consumer_short}_x_{provider_short}"

    flow_filter = build_scope_filter(
        args.consumer_scope,
        args.provider_scope,
        include_netflow=args.include_netflow,
    )

    print(f"\n  Cluster: {os.environ.get('CSW_API_URL', '?')}")
    print(f"  Date: {DATE_TAG}")
    print(f"  Flow window: last {args.hours} hours\n")
    print(f"  Filter:")
    print(f"      (Consumer scope = ...{consumer_short}"
          f"  OR  Provider scope = ...{consumer_short})")
    print(f"      AND (Consumer scope = ...{provider_short}"
          f"  OR  Provider scope = ...{provider_short})")
    if not args.include_netflow:
        print(f"      AND NOT (NETFLOW IDENTIFIED = TRUE)")
    print()

    flows = download_flows(flow_filter, args.root_scope, t0, t1)

    if not flows:
        print("  No flows found matching the filter.")
        return

    csv_path = args.out or f"snapshots/flows-{file_tag}-{DATE_TAG}.csv"
    write_csv(flows, csv_path)

    size_mb = os.path.getsize(csv_path) / (1024 * 1024)
    print(f"\n  Saved {len(flows):,} flows to {csv_path} ({size_mb:.1f} MB)")

    print_stats(flows)


if __name__ == "__main__":
    main()
