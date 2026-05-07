#!/usr/bin/env python3
"""
download_conversations.py — Download all conversations from a CSW workspace
---------------------------------------------------------------------------

What this script is for (plain English)
---------------------------------------
"Conversation" is a CSW-specific word that confuses everybody at first.
Here is the mental model:

  * A **flow** is one network connection: source IP, destination IP,
    destination port, protocol. Your servers generate millions of these
    every day.
  * Many flows are essentially the same conversation repeated over and
    over (e.g. ``app-server -> db-server : tcp/5432`` happens hundreds of
    times an hour). Logging each one separately would be useless.
  * CSW's **ADM** (Application Dependency Mapping) groups all those
    repeated flows into a single **conversation** record. One row per
    "who-talked-to-who-on-which-port", with byte/packet/flow totals
    aggregated.

So a conversation is a *deduplicated, summarized* flow record - the kind
of thing you actually want to look at when designing segmentation policy
or auditing what an application does.

A few more terms you will meet:

  * **Workspace** (sometimes "Application" in the API): a folder for
    grouping policy rules. Inside a workspace, ADM produces a set of
    conversations and proposes rules for them.
  * **ADM version**: every time ADM is re-run on a workspace it produces
    a new numbered version. The conversations API requires you to pick
    one; this script uses the latest by default.

Why download them?
  * Build offline reports / spreadsheets the engagement team can review.
  * Diff against a snapshot from last month to see drift.
  * Feed them into other analysis tooling.

How the script works
--------------------
  1. Look up the workspace by name (or accept an ID directly).
  2. Find its latest ADM version (or accept a specific one).
  3. Page through the conversations API 500 records at a time, using the
     shared ``csw_helpers.paginate()`` helper, until everything is
     collected.
  4. Save the lot as a single JSON file under ``snapshots/``.

Usage
-----
    python3 download_conversations.py --workspace "MyWorkspace"
    python3 download_conversations.py --app-id <workspace_id>  # direct ID
    python3 download_conversations.py --version 3              # specific ADM version
    python3 download_conversations.py --out snapshots/custom.json

Output
------
    snapshots/conversations-<workspace>-<date>.json
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csw_api
import csw_helpers

csw_api._load_dotenv()

DATE_TAG = datetime.now().strftime("%Y-%m-%d")

# The conversations API supports up to 500 results per request.
BATCH_SIZE = 500


def find_workspace(name: str) -> dict:
    """Look up a workspace (application) by name.

    The CSW API only knows workspaces by their numeric ID, but humans
    name them. So we list every workspace, find the one whose name
    matches (case-insensitive), and return its full record - including
    the ID we'll need for subsequent calls.

    Exits with a helpful list of available workspace names if the lookup
    fails - much friendlier than a stack trace.
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

    Why this matters: every time ADM is re-run on a workspace, it
    produces a new numbered version (1, 2, 3, ...). Older versions stay
    around so you can compare them. The conversations API insists on
    knowing *which* version you want.

    99% of the time you want the latest, so that's what we default to.
    Pass ``--version 3`` to the CLI if you want an older one.
    """
    r = csw_api.make_request("GET", f"/openapi/v1/applications/{app_id}")
    if r.get("status") != 200:
        print(f"  GET /applications/{app_id} failed: HTTP {r.get('status')}")
        sys.exit(1)
    return r["data"].get("latest_adm_version", 1)


def download_all_conversations(app_id: str, version: int) -> list:
    """Paginate through the conversations API and collect all records.

    Uses the shared ``csw_helpers.paginate()`` helper, which handles the
    offset-cursor loop, rate limiting, and graceful error termination.
    Caller retains full control over progress display.
    """
    all_convos = []

    for page, results in csw_helpers.paginate(
        "POST",
        f"/openapi/v1/conversations/{app_id}",
        body={"version": version},
        batch_size=BATCH_SIZE,
        sleep=0.15,
    ):
        all_convos.extend(results)
        print(
            f"\r  Page {page}: +{len(results)} conversations "
            f"(total: {len(all_convos)})",
            end="", flush=True,
        )

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

    # Sanitize workspace name for use in filenames (handles colons,
    # whitespace, slashes, and other filesystem-unfriendly characters)
    out_path = (
        args.out
        or f"snapshots/conversations-{csw_helpers.safe_filename(ws_name)}-{DATE_TAG}.json"
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
