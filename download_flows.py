#!/usr/bin/env python3
"""
download_flows.py — Download filtered flow data from the CSW cluster
--------------------------------------------------------------------

What this script is for (plain English)
---------------------------------------
A **flow** in CSW is one record describing a network connection: which
two hosts talked, on which port, using which protocol, how many bytes
moved, and (if a policy was active) whether the connection was permitted
or rejected. The CSW cluster collects flows from every sensor it has, so
on a busy network this is millions of records per day.

This script is the workhorse for "show me all the conversations between
group A and group B over the last day" - the bread-and-butter question
when planning microsegmentation policy. It does this by:

  1. Asking the CSW ``/flowsearch`` API for flows where one end of the
     connection is in **consumer scope A** and the other end is in
     **provider scope B** (terms explained below).
  2. Paginating through the results 100 at a time (the helper
     ``csw_helpers.paginate()`` handles the loop).
  3. Writing the lot to a CSV file under ``snapshots/`` so the customer
     can open it in Excel.

Key terms
---------
  * **Scope**: a logical group of workloads. Scopes are arranged in a
    tree (e.g. ``Default:Production:Database``), and any workload that
    matches the scope's filter rule belongs to that scope plus all of
    its parents. Scopes are how CSW expresses "all my databases" or
    "anything in our staging environment" without naming individual IPs.
  * **Consumer / Provider**: CSW's words for "client side" and "server
    side" of a connection. The consumer is the one initiating the TCP
    handshake; the provider is the one accepting it.
  * **NetFlow** flows: flows reported by an external NetFlow collector
    (router or switch) instead of by a CSW agent. They are lower
    fidelity (no process info, no policy decision). This script
    excludes them by default - turn them back on with
    ``--include-netflow`` if you have no agent coverage on the segment.

Default filter logic, in plain English
--------------------------------------
"Show me flows where one endpoint is somewhere in the consumer scope's
tree AND the other endpoint is somewhere in the provider scope's tree,
excluding anything that was reported only via NetFlow."

That is exactly the right filter for "what does group A say to group B?"

Configuration
-------------
Set ``DEFAULT_CONSUMER_SCOPE`` / ``DEFAULT_PROVIDER_SCOPE`` /
``DEFAULT_ROOT_SCOPE`` below for your POV, or pass them on the command
line each time.

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
import csw_helpers

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

    Quick mental model of how scope membership is stored in flow records:
    each flow record carries TWO arrays - ``src_scope_name`` and
    ``dst_scope_name`` - listing every scope each endpoint belongs to
    (workloads belong to many scopes simultaneously, one per level of
    the scope tree). To check "is endpoint X in scope S?" you ask the
    API "does the array contain S?".

    The filter we build is structured logically as:

        (src OR dst is in consumer_scope)
        AND
        (src OR dst is in provider_scope)
        AND NOT (the flow was reported by a NetFlow collector)

    The ``OR`` is important: CSW doesn't know in advance which side of
    the connection is the "consumer" and which is the "provider", so we
    accept either.

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

    Uses the shared ``csw_helpers.paginate()`` helper for the offset-cursor
    loop, rate limiting, and graceful error termination. Caller retains
    control over progress display.
    """
    all_flows = []
    body = {
        "t0": t0,
        "t1": t1,
        "filter": flow_filter,
        "scopeName": root_scope,
    }

    for page, results in csw_helpers.paginate(
        "POST", "/openapi/v1/flowsearch",
        body=body, batch_size=BATCH_SIZE, sleep=0.2,
    ):
        all_flows.extend(results)
        print(
            f"\r  Page {page}: +{len(results)} flows "
            f"(total: {len(all_flows):,})",
            end="", flush=True,
        )

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
