#!/usr/bin/env python3
"""
download_conversations.py — Download all conversations from a CSW workspace
---------------------------------------------------------------------------
Conversations are network flows that have been matched to ADM-generated
policies within a workspace.  Each conversation record includes the
src/dst IP pair, protocol, port, byte/packet counts, policy filter IDs,
and the ADM confidence score.

The script paginates through the CSW conversations API in batches of 500,
collects all records, and saves the full result set as JSON.  A quick
statistical summary (protocol distribution, top ports) is printed at the end.

Usage:
    python3 download_conversations.py --workspace "MyWorkspace"
    python3 download_conversations.py --app-id <workspace_id>  # direct ID
    python3 download_conversations.py --version 3              # specific ADM version
    python3 download_conversations.py --out snapshots/custom.json

Output:
    snapshots/conversations-<workspace>-<date>.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csw_api

csw_api._load_dotenv()

DATE_TAG = datetime.now().strftime("%Y-%m-%d")

# The conversations API supports up to 500 results per request.
BATCH_SIZE = 500


def find_workspace(name: str) -> dict:
    """Look up a workspace (application) by name.

    Performs a case-insensitive match against the list of all workspaces
    in the cluster and returns the first match.
    """
    r = csw_api.make_request("GET", "/openapi/v1/applications")
    if r.get("status") != 200:
        print(f"  GET /applications failed: HTTP {r.get('status')}")
        sys.exit(1)
    apps = r.get("data", [])
    for a in apps:
        if a.get("name", "").lower() == name.lower():
            return a
    print(f"  Workspace '{name}' not found. Available:")
    for a in apps:
        print(f"      - {a.get('name')}")
    sys.exit(1)


def get_latest_version(app_id: str) -> int:
    """Retrieve the latest ADM version number for a workspace.

    The conversations API requires an explicit ADM version.  This fetches
    the workspace details and returns the latest_adm_version field.
    """
    r = csw_api.make_request("GET", f"/openapi/v1/applications/{app_id}")
    if r.get("status") != 200:
        print(f"  GET /applications/{app_id} failed: HTTP {r.get('status')}")
        sys.exit(1)
    return r["data"].get("latest_adm_version", 1)


def download_all_conversations(app_id: str, version: int) -> list:
    """Paginate through the conversations API and collect all records.

    The API uses cursor-based pagination: each response includes an opaque
    "offset" token that must be passed in the next request to fetch the
    next batch.  Pagination ends when fewer than BATCH_SIZE results are
    returned or no offset token is present.
    """
    all_convos = []
    offset = None
    page = 0

    while True:
        page += 1
        body = {"version": version, "limit": BATCH_SIZE}
        if offset:
            body["offset"] = offset

        r = csw_api.make_request(
            "POST",
            f"/openapi/v1/conversations/{app_id}",
            body=body,
        )

        if r.get("status") != 200:
            print(f"\n  API error on page {page}: HTTP {r.get('status')}")
            err = r.get("data", {})
            if isinstance(err, dict):
                print(f"      {err.get('error', err)}")
            break

        data = r.get("data", {})
        results = data.get("results", [])
        all_convos.extend(results)

        batch_count = len(results)
        print(
            f"\r  Page {page}: +{batch_count} conversations "
            f"(total: {len(all_convos)})",
            end="", flush=True,
        )

        if batch_count < BATCH_SIZE:
            break

        offset = data.get("offset")
        if not offset:
            break

        # Gentle rate-limiting to avoid overloading the API
        time.sleep(0.15)

    print()
    return all_convos


def main():
    parser = argparse.ArgumentParser(
        description="Download all conversations from a CSW workspace.",
    )
    parser.add_argument(
        "--workspace", "-w",
        default=None,
        help="Workspace name to download conversations from (required unless --app-id is set)",
    )
    parser.add_argument(
        "--app-id",
        default=None,
        help="Application/workspace ID (overrides --workspace)",
    )
    parser.add_argument(
        "--version", "-v",
        type=int,
        default=None,
        help="ADM version (default: latest)",
    )
    parser.add_argument(
        "--out", "-o",
        default=None,
        help="Output JSON path "
             "(default: snapshots/conversations-<workspace>-<date>.json)",
    )
    args = parser.parse_args()

    os.makedirs("snapshots", exist_ok=True)

    print(f"\n  Connecting to: {os.environ.get('CSW_API_URL', '?')}")
    print(f"  Date: {DATE_TAG}\n")

    # Resolve workspace: either by explicit ID or by name lookup
    if args.app_id:
        app_id = args.app_id
        ws_name = args.workspace
    else:
        ws = find_workspace(args.workspace)
        app_id = ws["id"]
        ws_name = ws["name"]

    version = args.version or get_latest_version(app_id)
    print(f"  Workspace: {ws_name}")
    print(f"  App ID: {app_id}")
    print(f"  ADM version: {version}")
    print(f"  Batch size: {BATCH_SIZE}\n")

    convos = download_all_conversations(app_id, version)

    if not convos:
        print("  No conversations found.")
        return

    # Sanitize workspace name for use in filenames
    safe_name = ws_name.replace(":", "_").replace(" ", "_")
    out_path = (
        args.out or f"snapshots/conversations-{safe_name}-{DATE_TAG}.json"
    )
    with open(out_path, "w") as f:
        json.dump(convos, f, indent=2)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(
        f"\n  Saved {len(convos):,} conversations "
        f"to {out_path} ({size_mb:.1f} MB)"
    )

    # Print protocol and port distribution summary
    protos = {}
    ports = {}
    for c in convos:
        p = c.get("protocol", "?")
        protos[p] = protos.get(p, 0) + 1
        port = c.get("port", "?")
        ports[port] = ports.get(port, 0) + 1

    print(f"\n  Quick stats:")
    print(
        f"      Protocols: "
        f"{dict(sorted(protos.items(), key=lambda x: -x[1]))}"
    )
    top_ports = sorted(ports.items(), key=lambda x: -x[1])[:10]
    print(f"      Top 10 ports: {dict(top_ports)}")


if __name__ == "__main__":
    main()
